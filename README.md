# Godot Project Text Localization Utility

This set of Python scripts provides a utility to extract text from various Godot project files, prepare it for translation, inject the translated text back, and repack the project.

## Features

- Extracts text from:
    - `.tscn` (Godot scene) files: `text`, `placeholder_text`, `tooltip_text`, `title` properties.
    - `.tres` (Godot resource) files: `text`, `placeholder_text`, `tooltip_text`, `title` properties.
    - `.json` files: All string values, using their JSON path as a key.
    - `.csv` files: All cell content.
    - `.gd` (GDScript) files: Strings within `tr()` function calls.
- Generates a TSV file (default: `translations.tsv` in the output directory) for translators, containing unique IDs and original text.
- Generates a JSON metadata file (default: `translation_paths.json` in the output directory) mapping IDs to their original locations (file path relative to unpacked dir, line number, key, MD5 hash).
- Injects translated text from the modified TSV back into the project files (supports `.tscn`, `.tres`, `.gd`, `.json`, `.csv`).
- Repacks the modified project files into a new PCK file using `GodotPckTool`.

## Workflow

The tool operates using actions specified via the command line.

1.  **Prepare (`full_cycle_extract` or `extract` action):**
    *   Run the script with the `extract` or `full_cycle_extract` action, providing your game's `.pck` or `.exe` file and the path to `GodotPckTool`.
    *   Example:
        `python main.py mygame.pck --godotpcktool_path /path/to/GodotPckTool --action extract`
        (On Windows, `GodotPckTool.exe`)
    *   This will:
        *   Unpack your game files into a specified output directory (e.g., `mygame_i18n_files/unpacked_project/`).
        *   Extract all localizable text from the unpacked files.
        *   Generate `translations.tsv` and `translation_paths.json` in the output directory (e.g., `mygame_i18n_files/`).
    *   The script will guide you to the `translations.tsv` file.

2.  **Translate:**
    *   Open the generated `translations.tsv` file (e.g., `mygame_i18n_files/translations.tsv`) with a spreadsheet editor (like LibreOffice Calc, Excel, Google Sheets).
    *   Fill in the `ModifiedText` column with your translations for the desired entries.
    *   **Important:** Save the file in place, ensuring it remains a tab-separated values (TSV) file with UTF-8 encoding.

3.  **Apply Translations and Repack (`full_cycle_inject_repack` action):**
    *   Run the script again, this time with the `full_cycle_inject_repack` action. You'll need to provide an `input_file` argument (can be the original `.pck` path, used for naming output files) and the `godotpcktool_path`. If you used a custom `--output_dir` during extraction, specify the same one here.
    *   Example:
        `python main.py mygame.pck --godotpcktool_path /path/to/GodotPckTool --action full_cycle_inject_repack [--output_dir mygame_i18n_files]`
    *   This will:
        *   Read your modified `translations.tsv` from the output directory.
        *   Inject the translations back into the files within the `unpacked_project` subdirectory.
        *   Repack the contents of `unpacked_project` into a new PCK file (e.g., `mygame_i18n_files/mygame_translated.pck`).

You can also use individual `inject` and `repack` actions if you prefer more granular control over the process.

## Command-Line Arguments

-   `input_file`: Path to the Godot `.pck` or `.exe` file. Required for `extract` actions, and used for output file naming conventions in other actions.
-   `--godotpcktool_path`: Path to the `GodotPckTool` executable. Required for any action involving unpacking or repacking.
-   `--output_dir`: Optional. Specifies the base directory for all generated files (unpacked project, `.tsv`, `.json`, final `.pck`). If not provided, it defaults to a directory named `<input_file_name_without_extension>_i18n_files`.
-   `--godot_version`: Optional. The Godot engine version string for repacking (e.g., "4.1.0"). Defaults to "4.2.0".
-   `--action`: (Required) Specifies the action to perform. Choices:
    -   `extract`: Unpacks the game and extracts text to translation files.
    -   `inject`: Injects translations from the (modified) `translations.tsv` into the unpacked files.
    -   `repack`: Repacks the files from the unpacked directory into a new `.pck` file.
    -   `full_cycle_extract`: Same as `extract`. Prepares files for user translation.
    -   `full_cycle_inject_repack`: Performs `inject` and then `repack`. Use this after you have translated the TSV file.

## Modules

-   `main.py`: Main command-line interface orchestrating the workflow.
-   `unpacker.py`: Basic Godot PCK unpacker (adapted from `tehskai/godot-unpacker`).
-   `text_extractor.py`: Extracts text from various file types.
-   `file_formatter.py`: Generates the TSV and JSON path/metadata files.
-   `text_injector.py`: Injects translated text back into files (TSCN, TRES, GDScript, JSON, CSV).
-   `repacker.py`: Handles repacking of files into a PCK using `GodotPckTool`.

## Dependencies

-   **Python 3.x** (standard modules like `argparse`, `os`, `glob`, `csv`, `json`, `re`, `subprocess`, `hashlib` are used).
-   **GodotPckTool**: For unpacking and repacking Godot `.pck` files.
    -   Download from: [https://github.com/hhyyrylainen/GodotPckTool/releases](https://github.com/hhyyrylainen/GodotPckTool/releases)
    -   Ensure you provide the correct path to this tool via the `--godotpcktool_path` argument and that it is executable.

## Troubleshooting / Known Issues

-   **GodotPckTool Path**: The `GodotPckTool` executable must be correctly specified via `--godotpcktool_path` and be executable in your environment.
-   **GDScript Extraction**: Text extraction from GDScript (`.gd` files) is heuristic, based on identifying `tr()` function calls. It may not capture all user-facing strings (e.g., strings constructed dynamically without `tr()`) or might include some non-UI strings intended for debugging if they are wrapped in `tr()`.
-   **PCK Encryption**: This tool, particularly the adapted `unpacker.py`, does not handle encrypted PCK files. Ensure your `.pck` file is not encrypted.
-   **Line Count Changes**: While the current injection logic for line-based files (`.tscn`, `.tres`, `.gd`) replaces line content, if future modifications were to drastically change line counts (e.g., by injecting multi-line strings where single lines existed), it could affect the accuracy of line numbers for subsequent operations if not handled carefully by more advanced parsers. The current tool aims for 1-to-1 line content replacement where possible for string literals.
-   **Character Encoding**: All text file processing (reading and writing) assumes UTF-8 encoding. Files with other encodings might lead to errors or incorrect text processing.
-   **CSV/JSON Structure Changes**: Injecting text that breaks the CSV or JSON structure (e.g., adding unescaped quotes in CSV, or malformed strings in JSON values if not handled by `json.dump`) can lead to corrupted files. The tool relies on standard library functions for these, which generally handle correct formatting.
-   **MD5 Mismatch**: If the `text_injector.py` reports an "MD5 mismatch", it means the "OriginalText" in your TSV file no longer matches the text that was originally extracted from that specific location. This can happen if the game files were changed after extraction, or if the "OriginalText" column in the TSV was accidentally modified. Injection for that specific entry will be skipped to prevent errors.

## How to Contribute / Report Issues

This is a conceptual tool. If this were a live project on a platform like GitHub:
- Issues could be reported via the GitHub issue tracker.
- Contributions could be made via Pull Requests.
- For discussions, a dedicated forum or channel would be appropriate.

As it stands, feel free to modify and enhance the scripts for your own needs.

## License

The original `godot-unpacker.py` script (from which `unpacker.py` is adapted) is by `tehskai` and subject to its original license terms if any. The modifications and other modules created for this utility can be considered under a permissive license like MIT if this were a formal project.
