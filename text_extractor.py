"""
Extracts text from various Godot project file types for localization.

This module provides functions to parse different file formats commonly found
in Godot projects (TSCN, TRES, JSON, CSV, GDScript) and extract strings
that are likely candidates for translation. Each extraction function returns
a list of dictionaries, where each dictionary contains details about the
extracted string, its location, and the original line/context.
"""
import re
import os
import json
import csv

def _extract_text_from_line_based_file(file_path, target_keys, file_type_label):
    """
    Internal helper for TSCN and TRES files to extract key = "value" patterns.

    Args:
        file_path (str): Path to the file.
        target_keys (list): List of string keys to look for (e.g., "text", "title").
        file_type_label (str): Label for the file type (e.g., "tscn", "tres") for context.

    Returns:
        list: A list of dictionaries, each containing:
              'file_path', 'line_number', 'key', 'value', 'original_line'.
    """
    extracted_data = []
    # Regex: start of line, optional whitespace, (key1|key2), optional whitespace, =,
    # optional whitespace, quote, (captured value - handling escaped quotes),
    # quote, optional whitespace, optional comment (`;`), end of line.
    keys_regex_part = "|".join(map(re.escape, target_keys)) # Escape keys for regex
    regex_pattern = r'^\s*(' + keys_regex_part + r')\s*=\s*"((?:\\.|[^"\\])*)"\s*(?:;.*)?$'

    if not os.path.exists(file_path):
        # This check is also in main.py's glob, but good for direct use.
        # print(f"Info: File not found at {file_path} for {file_type_label} extraction.")
        return []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f, 1):
                match = re.search(regex_pattern, line)
                if match:
                    key = match.group(1)
                    value = match.group(2).replace('\\"', '"').replace('\\\\', '\\')
                    extracted_data.append({
                        'file_path': file_path, # Will be made relative in main.py
                        'line_number': line_number,
                        'key': key,
                        'value': value,
                        'original_line': line.rstrip('\n\r')
                    })
    except Exception as e:
        print(f"Error reading or processing {file_type_label} file {file_path}: {e}")
    return extracted_data

def extract_text_from_tscn(file_path):
    """
    Extracts specified text properties (text, placeholder_text, tooltip_text, title)
    from a Godot TSCN (.tscn) file.

    Args:
        file_path (str): The path to the .tscn file.

    Returns:
        list: A list of dictionaries containing extracted text information.
    """
    target_keys = ["text", "placeholder_text", "tooltip_text", "title"]
    return _extract_text_from_line_based_file(file_path, target_keys, "tscn")

def extract_text_from_tres(file_path):
    """
    Extracts specified text properties (text, placeholder_text, tooltip_text, title)
    from a Godot TRES (.tres) file.

    Args:
        file_path (str): The path to the .tres file.

    Returns:
        list: A list of dictionaries containing extracted text information.
    """
    target_keys = ["text", "placeholder_text", "tooltip_text", "title"]
    return _extract_text_from_line_based_file(file_path, target_keys, "tres")

