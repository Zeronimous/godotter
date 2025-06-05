"""
Injects translated text back into Godot project files.

This module takes a TSV file containing translations and a JSON metadata file
(mapping translation IDs to their original locations) and attempts to inject
the translated text back into the appropriate files (TSCN, TRES, GDScript,
JSON, CSV). It handles string escaping for Godot's specific formats and
attempts to preserve file structure.
"""
import csv
import json
import hashlib
import os
import re

def escape_for_godot_string_literal(text):
    """
    Escapes backslashes and double quotes for strings that will be placed
    inside Godot string literals (e.g., `text = "value"` in TSCN/TRES,
    or `tr("value")` in GDScript).

    Args:
        text (str): The raw string to escape.

    Returns:
        str: The string with backslashes and double quotes escaped.
             Example: 'A "quote"' becomes 'A \\"quote\\"'.
    """
    return text.replace('\\', '\\\\').replace('"', '\\"')

def _parse_json_path(path_str):
    """
    Parses a JSON path string (e.g., 'a.b[0].c') into a list of keys and indices.

    Args:
        path_str (str): The JSON path string.

    Returns:
        list: A list of path components (strings for keys, integers for indices).
    """
    parts = []
    current_part = ""
    in_bracket = False
    for char in path_str:
        if char == '.' and not in_bracket:
            if current_part: parts.append(current_part)
            current_part = ""
        elif char == '[':
            if current_part: parts.append(current_part)
            current_part = ""
            in_bracket = True
        elif char == ']':
            if current_part:
                try: parts.append(int(current_part))
                except ValueError: parts.append(current_part)
            current_part = ""
            in_bracket = False
        else:
            current_part += char
    if current_part: parts.append(current_part)
    return parts

def _set_value_by_json_path(data_struct, path_parts, new_value):
    """
    Sets a value within a nested dictionary/list structure using parsed path parts.

    Args:
        data_struct (dict or list): The JSON data structure to modify.
        path_parts (list): A list of keys/indices from `_parse_json_path`.
        new_value (str): The new string value to set.

    Returns:
        bool: True if the value was successfully set, False otherwise (e.g.,
              path invalid, type mismatch).
    """
    current = data_struct
    for i, part in enumerate(path_parts):
        if i == len(path_parts) - 1:
            if isinstance(current, dict) and isinstance(part, str):
                current[part] = new_value
                return True
            elif isinstance(current, list) and isinstance(part, int) and 0 <= part < len(current):
                current[part] = new_value
                return True
            else: return False
        else:
            if isinstance(current, dict) and isinstance(part, str):
                if part not in current: return False
                current = current[part]
            elif isinstance(current, list) and isinstance(part, int):
                if not (0 <= part < len(current)): return False
                current = current[part]
            else: return False
    return False


