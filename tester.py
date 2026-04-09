import os
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

load_dotenv()

SCRIPT = (
    "My neighbor has lived alone for eleven years. I know because I moved in the same week she did. "
    "We wave. Sometimes we talk over the fence. Normal stuff. "
    "Last Thursday I saw the lights in her house go on at two in the morning. Every single one. "
    "I thought maybe she couldn't sleep. I've been there. "
    "But then I saw someone standing at her bedroom window. Just standing there. Not moving. "
    "The shape was too tall to be her. "
    "I texted her. No reply. I called. Straight to voicemail. "
    "I told myself it was nothing. I went back to bed. "
    "Friday morning she waved at me from the driveway like always. "
    "I asked if everything was okay. She said yes, why. "
    "I said I saw her lights on late. She looked at me for a second too long. "
    "Then she said she went to bed at ten. She always does. "
    "I haven't been able to sleep since."
)

# (voice_label, voice_name, rate, pitch)
PRESETS = [
    ("eric_25", "en-US-EricNeural", "25%", "+0st"),
]

def audition(label: str, voice: str, rate: str, pitch: str):
    speech_key = os.environ.get("AZURE_SPEECH_KEY")
    speech_region = os.environ.get("AZURE_SPEECH_REGION")

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
    )
    speech_config.speech_synthesis_voice_name = voice

    filename = f"test_{label}.wav"
    audio_config = speechsdk.audio.AudioOutputConfig(filename=filename)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

    word_count = [0]
    def on_word(evt):
        if evt.boundary_type == speechsdk.SpeechSynthesisBoundaryType.Word:
            word_count[0] += 1
    synthesizer.synthesis_word_boundary.connect(on_word)

    ssml = (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        f'<voice name="{voice}">'
        f'<prosody rate="{rate}" pitch="{pitch}">'
        f'{SCRIPT}'
        f'</prosody></voice></speak>'
    )

    result = synthesizer.speak_ssml_async(ssml).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print(f"[✓] {label} → {filename}  (rate={rate} pitch={pitch})  [{word_count[0]} words timed]")
    else:
        details = result.cancellation_details
        print(f"[✗] {label} → {details.reason}: {details.error_details}")

if __name__ == "__main__":
    for label, voice, rate, pitch in PRESETS:
        audition(label, voice, rate, pitch)
    print("\nDone. Listen and pick.")
