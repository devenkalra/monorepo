import time
from google import genai
from google.genai import types
import json
'''
BatchJob(
  create_time=datetime.datetime(2025, 12, 9, 1, 13, 48, 133800, tzinfo=TzInfo(0)),
  display_name='My-Image-Analysis-Job',
  model='models/gemini-2.5-flash',
  name='batches/ul9nx0s0bh0m0nwk9cp5rneoue3jju3u8hxf',
  state=<JobState.JOB_STATE_PENDING: 'JOB_STATE_PENDING'>,
  update_time=datetime.datetime(2025, 12, 9, 1, 13, 48, 133800, tzinfo=TzInfo(0))
)
'''
# Assuming you have the job's name from the creation step
# Example: 'batches/o08hk76gv328ihxcssjsgwt3g6omtfysxi46'
JOB_NAME = 'batches/doekovmijbnaprif07gn33vydkj6vkpatwz7'
client = genai.Client(api_key="AIzaSyBrU4Xox5GFwSEBSdHeM81yit-8wx_qiQw")


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
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(file_content)

    print(f"Results saved locally to: {output_path}")

    # 4. Parse and display the results
    print("\n--- Parsed Results Snippet ---")
    for line in file_content.splitlines():
        try:
            # Each line is a JSON object corresponding to one request/response
            result = json.loads(line)

            key = result.get('key', 'N/A')

            # Navigate the nested JSON structure to find the generated text
            text = result.get('response', {}).get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get(
                'text', 'No text found')

            print(f"[{key}]: {text[:100]}...")  # Print the first 100 chars

        except json.JSONDecodeError:
            # This handles lines that might contain status/error messages instead of responses
            status = json.loads(line)
            print(
                f"[ERROR]: Key {status.get('key', 'N/A')} failed with status: {status.get('status', 'Unknown error')}")

def monitor_job(job_name):
    """Polls the job status until it succeeds or fails."""
    print(f"Polling status for job: {job_name}")

    while True:
        batch_job = client.batches.get(name=job_name)
        current_state = batch_job.state.name

        if current_state in ('JOB_STATE_SUCCEEDED', 'JOB_STATE_FAILED', 'JOB_STATE_CANCELLED'):
            print(f"Job finished with state: {current_state}")
            if current_state == 'JOB_STATE_FAILED':
                print(f"Error: {batch_job.error.message}")
            retrieve_results(batch_job, "output.jsonl")
            return batch_job

        print(f"Job not finished. Current state: {current_state}. Waiting 30 seconds...")
        time.sleep(30)
monitor_job(JOB_NAME)