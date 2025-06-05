"""
Basic Godot PCK file unpacker.

This module provides functionality to unpack Godot Engine's .pck or .exe files
(when the .exe contains an embedded .pck). It is adapted from the
godot-unpacker.py script by tehskai (https://github.com/tehskai/godot-unpacker).

The main function `unpack_pck` attempts to identify PCK headers, read file
metadata, and extract the contained files to a specified output directory.
"""
import sys
import os
import pathlib
import mmap
import struct
import re

def append_to_filename(path, text):
    """
    Appends a text suffix to a filename before its extension.

    Args:
        path (str): The original file path.
        text (str): The text to append to the filename.

    Returns:
        str: The new path with the modified filename.
    """
    path_parts = os.path.splitext(path)
    return path_parts[0] + text + path_parts[1]

def unpack_container(data):
    """
    Attempts to identify and extract common asset types from a raw data blob.

    This function checks for magic bytes of common formats like WebP, PNG, JPG,
    and OGG that might be stored as raw data within Godot's .tex, .stex, or
    .oggstr files.

    Args:
        data (bytes): The raw byte data of the container file.

    Returns:
        list or bool: A list containing the detected file extension (e.g., ".webp")
                      and the extracted file data (bytes) if a known format is found.
                      Returns False otherwise.
    """
    # webp
    start = data.find(bytes.fromhex("52 49 46 46")) # RIFF
    if start >= 0 and data[start+8:start+12] == bytes.fromhex("57 45 42 50"): # WEBP
        size = int.from_bytes(data[start + 4:start + 8], byteorder="little")
        # Ensure size is reasonable, preventing huge allocations if data is corrupt
        if 0 <= start + 8 + size <= len(data):
            return [".webp", data[start:start + 8 + size]]

    # png
    start = data.find(bytes.fromhex("89 50 4E 47 0D 0A 1A 0A"))
    if start >= 0:
        end = data.find(bytes.fromhex("49 45 4E 44 AE 42 60 82")) # IEND
        if end >= 0 and 0 <= start <= end + 8 <= len(data) :
            return [".png", data[start:end + 8]]

    # jpg
    start = data.find(bytes.fromhex("FF D8 FF"))
    if start >= 0:
        end = data.find(bytes.fromhex("FF D9"))
        if end >= 0 and 0 <= start <= end + 2 <= len(data):
            return [".jpg", data[start:end + 2]]

    # ogg
    start = data.find(bytes.fromhex("4F 67 67 53")) # OggS
    if start >= 0:
        # OGG files don't have a simple end marker like PNG/JPG in their header.
        # The original script read until -4, assuming some footer.
        # This might be risky if the .oggstr is just raw ogg data without extra Godot footer.
        # For safety, we'll return from start if found, assuming it's mostly ogg data.
        # A more robust method would parse OGG pages to find the true end.
        return [".ogg", data[start:]] # Potentially read to end of data if no clear end marker

    return False

