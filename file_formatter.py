"""
Generates output files for the localization process.

This module provides functions to take the aggregated extracted text data
and format it into two main output files:
1. A TSV (Tab-Separated Values) file intended for translators, containing
   a unique ID for each text segment, the original text, and a column for
   the modified (translated) text.
2. A JSON file that stores metadata for each unique ID, including the original
   file path, line number (if applicable), the key or JSON path of the text,
   the type of extraction, an MD5 hash of the original text for verification,
   and the full original line or context.
"""
import json
import csv
import hashlib
import os
import re # Moved import re to the top

def generate_unique_id(file_path_relative, line_number, key_or_path):
    """
    Generates a reasonably unique string ID based on file path, line number, and key.

    The ID is constructed to be filesystem-friendly and unique enough for mapping
    translations back to their original locations.

    Args:
        file_path_relative (str): The path of the file, relative to the unpacked project root.
        line_number (int or None): The line number where the text was found (1-indexed).
                                   Can be None for non-line-based extractions (e.g., JSON).
        key_or_path (str): The property key, JSON path, CSV column identifier,
                           or the text itself (for GDScript tr() calls).

    Returns:
        str: A generated unique ID string.
    """
    clean_file_path = str(file_path_relative).replace(os.sep, '_').replace('.', '_').replace(':', '_')
    clean_key = re.sub(r'[^a-zA-Z0-9_.-]', '_', str(key_or_path))
    if len(clean_key) > 50: # Limit length of key part
        clean_key = clean_key[:47] + "..."
    line_num_str = str(line_number) if line_number is not None else "NLN"
    return f"{clean_file_path}_{line_num_str}_{clean_key}"

def write_output_files(extracted_data, tsv_file_path, path_json_file_path):
    """
    Writes extracted text data to a TSV file for translation and a JSON
    metadata file for mapping translations back.

    Args:
        extracted_data (list): A list of dictionaries, where each dictionary
                               contains extracted text info including 'id', 'file_path' (relative),
                               'line_number', 'key', 'value', 'original_line', and 'type'.
        tsv_file_path (str): Path to write the output TSV file.
        path_json_file_path (str): Path to write the output JSON metadata file.
    """
    if not extracted_data:
        print("Info: No extracted data to write to output files.")
        return

    try:
        with open(tsv_file_path, 'w', newline='', encoding='utf-8') as tsvfile:
            writer = csv.writer(tsvfile, delimiter='\t', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(['ID', 'OriginalText', 'ModifiedText'])
            for item in extracted_data:
                original_text = str(item.get('value', '')).replace('\t', ' ').replace('\n', '\\n').replace('\r', '')
                writer.writerow([
                    item.get('id', 'MISSING_ID'),
                    original_text,
                    ''
                ])
        print(f"TSV translation file written to: {tsv_file_path}")
    except Exception as e:
        print(f"Error writing TSV file {tsv_file_path}: {e}")

    path_metadata = {}
    for item in extracted_data:
        item_id = item.get('id', None)
        if not item_id:
            print(f"Warning: Skipping item with missing ID in extracted_data: {item.get('value')[:50]}...")
            continue

        original_value = str(item.get('value', ''))
        path_metadata[item_id] = {
            'file_path': item.get('file_path', ''),
            'line_number': item.get('line_number', None),
            'key': item.get('key', ''),
            'type': item.get('type', 'unknown'),
            'original_text_md5': hashlib.md5(original_value.encode('utf-8')).hexdigest(),
            'original_line_content': item.get('original_line', '')
        }

    try:
        with open(path_json_file_path, 'w', encoding='utf-8') as jsonfile:
            json.dump(path_metadata, jsonfile, indent=2, ensure_ascii=False)
        print(f"Path metadata JSON file written to: {path_json_file_path}")
    except Exception as e:
        print(f"Error writing Path JSON file {path_json_file_path}: {e}")

if __name__ == '__main__':
    print("--- Running file_formatter.py self-tests ---")
    sample_data_for_formatting = [
        {
            'id': 'output_files_test_scene_tscn_3_text',
            'file_path': 'output_files/test_scene.tscn',
            'line_number': 3, 'key': 'text',
            'value': 'Hello World from TSCN with a \t tab and \n newline.',
            'original_line': 'text = "Hello World from TSCN with a \t tab and \n newline."', 'type': 'tscn'
        },
        { # ... more samples from previous version ...
            'id': 'output_files_game_logic_gd_6_Game_Started_', 'file_path': 'output_files/game_logic.gd',
            'line_number': 6, 'key': 'Game Started!', 'value': 'Game Started!',
            'original_line': 'label.text = tr("Game Started!")', 'type': 'gdscript'
        },
        {
            'id': 'output_files_text_data_json_NLN_char_player_name', 'file_path': 'output_files/text_data.json',
            'line_number': None, 'key': 'character.player.name', 'value': 'Hero',
            'original_line': 'Hero', 'type': 'json'
        }
    ]

    if sample_data_for_formatting:
        test_item = sample_data_for_formatting[0]
        generated_id_example = generate_unique_id(
            test_item['file_path'], test_item.get('line_number'), test_item['key']
        )
        print(f"\nExample generated ID: {generated_id_example}")

    temp_dir_for_formatter_test = "temp_formatter_output"
    os.makedirs(temp_dir_for_formatter_test, exist_ok=True)
    test_tsv_output_path = os.path.join(temp_dir_for_formatter_test, "test_output.tsv")
    test_json_output_path = os.path.join(temp_dir_for_formatter_test, "test_output.paths.json")

    write_output_files(sample_data_for_formatting, test_tsv_output_path, test_json_output_path)

    if os.path.exists(test_tsv_output_path):
        print(f"\nTSV content from '{test_tsv_output_path}' (first few lines):")
        with open(test_tsv_output_path, 'r', encoding='utf-8') as f:
            for i in range(5):
                line = f.readline().strip()
                if not line: break
                print(line)

    if os.path.exists(test_json_output_path):
        print(f"\nJSON metadata content from '{test_json_output_path}' (first few hundred chars):")
        with open(test_json_output_path, 'r', encoding='utf-8') as f:
            print(f.read(500) + "...")
    print(f"\n--- Self-tests finished. Manual cleanup of '{temp_dir_for_formatter_test}' might be needed. ---")

```

Now, proceeding to `text_injector.py`.
