import os
from pytube import Playlist
from youtube_transcript_api import YouTubeTranscriptApi
from slugify import slugify
from openai import OpenAI
from pytube import Playlist, YouTube


OPENAIKEY=os.getenv("OPENAIKEY")
client = OpenAI(api_key=OPENAIKEY)
from youtube_transcript_api import YouTubeTranscriptApi

OUTPUT_DIR = "transcripts"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def clean_transcript_with_chatgpt(title, transcript):
    prompt = f"""
You are an editor.

Clean and rewrite the following YouTube transcript into clear, readable prose.
- Remove filler words
- Fix grammar
- Add paragraph breaks
- Preserve original meaning
- Do NOT summarize

Title: {title}

Transcript:
{transcript}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You clean and format transcripts."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )

    return response.choices[0].message.content.strip()


def get_video_id(url):
    return url.split("v=")[1].split("&")[0]



from youtube_transcript_api import YouTubeTranscriptApi

def fetch_transcript(video_id):
    transcript = YouTubeTranscriptApi.get_transcript(video_id)
    return " ".join(item["text"] for item in transcript)



def process_playlist(playlist_url):
    playlist = Playlist(playlist_url)

    for video_url in playlist.video_urls:
        try:
            video_id = get_video_id(video_url)
            title = playlist.title  # fallback

            print(f"Processing: {title}")

            raw_transcript = fetch_transcript(video_id)
            cleaned = clean_transcript_with_chatgpt(title, raw_transcript)

            filename = slugify(title) + ".md"
            path = os.path.join(OUTPUT_DIR, filename)

            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n{cleaned}")

        except Exception as e:
            print(f"Skipping video: {video_url} → {e}")


if __name__ == "__main__":
    playlist_url = "https://www.youtube.com/watch?v=ugnJtaTRS38&list=PLsmceK7t6HVoIzJ3zwnazxOKsVYrpgcgL"
    process_playlist(playlist_url)
