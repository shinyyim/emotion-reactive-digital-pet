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
import base64
import tempfile

# Set your OpenAI API key
# os.environ["OPENAI_API_KEY"] = "your-api-key-here"

app = Flask(__name__)
CORS(app)  # Allow Unity to connect

# ------------------------
# AUDIO BUFFER SETUP
# ------------------------
audio_queue = queue.Queue()
SAMPLE_RATE = 16000
CHANNELS = 1
BUFFER_DURATION = 3

# Store latest pet response for Unity to fetch
latest_response = {
    "emotion": "neutral",
    "phonemes": "",
    "translation": "",
    "has_new_response": False
}
response_lock = threading.Lock()


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


# ------------------------
# PET PHONEMES
# ------------------------
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

# ------------------------
# EMOTIONS & MODIFIERS
# ------------------------
EMOTIONS = {
    "happy": {"pitch_mod": 100, "vibrato": (5, 10), "vibrato_depth": (15, 25)},
    "sad": {"pitch_mod": -100, "vibrato": (2, 5), "vibrato_depth": (5, 15)},
    "excited": {"pitch_mod": 150, "vibrato": (8, 15), "vibrato_depth": (20, 35)},
    "scared": {"pitch_mod": 80, "vibrato": (10, 20), "vibrato_depth": (30, 50)},
    "angry": {"pitch_mod": -50, "vibrato": (3, 6), "vibrato_depth": (5, 10)},
    "curious": {"pitch_mod": 50, "vibrato": (5, 12), "vibrato_depth": (10, 30)},
    "neutral": {"pitch_mod": 0, "vibrato": (3, 7), "vibrato_depth": (10, 20)}
}


# ------------------------
# GENERATE A PET WORD
# ------------------------
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
# PET RESPONSE GENERATOR
# ------------------------
def generate_pet_response(user_text):
    if not user_text.strip():
        return "neutral", 1, "..."

    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """You are a digital pet that speaks in its own language (sounds like "bri-koo-tik-woo").
                The human just said something to you. Respond with:
                1. Your emotion: happy, sad, excited, scared, angry, curious, or neutral
                2. Complexity (1-4): how much you want to "say" (number of sound syllables)
                3. Translation: What your pet sounds MEAN in English (1-2 short sentences, like subtitles)

                The translation should sound like a cute pet speaking, matching the emotion.

                Format: emotion,complexity,translation text
                Example: happy,3,Yay! I'm so happy to see you!
                Example: curious,2,Ooh, what's that? Tell me more!"""},
                {"role": "user", "content": user_text}
            ],
            max_tokens=100,
            temperature=0.8
        )

        result = response.choices[0].message.content.strip()
        parts = result.split(',', 2)

        emotion = parts[0].strip().lower() if len(parts) > 0 else "neutral"
        complexity = int(parts[1].strip()) if len(parts) > 1 else 2
        translation = parts[2].strip() if len(parts) > 2 else "..."

        if emotion not in EMOTIONS:
            emotion = "neutral"
        complexity = max(1, min(4, complexity))

        return emotion, complexity, translation
    except Exception as e:
        print(f"⚠️  AI error: {e}")
        return "neutral", 2, "Hmm..."


# ------------------------
# AUDIO CALLBACK
# ------------------------
def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"Audio status: {status}")
    audio_queue.put(indata.copy())


# ------------------------
# TRANSCRIPTION THREAD
# ------------------------
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

                    if text and len(text) > 3:
                        print(f"\n{'=' * 60}")
                        print(f"👤 YOU: {text}")

                        emotion, complexity, translation = generate_pet_response(text)
                        sound, sr, pet_phonemes = pet_word(emotion, complexity)

                        print(f"🐾 PET EMOTION: {emotion.upper()}")
                        print(f"🔊 PET SOUNDS: {pet_phonemes}")
                        print(f"💬 TRANSLATION: \"{translation}\"")
                        print(f"{'=' * 60}\n")

                        # Update global response for Unity
                        with response_lock:
                            latest_response["emotion"] = emotion
                            latest_response["phonemes"] = pet_phonemes
                            latest_response["translation"] = translation
                            latest_response["audio_data"] = sound
                            latest_response["sample_rate"] = sr
                            latest_response["has_new_response"] = True

                        # Still play locally
                        sd.play(sound, sr)

                except Exception as e:
                    print(f"⚠️  Transcription error: {e}")

                buffer = []

        except Exception as e:
            print(f"⚠️  Worker error: {e}")
            continue


# ------------------------
# FLASK API ENDPOINTS
# ------------------------

@app.route('/status', methods=['GET'])
def status():
    """Check if server is running"""
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
            # Convert to WAV format
            audio = latest_response["audio_data"]
            sr = latest_response["sample_rate"]

            # Create temporary WAV file
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
    print("• Python listens to your voice continuously")
    print("• Pet generates responses (emotion + translation + sounds)")
    print("• Unity polls the server to display the responses")
    print("\nAPI Endpoints for Unity:")
    print("• GET http://localhost:5000/status - Check if server is running")
    print("• GET http://localhost:5000/get_response - Get latest pet response")
    print("• GET http://localhost:5000/get_audio - Download audio file")
    print("\nSetup:")
    print("1. Install: pip install flask flask-cors")
    print("2. Set your OpenAI API key")
    print("3. Run this script")
    print("4. Connect Unity to http://localhost:5000")
    print("=" * 60)
    print()

    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not found")
        key_input = input("Enter your API key now (or press Enter to skip): ").strip()
        if key_input:
            os.environ["OPENAI_API_KEY"] = key_input
            print("✅ API key set!\n")

    # Start transcription thread
    thread = threading.Thread(target=transcription_worker, daemon=True)
    thread.start()

    # Start audio stream in separate thread
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

    # Start Flask server
    print("🚀 Starting Flask server...\n")
    app.run(host='0.0.0.0', port=5000, debug=False)


if __name__ == "__main__":
    main()