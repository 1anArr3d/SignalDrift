"""
tts.py
Converts the final script text to speech.
Primary: edge-tts (Microsoft Edge neural TTS — free, no API key, Python 3.13 compatible)
Fallback: ElevenLabs API

Output: MP3 file at output_path, plus word-level timing data (list of dicts)
used by caption_burner for kinetic caption sync.

Word timing format:
[
  {"word": "Why", "start": 0.0, "end": 0.35},
  ...
]
"""

import asyncio
import os
import re
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Script assembly
# ---------------------------------------------------------------------------

def assemble_narration(script: dict) -> str:
    """Join script fields in narration order. CTA excluded from audio."""
    parts = [
        script.get("hook", ""),
        script.get("body", ""),
        script.get("theories", ""),
        script.get("counterargument_acknowledgment", ""),
        script.get("conclusion", ""),
        script.get("engagement_question", ""),
    ]
    return " ".join(p for p in parts if p).strip()


# ---------------------------------------------------------------------------
# edge-tts primary
# ---------------------------------------------------------------------------

def _parse_vtt_timings(vtt_content: str) -> list[dict]:
    """
    Parse word-level timings from edge-tts subtitle output.
    Handles both WebVTT and SRT formats (edge-tts >= 7.0 uses SRT via get_srt()).
    """
    timings = []
    lines = vtt_content.strip().splitlines()
    i = 0

    def to_sec(h, m, s):
        return int(h) * 3600 + int(m) * 60 + float(s.replace(",", "."))

    while i < len(lines):
        line = lines[i].strip()
        ts_match = re.match(
            r"(\d+):(\d+):(\d+[.,]\d+)\s+-->\s+(\d+):(\d+):(\d+[.,]\d+)", line
        )
        if ts_match:
            start = to_sec(ts_match.group(1), ts_match.group(2), ts_match.group(3))
            end   = to_sec(ts_match.group(4), ts_match.group(5), ts_match.group(6))
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines):
                word = lines[i].strip()
                if word and word not in ("WEBVTT",) and not word.isdigit():
                    timings.append({"word": word, "start": round(start, 3), "end": round(end, 3)})
        i += 1
    return timings


async def _edge_synthesise_async(text: str, audio_path: str, vtt_path: str, rate: str = "+0%") -> None:
    import edge_tts
    voice     = _pick_voice()
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    submaker    = edge_tts.SubMaker()

    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    with open(vtt_path, "w", encoding="utf-8") as vtt_file:
        subs = submaker.get_srt() if hasattr(submaker, "get_srt") else submaker.get_subs()
        vtt_file.write(subs)


def _pick_voice() -> str:
    """Pick a random narrator voice. Called per synthesis so each video varies."""
    return random.choice([
        "en-GB-RyanNeural",        # British, investigative
        "en-US-EricNeural",        # American, warm
        "en-US-ChristopherNeural", # American, deep
    ])


def _run_edge_tts(text: str, output_path: str, rate: str = "+0%") -> list[dict]:
    """Synthesise with edge-tts and return word timings (Whisper-aligned where possible)."""
    vtt_path = output_path.replace(".mp3", ".vtt").replace(".wav", ".vtt")
    if not vtt_path.endswith(".vtt"):
        vtt_path += ".vtt"

    asyncio.run(_edge_synthesise_async(text, output_path, vtt_path, rate=rate))

    with open(vtt_path, encoding="utf-8") as f:
        vtt_content = f.read()

    try:
        os.remove(vtt_path)
    except OSError:
        pass

    # Priority 1: Whisper — reads actual audio waveform, captures real pauses
    timings = _whisper_align_timings(output_path)
    if timings:
        return timings

    # Priority 2: edge-tts VTT word boundaries
    timings = _parse_vtt_timings(vtt_content)
    if not timings:
        return _estimate_word_timings(text, output_path)

    # Scale VTT timings to match actual audio duration (edge-tts offsets run short)
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", output_path],
            capture_output=True, text=True,
        )
        audio_dur = float(r.stdout.strip())
        last_end  = timings[-1]["end"]
        if last_end > 0 and abs(audio_dur - last_end) > 0.5:
            scale = audio_dur / last_end
            for t in timings:
                t["start"] = round(t["start"] * scale, 3)
                t["end"]   = round(t["end"]   * scale, 3)
            print(f"[tts] Timing scaled {scale:.3f}x ({last_end:.1f}s → {audio_dur:.1f}s, {len(timings)} words)")
        else:
            print(f"[tts] Timing OK: {last_end:.1f}s / {audio_dur:.1f}s ({len(timings)} words)")
    except Exception:
        pass

    return timings


