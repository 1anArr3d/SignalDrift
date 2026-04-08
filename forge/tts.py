import os
from openai import OpenAI
import stable_whisper
from dotenv import load_dotenv

load_dotenv()

def run(script_text: str, output_path: str, config: dict) -> dict:
    """
    Generates audio via OpenAI TTS and aligns words using stable-whisper.
    """
    print(f"[tts] Generating audio for script ({len(script_text.split())} words)...")
    
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    tts_cfg = config.get("tts", {})

    # 1. Generate Audio
    response = client.audio.speech.create(
        model=tts_cfg.get("model", "tts-1"),
        voice=tts_cfg.get("voice", "shimmer"),
        input=script_text
    )
    response.stream_to_file(output_path)

    # 2. Align Timings (Stable-Whisper)
    # We use 'base' because it's fast and accurate enough for captions
    print("[tts] Aligning subtitles...")
    model = stable_whisper.load_model('base')
    result = model.align(output_path, script_text, language='en')
    
    # Flatten the result into a simple list of word timings for the composer
    word_timings = []
    for segment in result.segments:
        for word in segment.words:
            word_timings.append({
                "word": word.word,
                "start": word.start,
                "end": word.end
            })

    return {
        "wav_path": output_path,
        "word_timings": word_timings
    }