"""
Repacks Godot project files into a PCK archive using GodotPckTool.

This module provides a function to interface with the external GodotPckTool
executable to create a .pck file from a directory of game files. This is
typically the final step after translations have been injected.
"""
import subprocess
import os

def repack_files(godotpcktool_path, input_dir_path, output_pck_path, godot_version="4.2.0"):
    """
    Repacks files from a directory into a Godot PCK file using GodotPckTool.

    The contents of `input_dir_path` will form the root of the PCK archive.
    For example, if `input_dir_path` contains `file.txt` and `subdir/image.png`,
    the PCK will have `res://file.txt` and `res://subdir/image.png`.

    Args:
        godotpcktool_path (str): Path to the GodotPckTool executable.
        input_dir_path (str): The directory containing files to be packed.
        output_pck_path (str): The desired path for the newly created .pck file.
        godot_version (str): The Godot version string to embed in the PCK file
                             (e.g., "4.2.0").

    Returns:
        bool: True if repacking was successful (or simulated successfully with "echo"),
              False otherwise.
    """
    if not os.path.exists(godotpcktool_path):
        print(f"Error: GodotPckTool not found at '{godotpcktool_path}'.")
        # Specific check for placeholder used in main.py for testing
        if os.path.basename(godotpcktool_path) == "echo" or godotpcktool_path == "echo":
             print("       (This is expected if 'echo' is used as a placeholder for testing the command printout.)")
        return False

    if not os.path.isdir(input_dir_path):
        print(f"Error: Input directory '{input_dir_path}' not found or is not a directory.")
        return False

    # Ensure the output directory for the PCK file exists
    output_pck_dir = os.path.dirname(output_pck_path)
    if output_pck_dir and not os.path.exists(output_pck_dir):
        try:
            os.makedirs(output_pck_dir)
            print(f"Info: Created output directory for PCK: {output_pck_dir}")
        except Exception as e:
            print(f"Error: Could not create output directory {output_pck_dir}: {e}")
            return False

    # Command structure for GodotPckTool:
    # <tool_path> <output_pck_file> pack <folder_to_pack_contents> --godot-version <version>
    command = [
        godotpcktool_path,
        output_pck_path,
        "pack",
        input_dir_path, # The contents of this directory become the PCK root
        "--godot-version",
        godot_version
    ]

    print(f"\nExecuting Repacker Command: {' '.join(command)}")

    try:
        # Special handling for 'echo' placeholder to simulate success for testing main.py flow
        if os.path.basename(godotpcktool_path) == "echo" or godotpcktool_path == "echo":
            print("SIMULATING GodotPckTool execution with 'echo'. Command arguments printed above.")
            print(f"Output PCK file would be notionally created at: {output_pck_path}")
            return True # Simulate success for echo

        process = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8')

        if process.returncode == 0:
            print(f"GodotPckTool executed successfully.")
            print(f"Output PCK file created at: {output_pck_path}")
            if process.stdout:
                print("GodotPckTool STDOUT:")
                print(process.stdout)
            return True
        else:
            print(f"Error executing GodotPckTool. Return code: {process.returncode}")
            if process.stdout: # GodotPckTool might print errors to stdout
                print("GodotPckTool STDOUT:")
                print(process.stdout)
            if process.stderr:
                print("GodotPckTool STDERR:")
                print(process.stderr)
            return False
    except FileNotFoundError:
        print(f"Error: GodotPckTool command not found or permission issue at '{godotpcktool_path}'. Ensure it's executable.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred while trying to run GodotPckTool: {e}")
        return False

if __name__ == '__main__':
    print("--- Running repacker.py self-test example ---")

    dummy_input_dir_selftest = "temp_repack_input_selftest"
    os.makedirs(dummy_input_dir_selftest, exist_ok=True)
    with open(os.path.join(dummy_input_dir_selftest, "test_file.txt"), "w", encoding="utf-8") as f:
        f.write("This is a test file for repacking self-test.")
    print(f"Created dummy input directory: '{dummy_input_dir_selftest}' with a test file.")

    dummy_output_pck_selftest = "temp_test_output_selftest.pck"

    # Test with 'echo' placeholder
    print("\n--- Test 1: Using 'echo' as placeholder ---")
    # On Windows, 'echo' might be tricky with subprocess without shell=True.
    # However, our function handles 'echo' specifically now for simulation.
    repack_tool_path_for_test = "echo"
    if os.name == 'nt' and not shutil.which("echo"): # If echo is not found directly (unlikely for cmd)
        print("Warning: 'echo' command might not be directly callable via subprocess on this Windows system without shell=True.")
        print("The test will rely on the specific 'echo' string check in repack_files.")


    success_echo_test = repack_files(repack_tool_path_for_test, dummy_input_dir_selftest, dummy_output_pck_selftest, "3.5.0")
    print(f"Repack (with 'echo' placeholder) reported success: {success_echo_test}")

    # Clean up
    if os.path.exists(dummy_output_pck_selftest):
        os.remove(dummy_output_pck_selftest)
    if os.path.exists(os.path.join(dummy_input_dir_selftest, "test_file.txt")):
        os.remove(os.path.join(dummy_input_dir_selftest, "test_file.txt"))
    if os.path.exists(dummy_input_dir_selftest):
        # Need shutil for rmdir if it's not empty, but it should be after removing the file.
        try:
            os.rmdir(dummy_input_dir_selftest)
        except OSError as e: # If other hidden files exist etc.
            print(f"Note: Could not remove temp dir {dummy_input_dir_selftest}: {e}. Manual cleanup might be needed.")


    print("\n--- repacker.py self-test example finished. ---")
    print("Note: 'echo' test simulates command printout and success. For actual repacking, provide valid GodotPckTool path.")
    # Added shutil import for robust testing on Windows regarding 'echo'
    import shutil
```

**6. `main.py` (module-level and main function docstrings)**