def inject_translations(modified_tsv_path, path_json_file_path, unpacked_base_dir):
    """
    Injects translations from a modified TSV file back into the original game files.

    Args:
        modified_tsv_path (str): Path to the user-modified TSV file containing translations.
        path_json_file_path (str): Path to the JSON metadata file (e.g., "output.paths.json")
                                   that maps translation IDs to file locations.
        unpacked_base_dir (str): The directory where the game files were unpacked and
                                 where modifications should be applied. Paths in
                                 `path_json_file_path` are relative to this directory.

    Returns:
        dict: A dictionary containing a summary of the injection process:
              {
                  'processed_ids': list_of_successfully_injected_ids,
                  'warnings': list_of_warning_messages,
                  'errors': list_of_error_messages
              }
    """
    processed_ids = []
    warnings = []
    errors = []

    try:
        with open(path_json_file_path, 'r', encoding='utf-8') as f:
            path_data = json.load(f)
    except FileNotFoundError:
        errors.append(f"Path metadata file not found: {path_json_file_path}")
        return {'processed_ids': processed_ids, 'warnings': warnings, 'errors': errors}
    except json.JSONDecodeError as e:
        errors.append(f"Error decoding JSON from {path_json_file_path}: {e}")
        return {'processed_ids': processed_ids, 'warnings': warnings, 'errors': errors}

    translations_to_inject = []
    try:
        with open(modified_tsv_path, 'r', newline='', encoding='utf-8') as tsvfile:
            reader = csv.DictReader(tsvfile, delimiter='\t')
            for row_num, row in enumerate(reader, 1): # Start row_num from 1 for messages
                if 'ID' not in row or 'OriginalText' not in row or 'ModifiedText' not in row:
                    warnings.append(f"TSV row {row_num} missing required columns (ID, OriginalText, ModifiedText). Row: {row}")
                    continue
                modified_text = row['ModifiedText']
                original_text = row['OriginalText']
                if not modified_text or modified_text.strip() == original_text.strip():
                    # This is not a warning, just skipping unchanged/empty translations
                    continue
                translations_to_inject.append({
                    'id': row['ID'], 'original': original_text,
                    'modified': modified_text.strip()})
    except FileNotFoundError:
        errors.append(f"Modified TSV file not found: {modified_tsv_path}")
        return {'processed_ids': processed_ids, 'warnings': warnings, 'errors': errors}
    except Exception as e:
        errors.append(f"Error reading or processing TSV file {modified_tsv_path}: {e}")
        return {'processed_ids': processed_ids, 'warnings': warnings, 'errors': errors}

    if not translations_to_inject:
        warnings.append("No valid translations (with actual changes) found in the TSV to inject.")
        return {'processed_ids': processed_ids, 'warnings': warnings, 'errors': errors}

    for trans_item in translations_to_inject:
        item_id = trans_item['id']
        metadata = path_data.get(item_id)

        if not metadata:
            warnings.append(f"ID '{item_id}' from TSV not found in path metadata. Skipping.")
            continue

        # Construct full path using unpacked_base_dir and the relative path from metadata
        relative_file_path = metadata['file_path']
        target_file_full_path = os.path.join(unpacked_base_dir, relative_file_path)

        if not os.path.exists(target_file_full_path):
            warnings.append(f"Target file for ID '{item_id}' not found at '{target_file_full_path}' (base: '{unpacked_base_dir}', rel: '{relative_file_path}'). Skipping.")
            continue

        expected_md5 = metadata['original_text_md5']
        current_value_md5 = hashlib.md5(trans_item['original'].encode('utf-8')).hexdigest()
        if current_value_md5 != expected_md5:
            warnings.append(f"MD5 mismatch for ID '{item_id}'. OriginalText in TSV ('{trans_item['original'][:50]}...') does not match expected original text from extraction. Skipping to prevent data corruption.")
            continue

        file_modified_flag = False
        # Variables to store loaded data for writing if modification is successful
        file_lines = []
        json_data_to_write = None # Stores the entire JSON structure if modified
        csv_rows_to_write = []   # Stores all CSV rows if modified

        if metadata['type'] in ['tscn', 'tres', 'gdscript']:
            try:
                with open(target_file_full_path, 'r', encoding='utf-8') as f: file_lines = f.readlines()
            except Exception as e:
                warnings.append(f"Error reading target file {target_file_full_path} for ID '{item_id}': {e}. Skipping.")
                continue

            line_num_1_based = metadata.get('line_number', None)
            if line_num_1_based is None or not (1 <= line_num_1_based <= len(file_lines)):
                 warnings.append(f"Invalid line number {metadata.get('line_number')} for ID '{item_id}'. Max lines: {len(file_lines)}. Skipping.")
                 continue

            actual_line_index_0_based = line_num_1_based - 1
            original_line_content_from_file = file_lines[actual_line_index_0_based]

            modified_text_godot_literal_escaped = escape_for_godot_string_literal(trans_item['modified'])
            original_text_file_literal_escaped = escape_for_godot_string_literal(trans_item['original'])
            replacement_string_for_re_sub = modified_text_godot_literal_escaped

            new_line_content = original_line_content_from_file
            match_count = 0

            if metadata['type'] in ['tscn', 'tres']:
                pattern_str = r'(\b' + re.escape(metadata['key']) + r'\s*=\s*")' + re.escape(original_text_file_literal_escaped) + r'(")'
                def replace_tscn_tres(match): return match.group(1) + replacement_string_for_re_sub + match.group(2)
                new_line_content, match_count = re.subn(pattern_str, replace_tscn_tres, original_line_content_from_file, 1)
            elif metadata['type'] == 'gdscript':
                pattern_str = r'(tr\s*\(\s*")' + re.escape(original_text_file_literal_escaped) + r'("\s*[\),])'
                def replace_gdscript(match): return match.group(1) + replacement_string_for_re_sub + match.group(2)
                new_line_content, match_count = re.subn(pattern_str, replace_gdscript, original_line_content_from_file, 1)

            if match_count > 0:
                file_lines[actual_line_index_0_based] = new_line_content
                file_modified_flag = True
            else:
                warnings.append(f"Could not find pattern to replace for ID '{item_id}' in line: {original_line_content_from_file.strip()}. Pattern tried: {pattern_str}. Skipping.")
                continue

        elif metadata['type'] == 'json':
            try:
                with open(target_file_full_path, 'r', encoding='utf-8') as f: json_data_to_write = json.load(f)
                path_parts = _parse_json_path(metadata['key'])
                if _set_value_by_json_path(json_data_to_write, path_parts, trans_item['modified']):
                    file_modified_flag = True
                else:
                    warnings.append(f"Failed to set value for JSON path '{metadata['key']}' for ID '{item_id}'. Path invalid or structure mismatch. Skipping.")
                    continue
            except json.JSONDecodeError as e:
                warnings.append(f"Error decoding JSON from {target_file_full_path} for ID '{item_id}': {e}. Skipping.")
                continue
            except Exception as e:
                errors.append(f"Error processing JSON file {target_file_full_path} for ID '{item_id}': {e}")
                continue

        elif metadata['type'] == 'csv':
            try:
                with open(target_file_full_path, 'r', encoding='utf-8', newline='') as f: csv_rows_to_write = list(csv.reader(f))

                row_idx_1_based = metadata.get('line_number', 0)
                col_key = metadata.get('key', "")

                if not col_key.startswith("column_"):
                    warnings.append(f"Invalid CSV column key '{col_key}' for ID '{item_id}'. Skipping.")
                    continue

                col_idx = -1
                try:
                    col_idx = int(col_key.split('_')[1])
                except (IndexError, ValueError):
                     warnings.append(f"Could not parse column index from key '{col_key}' for ID '{item_id}'. Skipping.")
                     continue

                if 1 <= row_idx_1_based <= len(csv_rows_to_write) and 0 <= col_idx < len(csv_rows_to_write[row_idx_1_based-1]):
                    csv_rows_to_write[row_idx_1_based-1][col_idx] = trans_item['modified']
                    file_modified_flag = True
                else:
                    max_cols_in_row_str = len(csv_rows_to_write[row_idx_1_based-1]) if 1 <= row_idx_1_based <= len(csv_rows_to_write) else 'N/A (invalid row)'
                    warnings.append(f"CSV row/column index out of bounds for ID '{item_id}'. Row: {row_idx_1_based}, Col: {col_idx}. MaxRow: {len(csv_rows_to_write)}, MaxColInTargetRow: {max_cols_in_row_str}. Skipping.")
                    continue
            except ValueError: # For int(col_key.split('_')[1]) if format is unexpected
                 warnings.append(f"Invalid CSV column key format '{col_key}' for ID '{item_id}'. Skipping.")
                 continue
            except Exception as e:
                errors.append(f"Error processing CSV file {target_file_full_path} for ID '{item_id}': {e}")
                continue
        else:
            warnings.append(f"Unknown file type '{metadata['type']}' for ID '{item_id}'. Skipping.")
            continue

        if file_modified_flag:
            try:
                if metadata['type'] in ['tscn', 'tres', 'gdscript']:
                    with open(target_file_full_path, 'w', encoding='utf-8') as f: f.writelines(file_lines)
                elif metadata['type'] == 'json':
                    with open(target_file_full_path, 'w', encoding='utf-8') as f: json.dump(json_data_to_write, f, indent=2, ensure_ascii=False)
                elif metadata['type'] == 'csv':
                    with open(target_file_full_path, 'w', encoding='utf-8', newline='') as f: csv.writer(f).writerows(csv_rows_to_write)
                processed_ids.append(item_id)
            except Exception as e: errors.append(f"Error writing modified content to {target_file_full_path} for ID '{item_id}': {e}")

    return {'processed_ids': processed_ids, 'warnings': warnings, 'errors': errors}