def _traverse_json_for_strings(data, current_path, file_path, results_list):
    """
    Recursively traverses a JSON data structure (dicts and lists) to find all string values.

    Args:
        data: The current piece of JSON data (dict, list, string, etc.).
        current_path (str): The JSON path built up to this point for `data`.
        file_path (str): The path of the JSON file being processed.
        results_list (list): The list to append extracted string data to.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{current_path}.{key}" if current_path else key
            _traverse_json_for_strings(value, new_path, file_path, results_list)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_path = f"{current_path}[{i}]"
            _traverse_json_for_strings(item, new_path, file_path, results_list)
    elif isinstance(data, str):
        results_list.append({
            'file_path': file_path, # Will be made relative in main.py
            'line_number': None,  # Line numbers are not typically tracked for individual JSON string values
            'key': current_path,  # The full JSON path to the string
            'value': data,
            'original_line': data # For JSON, the value itself is the most direct "original line"
        })

def extract_text_from_json(file_path):
    """
    Extracts all string values from a JSON (.json) file.
    The 'key' for each extracted string is its JSON path (e.g., "parent.child.key").

    Args:
        file_path (str): The path to the .json file.

    Returns:
        list: A list of dictionaries containing extracted string information.
    """
    extracted_data = []
    if not os.path.exists(file_path):
        # print(f"Info: File not found at {file_path} for JSON extraction.")
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data_structure = json.load(f)
        _traverse_json_for_strings(data_structure, "", file_path, extracted_data)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON file {file_path}: {e}")
    except Exception as e:
        print(f"Error reading or processing JSON file {file_path}: {e}")
    return extracted_data

def extract_text_from_csv(file_path):
    """
    Extracts all cell content from a CSV (.csv) file.
    Each cell's content is treated as a string. The 'key' is "column_X".

    Args:
        file_path (str): The path to the .csv file.

    Returns:
        list: A list of dictionaries containing extracted cell information.
    """
    extracted_data = []
    if not os.path.exists(file_path):
        # print(f"Info: File not found at {file_path} for CSV extraction.")
        return []
    try:
        with open(file_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            for row_idx, row_content in enumerate(reader, 1): # CSV lines are 1-indexed
                for col_idx, cell_value in enumerate(row_content):
                    if cell_value and cell_value.strip(): # Only add if cell is not empty or just whitespace
                        extracted_data.append({
                            'file_path': file_path, # Will be made relative in main.py
                            'line_number': row_idx,
                            'key': f"column_{col_idx}", # Key indicates the column
                            'value': cell_value,
                            'original_line': cell_value # The cell content itself
                        })
    except csv.Error as e:
        # Try to get line number if available from csv.Error
        line_num_info = f"near line {e.line_num}" if hasattr(e, 'line_num') else ""
        print(f"Error reading CSV file {file_path} {line_num_info}: {e}")
    except Exception as e:
        print(f"Error processing CSV file {file_path}: {e}")
    return extracted_data

def extract_text_from_gdscript(file_path):
    """
    Extracts string literals from `tr()` function calls in GDScript (.gd) files.
    This uses a heuristic regex approach. The extracted string itself is used as the 'key'.

    Args:
        file_path (str): The path to the .gd file.

    Returns:
        list: A list of dictionaries containing extracted `tr()` call information.
    """
    extracted_data = []
    # Regex to find tr("string_literal") or tr('string_literal')
    # It captures the string content, handling escaped quotes within.
    # Allows for tr() to be followed by other arguments (e.g., context, placeholders).
    regex_pattern = r'tr\s*\(\s*"(?P<d_quote_val>(?:\\.|[^"\\])*)"\s*[\),]|tr\s*\(\s*\'(?P<s_quote_val>(?:\\.|[^\'\\])*)\'\s*[\),]'

    if not os.path.exists(file_path):
        # print(f"Info: File not found at {file_path} for GDScript extraction.")
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_number, line_content in enumerate(f, 1):
                for match in re.finditer(regex_pattern, line_content):
                    # Check which named group captured the value
                    value_double_quoted = match.group("d_quote_val")
                    value_single_quoted = match.group("s_quote_val")

                    raw_value = ""
                    if value_double_quoted is not None:
                        raw_value = value_double_quoted.replace('\\"', '"').replace('\\\\', '\\')
                    elif value_single_quoted is not None:
                        raw_value = value_single_quoted.replace("\\'", "'").replace('\\\\', '\\')

                    if raw_value: # Ensure we got a value
                        extracted_data.append({
                            'file_path': file_path, # Will be made relative in main.py
                            'line_number': line_number,
                            'key': raw_value, # For tr() calls, the text itself is often used as a key or default
                            'value': raw_value,
                            'original_line': line_content.rstrip('\n\r')
                        })
    except Exception as e:
        print(f"Error reading or processing GDScript file {file_path}: {e}")
    return extracted_data

if __name__ == '__main__':
    # Self-test examples (primarily for dev testing, not exhaustive)
    print("--- Running text_extractor.py self-tests ---")
    os.makedirs("temp_extractor_test_files", exist_ok=True)

    # TSCN Test
    tscn_path = "temp_extractor_test_files/test.tscn"
    with open(tscn_path, "w", encoding="utf-8") as f:
        f.write('[node name="Label" type="Label"]\ntext = "Hello TSCN"\nplaceholder_text = "Enter \\"text\\""\n')
    print(f"\nTSCN Test ({tscn_path}):")
    for item in extract_text_from_tscn(tscn_path): print(item)

    # TRES Test
    tres_path = "temp_extractor_test_files/test.tres"
    with open(tres_path, "w", encoding="utf-8") as f:
        f.write('[resource]\ntitle = "Test Resource Title"\n')
    print(f"\nTRES Test ({tres_path}):")
    for item in extract_text_from_tres(tres_path): print(item)

    # JSON Test
    json_path = "temp_extractor_test_files/test.json"
    with open(json_path, "w", encoding="utf-8") as f:
        data_to_dump = {
            "greeting": "Hello JSON",
            "details": {
                "path": "a.b.c",
                # Corrected line: ensure no stray backslash before the comment
                "value": "JSON data with a \\"quote\\"" # This Python string is 'JSON data with a "quote"'
            },
            "items": ["item1", "item2"]
        }
        json.dump(data_to_dump, f, ensure_ascii=False, indent=2) # Added ensure_ascii and indent for good practice
    print(f"\nJSON Test ({json_path}):")
    for item in extract_text_from_json(json_path): print(item)

    # CSV Test
    csv_path = "temp_extractor_test_files/test.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "text_key", "translation"])
        writer.writerow(["1", "GREETING_TEXT", "Hello, CSV World!"])
        writer.writerow(["2", "FAREWELL_TEXT", "Goodbye, and thanks for all the ""fish""!"])
    print(f"\nCSV Test ({csv_path}):")
    for item in extract_text_from_csv(csv_path): print(item)

    # GDScript Test
    gd_path = "temp_extractor_test_files/test.gd"
    with open(gd_path, "w", encoding="utf-8") as f:
        f.write('extends Node\nfunc _ready():\n    var a = tr("Hello GDScript")\n    var b = tr(\'Apostrophe Test\')\n    var c = tr("Complex with \\"quotes\\" and %s" % "placeholder", "context here")\n')
    print(f"\nGDScript Test ({gd_path}):")
    for item in extract_text_from_gdscript(gd_path): print(item)

    # Cleanup
    import shutil
    shutil.rmtree("temp_extractor_test_files")
    print("\n--- Self-tests finished and temp files cleaned up. ---")

```

**3. `file_formatter.py`**
