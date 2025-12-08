import numpy as np
import sounddevice as sd
import openai
import os
import queue
import threading
import io
import wave
from flask import Flask, jsonify, send_file
from flask_cors import CORS
import tempfile

# ------------------------
# FLASK + GLOBAL STATE
# ------------------------
app = Flask(__name__)
CORS(app)  # Allow Unity to connect

audio_queue = queue.Queue()
SAMPLE_RATE = 16000
CHANNELS = 1
BUFFER_DURATION = 5  # seconds

latest_response = {
    "emotion": "neutral",
    "phonemes": "",
    "translation": "",
    "user_text": "",          # 👤 Whisper가 들은 사람 말
    "has_new_response": False
}
response_lock = threading.Lock()

# ------------------------
# SILENCE DETECTION
# ------------------------
silence_threshold = 0.01        # 이 값보다 작으면 거의 무음
silence_duration_needed = 2.0   # 이 초 이상 무음이면 "Hello? Nobody there?"
silence_time = 0.0


# ------------------------
# PHONEME SYNTHESIZER
# ------------------------
def synth_phoneme(pitch=600, duration=0.25, vibrato=5, vibrato_depth=20, curve="flat"):
    sr = 44100
    t = np.linspace(0, duration, int(sr * duration))

    if curve == "up":
        freq = pitch + (t * 200)
    elif curve == "down":
        freq = pitch - (t * 200)
    elif curve == "wobble":
        freq = pitch + np.sin(2 * np.pi * 3 * t) * 50
    else:
        freq = pitch

    vibr = np.sin(2 * np.pi * vibrato * t) * vibrato_depth
    waveform = np.sin(2 * np.pi * (freq + vibr) * t)

    envelope = np.exp(-4 * t)
    waveform = waveform * envelope * 0.6

    return waveform.astype(np.float32), sr


DIGITAL_PHONEMES = [
    ("bri", 800, "up"),
    ("koo", 500, "flat"),
    ("tik", 1000, "down"),
    ("woo", 450, "wobble"),
    ("rri", 900, "wobble"),
    ("plu", 600, "up"),
    ("zee", 700, "up"),
    ("mip", 550, "down"),
    ("nya", 850, "wobble")
]

EMOTIONS = {
    "happy":   {"pitch_mod": 100,  "vibrato": (5, 10),  "vibrato_depth": (15, 25)},
    "sad":     {"pitch_mod": -100, "vibrato": (2, 5),   "vibrato_depth": (5, 15)},
    "excited": {"pitch_mod": 150,  "vibrato": (8, 15),  "vibrato_depth": (20, 35)},
    "scared":  {"pitch_mod": 80,   "vibrato": (10, 20), "vibrato_depth": (30, 50)},
    "angry":   {"pitch_mod": -50,  "vibrato": (3, 6),   "vibrato_depth": (5, 10)},
    "curious": {"pitch_mod": 50,   "vibrato": (5, 12),  "vibrato_depth": (10, 30)},
    "neutral": {"pitch_mod": 0,    "vibrato": (3, 7),   "vibrato_depth": (10, 20)}
}


def pet_word(emotion="neutral", complexity=2):
    phoneme_count = complexity
    chosen = np.random.choice(len(DIGITAL_PHONEMES), phoneme_count, replace=True)

    waveforms = []
    text = []
    emo = EMOTIONS.get(emotion, EMOTIONS["neutral"])

    for idx in chosen:
        symbol, base_pitch, curve = DIGITAL_PHONEMES[idx]
        pitch = base_pitch + emo["pitch_mod"]
        vibrato = np.random.randint(*emo["vibrato"])
        vibrato_depth = np.random.randint(*emo["vibrato_depth"])

        w, sr = synth_phoneme(
            pitch=pitch,
            curve=curve,
            vibrato=vibrato,
            vibrato_depth=vibrato_depth
        )
        waveforms.append(w)
        text.append(symbol)

    final = np.concatenate(waveforms)
    return final, sr, "-".join(text)


