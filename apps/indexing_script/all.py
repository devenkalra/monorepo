import os
import json
import time
from google import genai
from google.genai import types
import uuid

ROOT_DIR = "/mnt/photo/0 tmp/"
# 1. Setup
IMAGE_DIRECTORY = "/mnt/photo/0 tmp/"  # Folder containing your local images
BATCH_FILE_NAME = "my_batch_requests.jsonl"
MODEL_ID = "gemini-2.5-flash"

client = genai.Client(api_key="AIzaSyBrU4Xox5GFwSEBSdHeM81yit-8wx_qiQw")


def upload_images_and_create_requests(directory):
    batch_requests = []

    print(f"Scanning directory: {directory}")
    for filename in os.listdir(directory):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            file_path = os.path.join(directory, filename)

            # A. Upload the local image to the Gemini File API
            print(f"Uploading {filename}...")
            file_ref = client.files.upload(file=file_path)

            # Wait for processing (important for large images/videos)
            while file_ref.state.name == "PROCESSING":
                print("Processing...")
                time.sleep(2)
                file_ref = client.files.get(name=file_ref.name)

            if file_ref.state.name == "FAILED":
                print(f"Failed to process {filename}")
                continue

            # B. Create a request object referencing the uploaded file URI
            # Note: The 'name' usually works as the reference URI in the SDK
            key = uuid.uuid4().hex
            def remove_nls(s):
                s = s.replace("  ", " ")
                lines = s.split("\n")
                return (" ".join([line.strip() for line in lines]))

            request_entry = {
                # Move custom_id here so it's tracked in the final output file
                "key": f"req-{key}",
                "request": {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {"fileData": {"mimeType": file_ref.mime_type, "fileUri": file_ref.uri}},
                                {"text": remove_nls("""
                                You are a computer vision system.
                                You are a computer vision system. Describe this image in detail. Detect all human faces with as tightly as possible, do not include too much besides the face, and output the coordinates of faces. Detect location and output location"
                                    Task:
                                    Detect all human faces in the provided image.
                                    
                                    Output format:
                                    Return ONLY valid JSON in this exact schema:
                                    
                                    {
                                      "image_width": number,
                                      "image_height": number,
                                      "description": string,
                                      "faces": [
                                        {
                                          "face_index": number,
                                          "confidence": number,
                                          "box": {
                                            "left": number,
                                            "top": number,
                                            "right": number,
                                            "bottom": number
                                          }
                                        }
                                      ]
                                    }
                                    
                                    Rules:
                                    - Coordinates must be in absolute pixels.
                                    - (x, y) is the top-left corner.
                                    - Do NOT include any text outside the JSON.
                                    """)
                                 }
                            ]
                        }
                    ]
                }
            }

            batch_requests.append(request_entry)
            print(f"Prepared request for {filename}")
            break

    return batch_requests


def retrieve_results(completed_job, output_path: str):
    """Downloads the output JSONL file and processes the results."""

    # 1. Get the URI of the results file
    result_file_name = completed_job.dest.file_name

    if not result_file_name:
        print("Error: Job succeeded but no output file name was found.")
        return

    print(f"\n--- Downloading results from {result_file_name} ---")

    # 2. Download the file content
    file_content_bytes = client.files.download(file=result_file_name)
    file_content = file_content_bytes.decode('utf-8')

    # 3. Save the raw output to a local file


    # 4. Parse and display the results
    print("\n--- Parsed Results Snippet ---")
    with open(output_path, 'w', encoding='utf-8') as f:
        for line in file_content.splitlines():
            try:
                # Each line is a JSON object corresponding to one request/response
                result = json.loads(line)

                key = result.get('key', 'N/A')

                # Navigate the nested JSON structure to find the generated text
                text = result.get('response', {}).get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get(
                    'text', 'No text found')

                print(f"[{key}]: {text[:100]}...")  # Print the first 100 chars
                text = text.replace("```json","").replace("```","")
                result["response"]["output"] = json.loads(text)

                output = json.dumps(result)
                f.write(output)

                print(f"Results saved locally to: {output_path}")

            except json.JSONDecodeError:
                # This handles lines that might contain status/error messages instead of responses
                status = json.loads(line)
                print(
                    f"[ERROR]: Key {status.get('key', 'N/A')} failed with status: {status.get('status', 'Unknown error')}")


def monitor_job(job_name):
    """Polls the job status until it succeeds or fails."""
    print(f"Polling status for job: {job_name}")

    while True:
        print(f"Waiting 30 seconds...")

        time.sleep(30)
        batch_job = client.batches.get(name=job_name)
        current_state = batch_job.state.name

        if current_state in ('JOB_STATE_SUCCEEDED', 'JOB_STATE_FAILED', 'JOB_STATE_CANCELLED'):
            print(f"Job finished with state: {current_state}")
            if current_state == 'JOB_STATE_FAILED':
                print(f"Error: {batch_job.error.message}")
            retrieve_results(batch_job, "output.jsonl")
            return batch_job


# 2. Main Execution
try:
    # Generate the list of requests
    requests = upload_images_and_create_requests(IMAGE_DIRECTORY)

    if not requests:
        print("No valid images found or prepared.")
        exit()

    # 3. Save requests to a local JSONL file
    with open(BATCH_FILE_NAME, "w") as f:
        for req in requests:
            f.write(json.dumps(req) + "\n")

    # 4. Upload the Batch JSONL file itself
    print(f"Uploading batch file: {BATCH_FILE_NAME}")
    batch_file_ref = client.files.upload(file=BATCH_FILE_NAME, config={
        'mime_type': "application/jsonl"  # Passed via config to avoid the TypeError
    })

    # 5. Submit the Batch Job
    print("Submitting batch job...")
    batch_job = client.batches.create(
        model=MODEL_ID,
        src=batch_file_ref.name,
        config={
            'display_name': "image-analysis-job",
        },
    )

    print(f"Batch Job Created!")
    print(f"Job Name: {batch_job.name}")
    print(f"Status: {batch_job.state}")
    print("Use 'client.batches.get(name=JOB_NAME)' to check status.")

    monitor_job(batch_job.name)
except Exception as e:
    print(f"An error occurred: {e}")
