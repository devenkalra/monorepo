# --- SUBMITTING THE BATCH JOB (Run this separately) ---
from google import genai
# Replace with the actual URI returned by the previous script
JSONL_FILE_URI = "files/ze9axzp5qp17"
client = genai.Client(api_key="AIzaSyBrU4Xox5GFwSEBSdHeM81yit-8wx_qiQw")
print(f"Submitting batch job using source: {JSONL_FILE_URI}")

batch_job = client.batches.create(
    model='gemini-2.5-flash', # Or 'gemini-2.5-pro' for more complex analysis
    src=JSONL_FILE_URI,
    config={
        'display_name': 'My-Recursive-File-Analysis'
    }
)

print(f"Batch Job created: {batch_job.name}")
print("Monitor the status of this job until it SUCCEEDED.")