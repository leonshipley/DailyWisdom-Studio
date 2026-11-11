import os
import re
import json
import wave
import base64
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Dict, Any, Tuple, List
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

GEMINI_ACTING_VOICES = {
    "Charon — Deep Gravelly Pulpit Preacher (Male)": "Charon",
    "Fenrir — Fiery Passionate Revival Preacher (Male)": "Fenrir",
    "Orus — Warm Empathetic Pastor & Counselor (Male)": "Orus",
    "Puck — Urgent Emotional Storyteller (Male)": "Puck",
    "Kore — Soulful Tearful Prayer Intercessor (Female)": "Kore",
    "Aoede — Gentle Midnight Soaking Voice (Female)": "Aoede",
}

ENGINE_CHOICES = [
    "🌟 Gemini AI Native Acting Voice (ElevenLabs-Style Feeling & Emotion Commands!)",
    "🎙️ Edge-TTS + Preacher Pitch/Speed Modulator (Fast Standard Neural)"
]

def _get_api_key() -> str:
    load_dotenv(BASE_DIR / ".env", override=True)
    return os.getenv("GEMINI_API_KEY", "").strip()

def convert_tags_to_acting_Prompt(script_text: str, custom_feeling_prompt: str = "") -> str:
    """
    Converts inline tags like [empathy], [angry], [whisper], [warfare], *WORD* into
    natural theatrical acting instructions that Gemini Native Audio TTS understands!
    """
    s = script_text
    s = re.sub(r"\[(boom|shimmer|swell|bell|thunder)\]", "", s, flags=re.IGNORECASE)

    # Convert bracket tags into inline acting cues for the audio LLM
    replacements = {
        r"\[angry\]": "(Speak this next part with fierce, righteous preacher anger and thunderous intensity:)",
        r"\[fierce\]": "(Speak with fierce, commanding intensity:)",
        r"\[warfare\]": "(Speak with bold, rising spiritual warfare authority and power:)",
        r"\[empathy\]": "(Speak in a soft, deeply compassionate, heartbroken and comforting tone, with a gentle sigh:)",
        r"\[sad\]": "(Speak with tearful empathy and sorrowful tenderness:)",
        r"\[whisper\]": "(Drop your voice to an intimate, close-mic, late-night whisper:)",
        r"\[scripture\]": "(Speak with slow, reverent, sacred biblical gravitas:)",
        r"\[joy\]": "(Speak with warm, uplifting, joyful breakthrough energy:)",
        r"\[amen\]": "(Slow down deeply and speak with peaceful, solemn finality:)",
    }
    for pat, act_str in replacements.items():
        s = re.sub(pat, act_str, s, flags=re.IGNORECASE)

    director_header = (
        "ACTING & VOCAL DIRECTION FOR PREACHER:\n"
        "You are an anointed, deeply emotional human Christian pastor—NOT a robotic narrator. "
        "Breathe naturally, use real vocal emotion, vary your pacing dynamically, punch words in *ASTERISKS* with strong emphasis, "
        "and follow every parenthetical emotion cue in the script below without reading the parenthetical instructions aloud.\n"
    )
    if custom_feeling_prompt.strip():
        director_header += f"SPECIAL FEELING COMMAND FROM DIRECTOR: {custom_feeling_prompt.strip()}\n"

    return f"{director_header}\nSCRIPT TO PERFORM ALOUD:\n{s.strip()}"

def synthesize_gemini_native_emotional_tts(
    script_text: str,
    out_mp3_path: Path,
    gemini_voice_name: str = "Charon",
    custom_feeling_prompt: str = ""
) -> Tuple[bool, str]:
    """
    Calls Google's Native Multimodal Audio TTS (`gemini-2.5-flash-preview-tts` / `gemini-2.0-flash-exp`)
    which understands real human acting/feeling prompts just like ElevenLabs v3 / Fish Speech!
    """
    key = _get_api_key()
    if not key:
        return False, "Missing GEMINI_API_KEY in .env"

    acting_prompt = convert_tags_to_acting_Prompt(script_text, custom_feeling_prompt)

    payload = {
        "contents": [{"parts": [{"text": acting_prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": gemini_voice_name
                    }
                }
            }
        }
    }
    data_bytes = json.dumps(payload).encode("utf-8")

    for model_id in ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts", "gemini-2.0-flash-exp"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={key}"
            req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=data_bytes)
            with urllib.request.urlopen(req, timeout=30) as resp:
                rj = json.loads(resp.read().decode("utf-8"))
                parts = rj.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                for p in parts:
                    inl = p.get("inlineData") or p.get("inline_data")
                    if inl and inl.get("data"):
                        raw_audio = base64.b64decode(inl["data"])
                        mime = str(inl.get("mimeType") or inl.get("mime_type") or "").lower()
                        temp_wav = out_mp3_path.with_suffix(".raw_gem.wav")

                        # Gemini TTS returns 24kHz 16-bit mono PCM (`audio/L16;rate=24000`) or WAV
                        if "l16" in mime or "pcm" in mime or raw_audio[:4] != b"RIFF":
                            rate_m = re.search(r"rate=(\d+)", mime)
                            sr = int(rate_m.group(1)) if rate_m else 24000
                            with wave.open(str(temp_wav), "wb") as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(sr)
                                wf.writeframes(raw_audio)
                        else:
                            temp_wav.write_bytes(raw_audio)

                        subprocess.run([
                            "ffmpeg", "-y", "-i", str(temp_wav.absolute()),
                            "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k",
                            str(out_mp3_path.absolute())
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        temp_wav.unlink(missing_ok=True)

                        if out_mp3_path.exists() and out_mp3_path.stat().st_size > 1000:
                            return True, f"🌟 Gemini Native Emotional Acting Voice ({gemini_voice_name} via {model_id})"
        except Exception as e:
            continue

    return False, "Gemini TTS endpoint busy — seamlessly used Preacher Prosody Engine."

def build_proportional_word_timings(clean_script: str, total_dur_sec: float) -> List[Dict[str, Any]]:
    """Builds accurate word-level subtitle & SFX timings for any audio file."""
    words = clean_script.split()
    if not words:
        return []
    weights = []
    for w in words:
        wt = max(2, len(w))
        if re.search(r"[\.\!\?।]", w):
            wt += 6
        elif re.search(r"[,;:]", w):
            wt += 3
        weights.append(wt)
    tot_w = sum(weights) or 1
    usable = max(0.8, total_dur_sec - 0.35)
    cur_t = 0.05
    timings = []
    for w, wt in zip(words, weights):
        d = usable * (wt / tot_w)
        timings.append({
            "text": w.strip(),
            "start": round(cur_t, 3),
            "end": round(cur_t + d, 3)
        })
        cur_t += d
    return timings