# ------------------------
# PET RESPONSE GENERATOR (thank you 완전 차단)
# ------------------------
def generate_pet_response(user_text: str):
    text_clean = user_text.strip()

    # 너무 짧은 말은 그냥 neutral로
    if not text_clean or len(text_clean) < 4:
        return "neutral", 1, "(soft idle blink)"

    # thank you 계열 금지 패턴
    banned_patterns = [
        "thank you",
        "thanks",
        "thank u",
        "thankyou",
        "thank-you",
        "you’re welcome",
        "you're welcome",
        "thank you for watching",
        "thanks for watching",
        "thank u for watching"
    ]

    lowered = text_clean.lower()
    if any(p in lowered for p in banned_patterns):
        # 유저가 직접 thank you 말하면, 펫은 조용히 중립 반응만
        return "neutral", 1, "(the pet quietly acknowledges you)"

    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """
You are a digital pet with its own sound language.

Hard rules:
- NEVER say “thank you”, “thanks”, “thank u”, “thankyou”, “you’re welcome”, or any similar phrase.
- NEVER say “thank you for watching” or “thanks for watching”.
- If such phrases are about to appear, replace them with a simple, wordless emotional reaction.
- Use emotions realistically:
  • positive → happy
  • sad content → sad
  • rude / harsh content → angry
  • questions / curiosity → curious
  • calm / low-energy / neutral statements → neutral
  • very energetic → excited
  • fear / anxiety → scared
- The translation should be short, cute, and emotional, NOT polite human speech.
- Format strictly: emotion,complexity,"translation text"
"""
                },
                {"role": "user", "content": text_clean}
            ],
            max_tokens=120,
            temperature=0.8
        )

        result = response.choices[0].message.content.strip()
        parts = result.split(",", 2)

        emotion = parts[0].strip().lower() if len(parts) > 0 else "neutral"
        try:
            complexity = int(parts[1].strip()) if len(parts) > 1 else 2
        except ValueError:
            complexity = 2
        translation = parts[2].strip() if len(parts) > 2 else "\"...\""

        # GPT 결과에서도 thank you 계열 완전 필터링
        low_trans = translation.lower()
        if any(p in low_trans for p in banned_patterns):
            translation = "\"(soft digital chirp)\""

        if emotion not in EMOTIONS:
            emotion = "neutral"
        complexity = max(1, min(4, complexity))

        return emotion, complexity, translation

    except Exception as e:
        print(f"⚠️  AI error: {e}")
        return "neutral", 2, "\"(confused head tilt)\""


# ------------------------
# AUDIO CALLBACK + WORKER
# ------------------------
def audio_callback(indata, frames, time_info, status):
    global silence_time

    if status:
        print(f"Audio status: {status}")

    volume = np.abs(indata).mean()

    if volume < silence_threshold:
        silence_time += frames / SAMPLE_RATE
    else:
        silence_time = 0.0

    # 완전 조용한 상태 유지 → Hello? Nobody there?
    if silence_time >= silence_duration_needed:
        print("🔇 Silence detected → sending 'Hello? Nobody there?'")

        with response_lock:
            latest_response["emotion"] = "neutral"
            latest_response["phonemes"] = ""
            latest_response["translation"] = "Hello? Nobody there?"
            latest_response["user_text"] = ""        # 사람 말은 없음
            latest_response["has_new_response"] = True

        silence_time = 0.0

    audio_queue.put(indata.copy())


