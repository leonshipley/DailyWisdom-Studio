# analyzer.py
import json
import time
from pathlib import Path
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

class BookClip(BaseModel):
    title: str = Field(description="Catchy, high-CTR YouTube Short title under 60 chars")
    start_time: str = Field(description="Start timestamp HH:MM:SS or MM:SS")
    end_time: str = Field(description="End timestamp HH:MM:SS or MM:SS")
    book_title: str = Field(description="The exact title of the book discussed in this clip")
    book_author: str = Field(description="The author of the book (or 'Unknown')")
    hook_caption: str = Field(description="1 punchy sentence summarizing the insight")
    hashtags: list[str] = Field(description="5 viral tags, e.g., ['#Wisdom', '#Books', '#Shorts']")

class AnalysisResponse(BaseModel):
    clips: list[BookClip]

def analyze_video_for_books(client: genai.Client, video_path: Path, max_clips: int = 2) -> list[BookClip]:
    print("\n🧠 [Brain] Uploading video to Gemini File API...")
    video_file = client.files.upload(file=str(video_path))

    while video_file.state.name == "PROCESSING":
        time.sleep(3)
        video_file = client.files.get(name=video_file.name)

    if video_file.state.name == "FAILED":
        raise RuntimeError("Gemini failed to process the video.")

    print("🧠 [Brain] Identifying book recommendations and high-retention moments...")
    prompt = f"""
    You are an elite short-form video editor for a book wisdom channel.
    Analyze this video and extract up to {max_clips} viral moments where a specific book, philosophy, or mental model is explained.

    Requirements:
    - Clip length: strictly 30 to 58 seconds.
    - Identify the EXACT book title and author being discussed.
    - Start right at the punchy hook; stop cleanly after the lesson is complete.
    """

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[video_file, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AnalysisResponse,
            temperature=0.2,
        ),
    )

    try:
        client.files.delete(name=video_file.name)
    except Exception:
        pass

    data = json.loads(response.text)
    return [BookClip(**item) for item in data.get("clips", [])]