if __name__ == '__main__':
    # Self-test code remains largely the same, but ensure it aligns with any logic changes.
    # Key changes in main function:
    # - Corrected line number validation for line-based files.
    # - Storing loaded file content (lines, json_data, csv_rows) in variables for writing.
    # - Centralized file writing logic after modification checks.
    # - Improved error reporting for CSV column key parsing and index out of bounds.
    print("Running text_injector.py self-test example (with JSON/CSV)...")
    dummy_unpacked_dir_name = "temp_injector_test_output_files"
    project_root_selftest = "."
    dummy_unpacked_dir = os.path.join(project_root_selftest, dummy_unpacked_dir_name)
    os.makedirs(dummy_unpacked_dir, exist_ok=True)
    path_prefix_in_json = dummy_unpacked_dir_name

    dummy_paths_data = {
        f"{path_prefix_in_json}_test_scene_tscn_2_text": {
            "file_path": os.path.join(path_prefix_in_json, "test_scene.tscn"), "line_number": 2, "key": "text", "type": "tscn",
            "original_text_md5": hashlib.md5("Hello TSCN".encode('utf-8')).hexdigest(),},
        f"{path_prefix_in_json}_game_logic_gd_2_Game_Started_": {
            "file_path": os.path.join(path_prefix_in_json, "game_logic.gd"), "line_number": 2, "key": "Game Started!", "type": "gdscript",
            "original_text_md5": hashlib.md5("Game Started!".encode('utf-8')).hexdigest(),},
        f"{path_prefix_in_json}_data_json_NLN_title": {
            "file_path": os.path.join(path_prefix_in_json, "data.json"), "line_number": None, "key": "title", "type": "json",
            "original_text_md5": hashlib.md5("My JSON Title".encode('utf-8')).hexdigest(),},
        f"{path_prefix_in_json}_data_json_NLN_chapters[0]_name": {
            "file_path": os.path.join(path_prefix_in_json, "data.json"), "line_number": None, "key": "chapters[0].name", "type": "json",
            "original_text_md5": hashlib.md5("Chapter 1 Name".encode('utf-8')).hexdigest(),},
        f"{path_prefix_in_json}_trans_csv_2_column_1": {
            "file_path": os.path.join(path_prefix_in_json, "trans.csv"), "line_number": 2, "key": "column_1", "type": "csv",
            "original_text_md5": hashlib.md5("Hello CSV".encode('utf-8')).hexdigest(),}
    }
    dummy_paths_file = os.path.join(project_root_selftest, "dummy_paths_selftest.json")
    with open(dummy_paths_file, 'w', encoding='utf-8') as f: json.dump(dummy_paths_data, f, indent=2)

    dummy_tsv_content = [
        ['ID', 'OriginalText', 'ModifiedText'],
        [f"{path_prefix_in_json}_test_scene_tscn_2_text", "Hello TSCN", "Hola TSCN"],
        [f"{path_prefix_in_json}_game_logic_gd_2_Game_Started_", "Game Started!", "Juego Iniciado!"],
        [f"{path_prefix_in_json}_data_json_NLN_title", "My JSON Title", "Mi Titulo JSON"],
        [f"{path_prefix_in_json}_data_json_NLN_chapters[0]_name", "Chapter 1 Name", "Nombre Capitulo 1"],
        [f"{path_prefix_in_json}_trans_csv_2_column_1", "Hello CSV", "Hola CSV"],
    ]
    dummy_modified_tsv = os.path.join(project_root_selftest, "dummy_modified_selftest.tsv")
    with open(dummy_modified_tsv, 'w', newline='', encoding='utf-8') as tsvfile:
        csv.writer(tsvfile, delimiter='\t').writerows(dummy_tsv_content)

    with open(os.path.join(dummy_unpacked_dir, "test_scene.tscn"), 'w', encoding='utf-8') as f:
        f.write('property1 = "foo"\ntext = "Hello TSCN"\n')
    with open(os.path.join(dummy_unpacked_dir, "game_logic.gd"), 'w', encoding='utf-8') as f:
        f.write('func _ready():\n    var a = tr("Game Started!")\n')
    json_content_for_test = {"title": "My JSON Title", "chapters": [{"name": "Chapter 1 Name", "value": "..."}]}
    with open(os.path.join(dummy_unpacked_dir, "data.json"), 'w', encoding='utf-8') as f:
        json.dump(json_content_for_test, f, indent=2)
    csv_content_for_test = [["ID", "Original", "Context"], ["1", "Hello CSV", "Greeting"], ["2", "Bye CSV", "Farewell"]]
    with open(os.path.join(dummy_unpacked_dir, "trans.csv"), 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerows(csv_content_for_test)

    print(f"Dummy files created. Target files in '{dummy_unpacked_dir}'.")
    results = inject_translations(dummy_modified_tsv, dummy_paths_file, dummy_unpacked_dir) # Corrected base_dir for self-test

    print("\nInjection Results:")
    print(f"  Processed IDs: {results['processed_ids']}")
    print(f"  Warnings: {results['warnings']}")
    print(f"  Errors: {results['errors']}")

    print("\nVerifying file content post-injection:")
    with open(os.path.join(dummy_unpacked_dir, "test_scene.tscn"), 'r') as f: content = f.read()
    if 'text = "Hola TSCN"' in content: print("  TSCN 'Hola TSCN' VERIFIED.")
    else: print(f"  TSCN 'Hola TSCN' FAILED. Content:\n{content}")
    with open(os.path.join(dummy_unpacked_dir, "game_logic.gd"), 'r') as f: content = f.read()
    if 'var a = tr("Juego Iniciado!")' in content: print("  GDScript 'Juego Iniciado!' VERIFIED.")
    else: print(f"  GDScript 'Juego Iniciado!' FAILED. Content:\n{content}")
    with open(os.path.join(dummy_unpacked_dir, "data.json"), 'r') as f: json_data_ver = json.load(f)
    if json_data_ver["title"] == "Mi Titulo JSON": print("  JSON 'Mi Titulo JSON' VERIFIED.")
    else: print(f"  JSON 'Mi Titulo JSON' FAILED. Got: {json_data_ver['title']}")
    if json_data_ver["chapters"][0]["name"] == "Nombre Capitulo 1": print("  JSON 'Nombre Capitulo 1' VERIFIED.")
    else: print(f"  JSON 'Nombre Capitulo 1' FAILED. Got: {json_data_ver['chapters'][0]['name']}")
    with open(os.path.join(dummy_unpacked_dir, "trans.csv"), 'r', newline='') as f:
        csv_rows_ver = list(csv.reader(f))
    if csv_rows_ver[1][1] == "Hola CSV": print("  CSV 'Hola CSV' VERIFIED.")
    else: print(f"  CSV 'Hola CSV' FAILED. Got: {csv_rows_ver[1][1]}")

    print(f"\nSelf-test finished. Manual cleanup of relevant files might be needed.")

```

**5. `repacker.py`**
