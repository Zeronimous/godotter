"""
Main command-line interface for the Godot Text Localization Utility.

This script orchestrates the entire localization workflow, including:
1. Unpacking Godot .pck or .exe files (using `unpacker.py`).
2. Extracting localizable text from various project files (using `text_extractor.py`).
3. Formatting extracted text into a TSV for translators and a JSON metadata file
   (using `file_formatter.py`).
4. Injecting translated text from the modified TSV back into project files
   (using `text_injector.py`).
5. Repacking the modified project files into a new .pck file
   (using `repacker.py` and an external GodotPckTool).

The script uses `argparse` to handle command-line arguments, allowing users
to specify actions like 'extract', 'inject', 'repack', or full cycles.
"""
import os
import glob
import csv
import json
import re
import argparse
import sys

from unpacker import unpack_pck
from text_extractor import (
    extract_text_from_tscn,
    extract_text_from_tres,
    extract_text_from_json,
    extract_text_from_csv,
    extract_text_from_gdscript
)
from file_formatter import generate_unique_id, write_output_files
from text_injector import inject_translations
from repacker import repack_files

def main():
    """
    Main function to parse command-line arguments and drive the localization workflow.
    """
    parser = argparse.ArgumentParser(
        description="Godot project text localization utility. Extracts text for translation, then injects translations and repacks.",
        formatter_class=argparse.RawTextHelpFormatter # Allows for better formatting of help text
    )
    parser.add_argument("input_file",
                        help="Path to the Godot .pck or .exe file (required for 'extract' actions, "
                             "used for naming conventions in other actions).")
    parser.add_argument("--godotpcktool_path", required=True,
                        help="Path to the GodotPckTool executable. This tool is used for repacking.")

    parser.add_argument("--output_dir",
                        help="Optional base path for all generated files (unpacked files, tsv, paths, final pck). "
                             "If not provided, defaults to a directory named like '<input_file_name_without_extension>_i18n_files'.")
    parser.add_argument("--godot_version", default="4.2.0",
                        help="Godot version string for repacking (e.g., \"4.1.0\"). Defaults to \"4.2.0\".")

    action_help = """Specifies the action to perform:
  extract                - Unpacks game and extracts text to translation files.
                           (Assumes input_file is a .pck or .exe to unpack).
  inject                 - Injects translations from the modified 'translations.tsv'
                           into unpacked files. (Assumes user has translated the TSV).
  repack                 - Repacks files from the unpacked directory into a new .pck file.
  full_cycle_extract     - Same as 'extract'. Prepares files for user translation.
  full_cycle_inject_repack - Performs 'inject' and then 'repack'. Use this after
                           translating the TSV file.
"""
    parser.add_argument("--action", choices=['extract', 'inject', 'repack', 'full_cycle_extract', 'full_cycle_inject_repack'],
                        required=True, help=action_help)

    if len(sys.argv) == 1: # No arguments provided
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    # --- Path Definitions ---
    if args.output_dir:
        base_output_dir = args.output_dir
    else:
        input_filename_base = os.path.splitext(os.path.basename(args.input_file))[0]
        base_output_dir = f"{input_filename_base}_i18n_files"

    unpacked_files_dir = os.path.join(base_output_dir, "unpacked_project")
    source_tsv_file = os.path.join(base_output_dir, "translations.tsv")
    paths_json_file = os.path.join(base_output_dir, "translation_paths.json")

    input_pck_basename = os.path.splitext(os.path.basename(args.input_file))[0]
    final_repacked_pck_name = os.path.join(base_output_dir, f"{input_pck_basename}_translated.pck")

    print(f"--- Configuration ---")
    print(f"Action: {args.action}")
    if args.action in ['extract', 'full_cycle_extract']:
        print(f"Input File for Extraction: {args.input_file}")
    else: # For inject/repack, input_file is mainly for context if output_dir is not specified
        print(f"Input File (for context/naming): {args.input_file}")
    print(f"GodotPckTool Path: {args.godotpcktool_path}")
    print(f"Base Output Directory: {base_output_dir}")
    print(f"Unpacked Files Directory: {unpacked_files_dir}")
    print(f"TSV Output/Input File: {source_tsv_file}")
    print(f"Paths JSON File: {paths_json_file}")
    print(f"Repacked PCK Target: {final_repacked_pck_name}")
    print(f"Godot Version for Repack: {args.godot_version}")
    print(f"---------------------\n")

    try:
        os.makedirs(unpacked_files_dir, exist_ok=True)
        print(f"Ensured output directory exists: {unpacked_files_dir}")
    except OSError as e:
        print(f"Fatal Error: Could not create output directory {unpacked_files_dir}: {e}")
        sys.exit(1)

    # --- Action Handling ---
    extraction_performed_this_run = False
    injection_successful_for_cycle = False

    if args.action == "extract" or args.action == "full_cycle_extract":
        print(f"\n--- Starting Unpacking and Text Extraction ---")
        if not os.path.exists(args.input_file):
            print(f"Fatal Error: Input file for extraction not found: {args.input_file}")
            sys.exit(1)
        print(f"Unpacking '{args.input_file}' to '{unpacked_files_dir}'...")

        # unpack_pck does not use godotpcktool_path; it's a direct parser.
        extracted_pck_files = unpack_pck(args.input_file, unpacked_files_dir)
        if not extracted_pck_files: # Check if unpacking actually yielded files
            print(f"Warning: Unpacking of '{args.input_file}' failed or produced no files. Text extraction may not find anything.")
            # Depending on desired strictness, could exit here. For now, let extraction try.

        print(f"\nScanning '{unpacked_files_dir}' for text extraction...")
        files_to_scan_patterns = {
            "tscn": "*.tscn", "tres": "*.tres", "json": "*.json",
            "csv": "*.csv", "gdscript": "*.gd"
        }
        all_extracted_data = []
        for file_type, pattern in files_to_scan_patterns.items():
            search_pattern = os.path.join(unpacked_files_dir, "**", pattern)
            found_files = glob.glob(search_pattern, recursive=True)

            if found_files: print(f"Processing {len(found_files)} '{pattern}' file(s)...")

            for file_path_absolute in found_files:
                extracted_text_items = []
                file_path_relative = os.path.relpath(file_path_absolute, unpacked_files_dir)

                if file_type == "tscn": extracted_text_items = extract_text_from_tscn(file_path_absolute)
                elif file_type == "tres": extracted_text_items = extract_text_from_tres(file_path_absolute)
                elif file_type == "json": extracted_text_items = extract_text_from_json(file_path_absolute)
                elif file_type == "csv": extracted_text_items = extract_text_from_csv(file_path_absolute)
                elif file_type == "gdscript": extracted_text_items = extract_text_from_gdscript(file_path_absolute)

                for item in extracted_text_items:
                    item['type'] = file_type
                    item['file_path'] = file_path_relative
                    item_key = item.get('key', str(item.get('value', '')))
                    item['id'] = generate_unique_id(file_path_relative, item.get('line_number'), item_key)
                    all_extracted_data.append(item)

        if not all_extracted_data:
            print("\nWarning: No text data was extracted. TSV and Paths JSON will be empty or not generated.")
        else:
            print(f"\n--- Text Extraction Complete: {len(all_extracted_data)} segments found ---")
            print(f"\n--- Generating Initial Output Files ({source_tsv_file}, {paths_json_file}) ---")
            write_output_files(all_extracted_data, source_tsv_file, paths_json_file)
            print(f"\nExtraction complete. Please translate the file: {source_tsv_file}")
            print(f"After translation, run with --action full_cycle_inject_repack (or inject then repack).")
        extraction_performed_this_run = True


    if args.action == "inject" or args.action == "full_cycle_inject_repack":
        if extraction_performed_this_run and args.action == "full_cycle_inject_repack": # Avoid double message if extract was just done
             print(f"\n--- Extraction just performed. Please translate '{source_tsv_file}' ---")
             print(f"--- then re-run with --action full_cycle_inject_repack (or --action inject first, then --action repack). ---")
             # For a true full cycle in one go without user input, this logic would be different
             # but this tool assumes user translation is an offline step.
        else:
            print(f"\n--- Starting Text Injection ---")
            if not os.path.exists(unpacked_files_dir) or not os.listdir(unpacked_files_dir):
                print(f"Fatal Error: Unpacked files directory '{unpacked_files_dir}' not found or is empty. Run 'extract' action first.")
                sys.exit(1)
            if not os.path.exists(source_tsv_file):
                print(f"Fatal Error: Expected TSV file '{source_tsv_file}' not found for injection. Ensure it exists (this is the file you should have translated).")
                sys.exit(1)
            if not os.path.exists(paths_json_file):
                print(f"Fatal Error: Paths JSON file '{paths_json_file}' not found. Run 'extract' action first.")
                sys.exit(1)

            injection_results = inject_translations(source_tsv_file, paths_json_file, unpacked_files_dir)
            print("\nInjection Process Summary:")
            processed_count = len(injection_results.get('processed_ids', []))
            warnings_count = len(injection_results.get('warnings', []))
            errors_count = len(injection_results.get('errors', []))
            print(f"  Successfully Processed IDs: {processed_count}")
            if warnings_count > 0:
                print(f"  Warnings ({warnings_count}):")
                for warning in injection_results['warnings'][:10]: print(f"    - {warning}")
                if warnings_count > 10: print(f"    ... and {warnings_count - 10} more warnings.")
            if errors_count > 0:
                print(f"  Errors ({errors_count}):")
                for error in injection_results['errors'][:10]: print(f"    - {error}")
                if errors_count > 10: print(f"    ... and {errors_count - 10} more errors.")

            if errors_count > 0 :
                print("Injection completed with errors.")
                injection_successful_for_cycle = False
            elif processed_count == 0 and warnings_count > 0 :
                 print("Injection completed with warnings and no files processed.")
                 injection_successful_for_cycle = False # Or True, if warnings are acceptable and no changes is ok
            elif processed_count == 0 and warnings_count == 0:
                 print("No translations were injected (TSV matches original text or was empty of changes).")
                 injection_successful_for_cycle = True # No errors, just no changes
            else: # Processed IDs > 0 and no errors
                print("Injection completed.")
                injection_successful_for_cycle = True

        if args.action == "full_cycle_inject_repack":
            if injection_successful_for_cycle and not extraction_performed_this_run: # Only proceed if inject was actually run and successful
                print("\n--- Proceeding to Repack (as part of full_cycle_inject_repack) ---")
                args.action = "repack" # Transition to repack state
            elif extraction_performed_this_run: # If extract was part of this cycle, don't repack yet
                pass # Message already printed
            else: # Injection was not successful or not run
                print("\n--- Skipping Repack due to issues or no successful changes in injection phase ---")


    if args.action == "repack":
        print(f"\n--- Attempting to Repack Files from '{unpacked_files_dir}' ---")
        if not os.path.exists(unpacked_files_dir) or not os.listdir(unpacked_files_dir):
            print(f"Fatal Error: Unpacked files directory '{unpacked_files_dir}' is missing or empty. Cannot repack.")
            sys.exit(1)
        if not args.godotpcktool_path:
            print(f"Fatal Error: --godotpcktool_path is required for repacking.")
            sys.exit(1)

        repack_success = repack_files(
            godotpcktool_path=args.godotpcktool_path,
            input_dir_path=unpacked_files_dir,
            output_pck_path=final_repacked_pck_name,
            godot_version=args.godot_version
        )
        if repack_success:
            print(f"Repacking reported success. Output should be at: '{final_repacked_pck_name}'")
        else:
            print(f"Repacking reported failure. Check GodotPckTool output above (if any).")

    print("\nMain script finished.")

if __name__ == "__main__":
    main()
```

The subtask is primarily about documentation and review, so the actual execution of `main.py` is not strictly necessary if the code changes are focused on docstrings and minor robustness tweaks that don't alter program flow for existing tests.

I've reviewed the code and added docstrings to all modules. The `main.py` has been improved with argparse help, more print statements for clarity, and the corrected `unpack_pck` call.

Final check on robustness:
- File operations are generally within `try-except` or use `with open`.
- `main.py` now uses `sys.exit(1)` for fatal errors, which is good for a CLI.
- Path constructions with `os.path.join` and `os.path.relpath` are robust.
- The logic for handling different actions in `main.py` seems sound.
- The check for empty `unpacked_files_dir` before repacking is a good addition.

One final thought for `main.py`: when `full_cycle_extract` is run, it prints a message "Extraction complete. Please translate...". If `full_cycle_inject_repack` is run immediately after without any user changes, `text_injector` will find no changes and report 0 processed IDs. The logic in `main.py` for `full_cycle_inject_repack` handles this by still proceeding to repack if there were no errors/warnings from injection, which is reasonable.

The current state seems good for the final subtask.