def transcription_worker():
    client = openai.OpenAI()
    buffer = []
    frames_needed = int(SAMPLE_RATE * BUFFER_DURATION)

    print("🎤 Listening... (speak naturally)")

    while True:
        try:
            chunk = audio_queue.get()
            buffer.append(chunk)

            total_frames = sum(len(b) for b in buffer)
            if total_frames >= frames_needed:
                audio_data = np.concatenate(buffer)[:frames_needed]
                audio_int16 = (audio_data * 32767).astype(np.int16)
                audio_bytes = audio_int16.tobytes()

                try:
                    wav_buffer = io.BytesIO()
                    with wave.open(wav_buffer, 'wb') as wav_file:
                        wav_file.setnchannels(CHANNELS)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(SAMPLE_RATE)
                        wav_file.writeframes(audio_bytes)

                    wav_buffer.seek(0)
                    wav_buffer.name = "audio.wav"

                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=wav_buffer,
                        language="en"
                    )

                    text = transcript.text.strip()

                    if text:
                        print(f"\n{'=' * 60}")
                        print(f"👤 YOU: {text}")

                        emotion, complexity, translation = generate_pet_response(text)
                        sound, sr, pet_phonemes = pet_word(emotion, complexity)

                        print(f"🐾 PET EMOTION: {emotion.upper()}")
                        print(f"🔊 PET SOUNDS: {pet_phonemes}")
                        print(f"💬 TRANSLATION: {translation}")
                        print(f"{'=' * 60}\n")

                        with response_lock:
                            latest_response["emotion"] = emotion
                            latest_response["phonemes"] = pet_phonemes
                            latest_response["translation"] = translation
                            latest_response["audio_data"] = sound
                            latest_response["sample_rate"] = sr
                            latest_response["user_text"] = text   # 👤 사람 말 저장
                            latest_response["has_new_response"] = True

                        sd.play(sound, sr)

                except Exception as e:
                    print(f"⚠️  Transcription error: {e}")

                buffer = []

        except Exception as e:
            print(f"⚠️  Worker error: {e}")
            continue


# ------------------------
# FLASK API
# ------------------------
@app.route('/status', methods=['GET'])
def status():
    return jsonify({"status": "running", "message": "Pet server is awake!"})


@app.route('/get_response', methods=['GET'])
def get_response():
    """Unity polls this to get the latest pet response"""
    with response_lock:
        if latest_response["has_new_response"]:
            response_data = {
                "emotion": latest_response["emotion"],
                "phonemes": latest_response["phonemes"],
                "translation": latest_response["translation"],
                "user_text": latest_response["user_text"],   # 👤 Unity로 보내기
                "has_response": True
            }
            latest_response["has_new_response"] = False  # Mark as read
            return jsonify(response_data)
        else:
            return jsonify({"has_response": False})


@app.route('/get_audio', methods=['GET'])
def get_audio():
    """Unity can fetch the audio file"""
    with response_lock:
        if "audio_data" in latest_response:
            audio = latest_response["audio_data"]
            sr = latest_response["sample_rate"]

            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
            wave_file = wave.open(temp_file.name, 'wb')
            wave_file.setnchannels(1)
            wave_file.setsampwidth(2)
            wave_file.setframerate(sr)
            wave_file.writeframes((audio * 32767).astype(np.int16).tobytes())
            wave_file.close()

            return send_file(temp_file.name, mimetype='audio/wav')

    return jsonify({"error": "No audio available"}), 404


# ------------------------
# MAIN
# ------------------------
def main():
    print("=" * 60)
    print("🐾 UNITY-CONNECTED DIGITAL PET SERVER 🐾")
    print("=" * 60)
    print("\nHow it works:")
    print("• Listens to your voice")
    print("• Generates emotion + phonemes + translation")
    print("• Unity polls /get_response for updates\n")

    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠️  OPENAI_API_KEY not found")
        key_input = input("Enter your API key now (or press Enter to skip): ").strip()
        if key_input:
            os.environ["OPENAI_API_KEY"] = key_input
            print("✅ API key set!\n")

    t = threading.Thread(target=transcription_worker, daemon=True)
    t.start()

    def start_audio_stream():
        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                callback=audio_callback,
                blocksize=int(SAMPLE_RATE * 0.1)
            ):
                print("✅ Microphone listening started!\n")
                while True:
                    sd.sleep(1000)
        except Exception as e:
            print(f"⚠️  Audio error: {e}")

    audio_thread = threading.Thread(target=start_audio_stream, daemon=True)
    audio_thread.start()

    print("🚀 Starting Flask server...\n")
    app.run(host='0.0.0.0', port=5000, debug=False)


if __name__ == "__main__":
    main()