def unpack_pck(pck_file_path, output_dir_path, unpack_containers=True):
    """
    Unpacks a Godot .pck file or a .exe file with an embedded .pck.

    Args:
        pck_file_path (str): Path to the .pck or .exe file.
        output_dir_path (str): Directory where files will be extracted.
        unpack_containers (bool): If True, attempts to unpack known asset types
                                  from .tex, .stex, .oggstr files.

    Returns:
        list: A list of paths to the extracted files. Returns an empty list
              on failure or if no files are extracted.
    """
    magic = bytes.fromhex('47445043')  # GDPC
    file_list = []
    import_file_list = []
    extracted_files_paths = []

    resource_pack_file_name = pathlib.Path(pck_file_path).name

    if not os.path.exists(output_dir_path):
        try:
            os.makedirs(output_dir_path)
            print(f"Created output directory: {output_dir_path}")
        except OSError as e:
            print(f"Error creating output directory {output_dir_path}: {e}")
            return []

    try:
        with open(pck_file_path, 'r+b') as pck_file_handle:
            # Use mmap for efficient file reading
            f = mmap.mmap(pck_file_handle.fileno(), 0, access=mmap.ACCESS_READ)
    except FileNotFoundError:
        print(f"Error: PCK file not found at {pck_file_path}")
        return []
    except Exception as e:
        print(f"Error opening PCK file {pck_file_path}: {e}")
        return []

    pck_start_offset = 0
    # Check for standard PCK header
    if f.read(4) == magic:
        print(f"'{resource_pack_file_name}' identified as a Godot PCK resource pack.")
        f.seek(0)
    else: # Check for embedded PCK in EXE
        f.seek(-4, os.SEEK_END)
        if f.read(4) == magic:
            print(f"'{resource_pack_file_name}' identified as a self-contained Godot executable.")
            f.seek(-12, os.SEEK_END)
            pck_start_offset_from_end = int.from_bytes(f.read(8), byteorder="little")
            pck_start_offset = f.size() - pck_start_offset_from_end

            f.seek(pck_start_offset - 8) # Original script logic: f.seek(f.tell() - main_offset - 8)
                                         # which is equivalent to f.size() - 12 - 8 - main_offset
                                         # Let's use the direct pck_start_offset
            if f.read(4) == magic:
                f.seek(pck_start_offset - 8) # Corrected seek based on where magic was found
                print(f"  Embedded PCK header found at offset: {pck_start_offset-8}")
            else:
                f.close()
                print("Error: Embedded PCK header signature not found at expected offset.")
                return []
        else:
            f.close()
            print(f"Error: File '{resource_pack_file_name}' is not a recognized PCK or self-contained EXE.")
            return []

    # Read PCK headers
    # struct PCKHeader {
    #   uint32_t magic; // 0
    #   uint32_t version; // 4
    #   uint32_t major; // 8
    #   uint32_t minor; // 12
    #   uint32_t patch; // 16
    #   uint32_t reserved[16]; // 20
    #   uint32_t file_count; // 20 + 16*4 = 84
    # };
    try:
        f.seek(pck_start_offset) # Go to the start of the PCK data
        header_data = f.read(88) # Size of PCKHeader up to and including file_count
        if len(header_data) < 88:
            print("Error: Could not read full PCK header.")
            f.close()
            return []

        # "IIIII" for magic, version, major, minor, patch. Then 16I for reserved. Then I for file_count.
        # Total 5 + 16 + 1 = 22 integers.
        package_headers = struct.unpack_from("<22I", header_data) # Little-endian
        pck_version = package_headers[1]
        godot_version_major = package_headers[2]
        godot_version_minor = package_headers[3]
        file_count = package_headers[-1]
        print(f"  PCK Version: {pck_version}, Godot Version: {godot_version_major}.{godot_version_minor}")
        print(f"  File count: {file_count}")

        # Read file entries
        for _ in range(file_count):
            path_len_bytes = f.read(4)
            if len(path_len_bytes) < 4:
                print("Error: Could not read filepath length for a file entry.")
                break
            filepath_length = int.from_bytes(path_len_bytes, byteorder="little")

            # Ensure filepath_length is reasonable to prevent excessive memory allocation
            # Max path length in Godot is typically around 1024 or 2048.
            # A very large length here likely indicates corruption or an unsupported PCK version feature.
            if filepath_length > 8192: # Arbitrary sanity check for path length
                print(f"Warning: Encountered unusually long filepath length ({filepath_length}). Skipping entry. PCK might be corrupt or unsupported.")
                # Attempt to seek past where this entry would have been if it's just this one entry.
                # This is speculative. A real skip would need to know how much data this entry claims.
                # For now, it's safer to stop processing if such an anomaly occurs.
                break # Stop processing further entries

            # Format: path string (UTF-8), offset (uint64), size (uint64), md5 (16 bytes)
            entry_header_format = f"<{filepath_length}sQQ16B"
            entry_header_size = struct.calcsize(entry_header_format)
            entry_data_bytes = f.read(entry_header_size)

            if len(entry_data_bytes) < entry_header_size:
                print("Error: Could not read full file entry header.")
                break

            file_info = struct.unpack_from(entry_header_format, entry_data_bytes)

            path_bytes = file_info[0]
            offset = file_info[1] + pck_start_offset # Offset is relative to PCK start
            size = file_info[2]
            # md5_hash_bytes = file_info[3:] # This would be a tuple of 16 bytes

            try:
                # Paths are stored as res://path/to/file.ext or user://path
                # We remove the "res://" or "user://" prefix.
                path_str = path_bytes.decode("utf-8").replace("res://", "").replace("user://", "")
            except UnicodeDecodeError:
                print(f"Warning: Could not decode path for an entry (bytes: {path_bytes[:64]}...). Skipping.")
                continue # Skip this file entry

            file_list.append({'path': path_str, 'offset': offset, 'size': size})

    except struct.error as e:
        print(f"Error unpacking PCK header or file entries: {e}. The PCK file might be corrupt or in an unsupported format.")
        f.close()
        return []
    except Exception as e: # Catch-all for other unexpected errors during header processing
        print(f"An unexpected error occurred during PCK metadata reading: {e}")
        f.close()
        return []


    print(f"\nUnpacking {len(file_list)} files from '{resource_pack_file_name}'...")
    for packed_file_info in file_list:
        # Construct full output path for the file
        # Ensure path components are valid for the OS, and handle potential leading slashes from path_str
        # os.path.join correctly handles joining path components.
        # lstrip('/\\') ensures that if path_str accidentally starts with a slash, it doesn't become absolute.
        current_file_output_path = os.path.join(output_dir_path, packed_file_info['path'].lstrip('/\\'))

        # Create directory for the file if it doesn't exist
        current_file_dir = os.path.dirname(current_file_output_path)
        if not os.path.exists(current_file_dir):
            try:
                pathlib.Path(current_file_dir).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"Warning: Could not create directory {current_file_dir} for {packed_file_info['path']}: {e}. Skipping file.")
                continue

        try:
            f.seek(packed_file_info['offset'])
            file_data = f.read(packed_file_info['size'])
        except Exception as e:
            print(f"Error reading data for {packed_file_info['path']} (offset: {packed_file_info['offset']}, size: {packed_file_info['size']}): {e}. Skipping.")
            continue

        # Handle .import files and potential container unpacking
        file_name_full = os.path.basename(packed_file_info['path'])
        _, file_extension = os.path.splitext(file_name_full)

        if unpack_containers:
            if file_extension == '.import':
                try:
                    import_file_data_str = file_data.decode("utf-8")
                    # Example: path="res://path/to/imported_asset.png"
                    # Example: source_file="res://original_assets/image.png"
                    import_path_match = re.search(r'path\s*=\s*"([^"]+)"', import_file_data_str)
                    import_source_match = re.search(r'source_file\s*=\s*"([^"]+)"', import_file_data_str)

                    if import_path_match and import_source_match:
                        # Normalize paths by removing res:// or user:// and leading slashes
                        imported_asset_path = import_path_match.group(1).replace("res://", "").replace("user://", "").lstrip('/\\')
                        original_source_path = import_source_match.group(1).replace("res://", "").replace("user://", "").lstrip('/\\')
                        import_file_list.append({"imported_path": imported_asset_path, "original_source": original_source_path})
                except UnicodeDecodeError:
                    print(f"Warning: Could not decode .import file {file_name_full} as UTF-8. Import processing skipped.")

            # Attempt to unpack common Godot container types
            if file_extension in ['.stex', '.tex', '.oggstr']: # .ctex for 3D compressed textures might also be relevant
                unpacked_asset = unpack_container(file_data)
                if isinstance(unpacked_asset, list) and len(unpacked_asset) == 2:
                    new_extension, new_data = unpacked_asset
                    # Potentially change current_file_output_path to reflect new extension
                    # e.g., current_file_output_path = os.path.splitext(current_file_output_path)[0] + new_extension
                    file_data = new_data # Use the unpacked data
                    print(f"  Unpacked '{file_name_full}' to '{new_extension}' format.")


        # Write the file (either original or unpacked data)
        try:
            with open(current_file_output_path, "w+b") as output_file:
                output_file.write(file_data)
            extracted_files_paths.append(current_file_output_path)
        except Exception as e:
            print(f"Error writing file {current_file_output_path}: {e}")

    f.close() # Close the mmap object

    # Rename imported files to their original source names if they exist
    # This helps in having a more source-like project structure after unpacking.
    if unpack_containers and import_file_list: # Only if container unpacking was enabled (as .import files are tied to it)
        print("\nProcessing .import file renames...")
        for import_info in import_file_list:
            # Path of the .import file's corresponding asset (e.g., texture.png.import -> texture.png)
            path_of_imported_asset = os.path.join(output_dir_path, import_info["imported_path"])
            # Desired new path based on source_file attribute in .import
            target_path_for_asset = os.path.join(output_dir_path, import_info["original_source"])

            if os.path.exists(path_of_imported_asset):
                try:
                    # Ensure target directory exists for the rename
                    os.makedirs(os.path.dirname(target_path_for_asset), exist_ok=True)

                    # If the target path (original_source) already exists, append "_imported"
                    # to avoid overwriting (e.g. if both original source and imported version were somehow packed).
                    if os.path.exists(target_path_for_asset) and path_of_imported_asset != target_path_for_asset :
                        target_path_for_asset = append_to_filename(target_path_for_asset, "_restored")

                    os.rename(path_of_imported_asset, target_path_for_asset)
                    print(f"  Renamed '{path_of_imported_asset}' to '{target_path_for_asset}' (based on .import)")
                    # Update extracted_files_paths list if the file was moved
                    if path_of_imported_asset in extracted_files_paths:
                        extracted_files_paths.remove(path_of_imported_asset)
                        extracted_files_paths.append(target_path_for_asset)
                except Exception as e:
                    print(f"Error renaming imported file {path_of_imported_asset} to {target_path_for_asset}: {e}")
            # else:
                # print(f"Warning: Asset file {path_of_imported_asset} mentioned in .import not found for renaming.")

    print(f"\nUnpacking finished. {len(extracted_files_paths)} files extracted to '{output_dir_path}'.")
    return extracted_files_paths

if __name__ == "__main__":
    # This part is for direct script execution testing, not used by main.py
    if len(sys.argv) < 3:
        print("Usage for direct testing: python unpacker.py <pck_file_path> <output_directory> [--no-containers]")
        sys.exit(1)

    _pck_path = sys.argv[1]
    _out_dir = sys.argv[2]
    _unpack_containers = True
    if len(sys.argv) > 3 and sys.argv[3] == '--no-containers':
        _unpack_containers = False

    print(f"Testing unpacker with PCK: '{_pck_path}', Output: '{_out_dir}', Unpack Containers: {_unpack_containers}")
    extracted = unpack_pck(_pck_path, _out_dir, _unpack_containers)
    if extracted:
        print(f"\nSuccessfully extracted {len(extracted)} files.")
        # print("First few files:")
        # for i, f_path in enumerate(extracted[:5]):
        #     print(f"  {f_path}")
    else:
        print("\nExtraction failed or no files were extracted.")

```

**2. `text_extractor.py`**
