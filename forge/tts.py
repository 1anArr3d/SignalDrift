import os
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

load_dotenv()

def run(script_text: str, output_path: str, config: dict) -> dict:
    tts_cfg = config.get("tts", {})
    voice = tts_cfg.get("voice", "en-US-SteffanNeural")

    speech_key = os.environ.get("AZURE_SPEECH_KEY")
    speech_region = os.environ.get("AZURE_SPEECH_REGION")

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
    )
    speech_config.speech_synthesis_voice_name = voice

    audio_config = speechsdk.audio.AudioOutputConfig(filename=output_path)
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config,
        audio_config=audio_config
    )

    words = script_text.split()
    word_timings = []

    def on_word_boundary(evt):
        if evt.boundary_type == speechsdk.SpeechSynthesisBoundaryType.Word:
            start = evt.audio_offset / 10_000_000  # ticks to seconds
            duration = evt.duration.total_seconds()
            word_timings.append({
                "word": evt.text,
                "start": start,
                "end": start + duration
            })

    synthesizer.synthesis_word_boundary.connect(on_word_boundary)

    rate = tts_cfg.get("rate", "90%")
    pitch = tts_cfg.get("pitch", "-2st")
    ssml = (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        f'<voice name="{voice}">'
        f'<prosody rate="{rate}" pitch="{pitch}">'
        f'{script_text}'
        f'</prosody></voice></speak>'
    )

    print(f"[tts] Synthesizing {len(words)} words with {voice}...")
    result = synthesizer.speak_ssml_async(ssml).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print(f"[tts] Done. {len(word_timings)} word timings returned.")
    else:
        cancellation = result.cancellation_details
        raise RuntimeError(f"Azure TTS failed: {cancellation.reason} — {cancellation.error_details}")

    return {
        "wav_path": output_path,
        "word_timings": word_timings
    }