def _whisper_align_timings(audio_path: str) -> list[dict]:
    """
    Post-process the generated audio through OpenAI Whisper to get word-level
    timestamps that perfectly reflect actual speech — including pauses and
    speed variations.

    Cost: ~$0.006/min (~$0.01 per video).
    """
    import openai
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return []
    client = openai.OpenAI(api_key=api_key)
    try:
        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )
        words = getattr(result, "words", None) or []
        if not words:
            return []
        timings = [
            {"word": w.word.strip(), "start": w.start, "end": w.end}
            for w in words if w.word.strip()
        ]
        print(f"[tts] Whisper alignment: {len(timings)} words synced to actual audio")
        return timings
    except Exception as e:
        print(f"[tts] Whisper alignment failed ({e}) — falling back")
        return []


def _estimate_word_timings(text: str, audio_path: str) -> list[dict]:
    """Uniform last-resort fallback — only used if both Whisper and VTT fail."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True,
        )
        duration = float(r.stdout.strip())
    except Exception:
        duration = 75.0
    print(f"[tts] Using estimated timings over {duration:.1f}s (last resort fallback)")

    words   = text.split()
    per_word = duration / len(words) if words else 1.0
    t = 0.0
    timings = []
    for word in words:
        timings.append({"word": word, "start": round(t, 3), "end": round(t + per_word, 3)})
        t += per_word
    return timings


# ---------------------------------------------------------------------------
# ElevenLabs fallback
# ---------------------------------------------------------------------------

def _run_elevenlabs(text: str, output_path: str) -> list[dict]:
    from elevenlabs.client import ElevenLabs

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise EnvironmentError("ELEVENLABS_API_KEY not set in environment.")

    client   = ElevenLabs(api_key=api_key)
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    response    = client.text_to_speech.convert_with_timestamps(
        voice_id=voice_id,
        text=text,
        model_id="eleven_monolingual_v1",
    )
    audio_bytes = b"".join(response.audio_stream)
    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    if hasattr(response, "alignment") and response.alignment:
        return [
            {"word": item.word, "start": item.start, "end": item.end}
            for item in response.alignment.words
        ]
    return _estimate_word_timings(text, output_path)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

import random

def synthesise(script: dict, output_path: str, config: dict) -> dict:
    """
    Convert the script dict to an audio file with word timing data.

    Returns:
        Dict with 'wav_path' and 'word_timings'.
    """
    engine = config["forge"]["tts_engine"]
    text   = assemble_narration(script)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if engine == "edge":
        if output_path.endswith(".wav"):
            output_path = output_path[:-4] + ".mp3"
        rate = config["forge"].get("tts_rate", "+0%")
        try:
            word_timings = _run_edge_tts(text, output_path, rate=rate)
            print(f"[tts] edge-tts synthesis complete: {output_path}")
        except Exception as e:
            print(f"[tts] edge-tts failed ({e}), trying ElevenLabs fallback.")
            if os.environ.get("ELEVENLABS_API_KEY"):
                word_timings = _run_elevenlabs(text, output_path)
                print(f"[tts] ElevenLabs synthesis complete: {output_path}")
            else:
                print("[tts] No ElevenLabs key — using estimated timings.")
                word_timings = _estimate_word_timings(text, output_path)

    elif engine == "elevenlabs":
        word_timings = _run_elevenlabs(text, output_path)
        print(f"[tts] ElevenLabs synthesis complete: {output_path}")

    else:
        raise ValueError(f"Unknown TTS engine: '{engine}'. Use 'edge' or 'elevenlabs'.")

    return {"wav_path": output_path, "word_timings": word_timings}
