from google import genai
import os



# --- Configuration ---
# Your local JSONL file path
JSONL_FILE_PATH = "batch_requests.jsonl"

# Initialize the client (assumes GEMINI_API_KEY is set in your environment)
try:
    client = genai.Client(api_key="AIzaSyBrU4Xox5GFwSEBSdHeM81yit-8wx_qiQw")
except Exception as e:
    print("Error initializing client. Ensure GEMINI_API_KEY is set.")
    print(e)
    exit()


def upload_jsonl_file_safe(file_path: str):
    """
    Uploads the JSONL request file to the Gemini Files API using only guaranteed parameters.
    """
    if not os.path.exists(file_path):
        print(f"Error: Input file not found at '{file_path}'")
        return None

    print(f"--- Starting upload of {file_path} ---")
    mime_type = "application/jsonl"
    try:
        # **STRICTEST UPLOAD:** Only the required 'file' argument.
        uploaded_file = client.files.upload(
            file=file_path,
            config={
                'mime_type': "application/jsonl"  # Passed via config to avoid the TypeError
            }
        )

        print("\n✅ Upload Successful!")
        # **CRUCIAL CHANGE:** Removed uploaded_file.display_name
        print(f"File URI (Source for Batch Job): {uploaded_file.name}")
        print(f"Size: {uploaded_file.size_bytes / 1024 ** 2:.2f} MB")

        return uploaded_file

    except Exception as e:
        # Check if the error is related to display_name (though it shouldn't be now)
        if 'display_name' in str(e):
            print(
                "\n❌ Upload Failed! The error is still related to 'display_name'. This suggests an issue with the SDK version or environment.")
        else:
            print(f"\n❌ Upload Failed! Error: {e}")
        return None

def submit_job(uri):
    batch_job = client.batches.create(
        model='gemini-2.5-flash',
        src=uri,
        config={
            'display_name': 'My-Image-Analysis-Job'
        }
    )
    return batch_job



if __name__ == "__main__":
    uploaded_jsonl = upload_jsonl_file_safe(JSONL_FILE_PATH)
    file_uri = uploaded_jsonl.name
    batch_job = submit_job(file_uri)

    if uploaded_jsonl:
        print("\n--- Next Step ---")
        print("Use the 'File URI' in the 'src' parameter of the client.batches.create() call.")
        print(batch_job.name)