import os
import json
from pathlib import Path
from google import genai
from typing import List, Tuple

# --- Configuration ---
# Initialize the client (assumes GEMINI_API_KEY is set as an environment variable)
client = genai.Client(api_key="AIzaSyBrU4Xox5GFwSEBSdHeM81yit-8wx_qiQw")

# The root directory to search recursively
ROOT_DIR = "/mnt/photo/0 tmp/"
# The name of the output JSONL file
OUTPUT_JSONL_FILE = "batch_requests.jsonl"
# The prompt you want to apply to every file
DEFAULT_PROMPT = "Provide a summary of this document, identifying the key entities and dates."
# List of file extensions to IGNORE (e.g., system files, code, etc.)
EXCLUDE_EXTENSIONS = ['.py', '.json', '.txt', '.log', '.ini']


def get_files_recursive(root_dir: str) -> List[Path]:
    """Recursively finds all files in a directory, excluding specified extensions."""
    files = []
    # Use Path.rglob() for simple, clean recursive file listing
    for path in Path(root_dir).rglob('*'):
        if path.is_file() and path.suffix.lower() not in EXCLUDE_EXTENSIONS:
            files.append(path)
    return files


def upload_and_create_batch_jsonl(files: List[Path], output_path: str):
    """
    Uploads files and creates the batch JSONL file.

    Returns a tuple of (File object of the JSONL file, uploaded file count).
    """
    uploaded_files = []
    batch_requests = []

    print(f"--- Starting File Uploads ---")

    # 1. UPLOAD ALL FILES AND COLLECT URIs
    for i, file_path in enumerate(files):
        print(f"[{i + 1}/{len(files)}] Uploading: {file_path.name}...", end=' ', flush=True)
        try:
            # Upload the file to the Files API
            uploaded_file = client.files.upload(
                file=str(file_path)
            )
            uploaded_files.append(uploaded_file)
            print(f"SUCCESS (URI: {uploaded_file.name})")

            # 2. CREATE THE BATCH REQUEST OBJECT
            request_key = f"request-{uploaded_file.name.split('/')[-1]}"

            # Use the format required for the Batch API
            request_object = {
                "key": request_key,
                "request": {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "fileData": {
                                        "mimeType": uploaded_file.mime_type,
                                        "fileUri": uploaded_file.name  # Use the file resource name (e.g., files/xyz123)
                                    }
                                },
                                {
                                    "text": DEFAULT_PROMPT
                                }
                            ]
                        }
                    ]
                }
            }
            batch_requests.append(request_object)

        except Exception as e:
            print(f"FAILURE: {e}")
            continue

    # 3. WRITE ALL REQUESTS TO A LOCAL JSONL FILE
    print(f"\n--- Creating local {output_path} ---")
    with open(output_path, 'w') as f:
        for request in batch_requests:
            f.write(json.dumps(request) + '\n')

    print(f"Successfully created {output_path} with {len(batch_requests)} requests.")

    # 4. UPLOAD THE JSONL FILE FOR BATCH SUBMISSION
    print(f"--- Uploading JSONL manifest for batch job ---")
    mime_type = "application/jsonl"
    uploaded_jsonl = client.files.upload(file=output_path, config={
                'mime_type': mime_type  # Passed via config to avoid the TypeError
            })


    print(f"JSONL uploaded. Use this URI for the batch job: {uploaded_jsonl.name}")

    return uploaded_jsonl, len(batch_requests)


if __name__ == "__main__":
    if not os.path.isdir(ROOT_DIR):
        print(f"Error: Directory '{ROOT_DIR}' not found. Please create it and add files.")
    else:
        all_files = get_files_recursive(ROOT_DIR)

        if not all_files:
            print(f"No valid files found in '{ROOT_DIR}'.")
        else:
            uploaded_jsonl_file, num_requests = upload_and_create_batch_jsonl(all_files, OUTPUT_JSONL_FILE)

            print("\n==============================================")
            print("✅ Batch Preparation Complete! ✅")
            print(f"Total Requests Prepared: {num_requests}")
            print(f"JSONL File URI to use in Batch API: {uploaded_jsonl_file.name}")
            print("==============================================")