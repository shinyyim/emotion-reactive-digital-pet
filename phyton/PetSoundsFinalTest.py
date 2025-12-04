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
BUFFER_DURATION = 3  # seconds

# Unity가 폴링해서 가져갈 최신 상태
latest_response = {
    "emotion": "neutral",
    "phonemes": "",
    "translation": "",
    "has_new_response": False
}
response_lock = threading.Lock()

# ------------------------
# SILENCE DETECTION
# ------------------------
silence_threshold = 0.01        # 평균 볼륨이 이 값보다 작으면 무음으로 판단
silence_duration_needed = 2.0   # 이 초 이상 무음이면 "아무도 없어요?" 메시지 전송
silence_time = 0.0              # 누적 무음 시간


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
# GPT RESPONSE GENERATOR
# ------------------------
def generate_pet_response(user_text: str):
    """
    사람이 실제로 말을 했을 때만 호출되는 함수.
    - 아주 짧은 말(<4글자)은 강제 neutral
    - 'thank you' 류 표현은 프롬프트 & post-process에서 제거
    """

    text_clean = user_text.strip()
    if not text_clean or len(text_clean) < 4:
        # 너무 짧으면 그냥 살짝 주변 둘러보는 느낌
        return "neutral", 1, "(looks around quietly)"

    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": """
You are a digital pet that responds ONLY based on the emotional tone of the human's message.

Rules you MUST follow:

1. NEVER say “thank you”, “thanks”, “thank u”, “you’re welcome”, or anything similar.
2. NEVER generate polite human-like responses. You are a pet, not a human.
3. The translation must be cute, simple, and emotional, but NOT repetitive.
4. Do NOT default to “happy” all the time. Use emotions realistically:
   - positive → happy
   - negative / sad content → sad
   - angry / rude content → angry
   - questions / curiosity → curious
   - calm / short / low-energy speech → neutral
   - very energetic / excited speech → excited
   - fear / anxiety → scared
5. The translation must match the emotion and should vary across responses.
6. Avoid using the same wording too often.

Format strictly:
emotion,complexity,"translation text"

Examples:
neutral,1,"(soft blink)"
curious,2,"Hmm? What's happening?"
sad,1,"I feel a little droopy..."
angry,2,"Hey! That startled me!"
happy,2,"Yip-yip! I like this!"
excited,3,"Whoa—so much energy!"
scared,2,"Eep… that was spooky..."
"""
                },
                {"role": "user", "content": text_clean}
            ],
            max_tokens=120,
            temperature=0.8
        )

        result = response.choices[0].message.content.strip()
        parts = result.split(',', 2)

        emotion = parts[0].strip().lower() if len(parts) > 0 else "neutral"
        complexity = int(parts[1].strip()) if len(parts) > 1 else 2
        translation = parts[2].strip() if len(parts) > 2 else "\"...\""

        # 안전장치: emotion이 리스트에 없으면 neutral
        if emotion not in EMOTIONS:
            emotion = "neutral"
        complexity = max(1, min(4, complexity))

        # 추가 안전장치: translation에서 thank you 류 표현 강제 제거
        low = translation.lower()
        if "thank" in low or "welcome" in low:
            translation = "\"(wiggles quietly instead of saying thanks)\""

        return emotion, complexity, translation

    except Exception as e:
        print(f"⚠️  AI error: {e}")
        return "neutral", 2, "\"(confused head tilt)\""


# ------------------------
# AUDIO CALLBACK + WORKER
# ------------------------
def audio_callback(indata, frames, time_info, status):
    """
    마이크에서 들어오는 오디오를 큐에 넣고,
    일정 시간 이상 완전 조용하면 'Hello, Nobody there?' 메시지 전송
    """
    global silence_time

    if status:
        print(f"Audio status: {status}")

    volume = np.abs(indata).mean()

    # 무음 누적
    if volume < silence_threshold:
        silence_time += frames / SAMPLE_RATE
    else:
        silence_time = 0.0

    # 🔇 완전 조용한 상태가 일정 시간 지속되면 → neutral + 'Is anyone there?'
    if silence_time >= silence_duration_needed:
        print("🔇 Silence detected → sending 'Hello, Nobody there?' neutral response")

        with response_lock:
            latest_response["emotion"] = "neutral"
            latest_response["phonemes"] = ""
            latest_response["translation"] = "Hello, Nobody there?"
            latest_response["has_new_response"] = True
            # audio_data / sample_rate 는 굳이 안 넣어도 됨

        silence_time = 0.0

    # 음성 분석용 버퍼에 추가
    audio_queue.put(indata.copy())


def transcription_worker():
    """
    큐에 쌓인 오디오를 3초 단위로 모아서 Whisper로 텍스트 변환
    → GPT로 emotion / translation 생성 → Unity에 전달
    """
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

                    if text and len(text) > 0:
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
                            latest_response["has_new_response"] = True

                        # 로컬에서도 사운드 재생
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
    """
    Unity가 poll해서 emotion / translation 가져가는 엔드포인트
    """
    with response_lock:
        if latest_response["has_new_response"]:
            resp = {
                "emotion": latest_response["emotion"],
                "phonemes": latest_response["phonemes"],
                "translation": latest_response["translation"],
                "has_response": True
            }
            latest_response["has_new_response"] = False
            return jsonify(resp)
        else:
            return jsonify({"has_response": False})


@app.route('/get_audio', methods=['GET'])
def get_audio():
    """
    Unity가 펫 소리 WAV를 받고 싶을 때 사용하는 엔드포인트
    """
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
    print("• Python listens to your voice continuously")
    print("• Pet generates responses (emotion + translation + sounds)")
    print("• Unity polls the server to display the responses")
    print("\nAPI Endpoints for Unity:")
    print("• GET http://localhost:5000/status")
    print("• GET http://localhost:5000/get_response")
    print("• GET http://localhost:5000/get_audio")
    print("=" * 60)
    print()

    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠️  OPENAI_API_KEY not found")
        key_input = input("Enter your API key now (or press Enter to skip): ").strip()
        if key_input:
            os.environ["OPENAI_API_KEY"] = key_input
            print("✅ API key set!\n")

    # 음성 → 텍스트 쓰레드
    thread = threading.Thread(target=transcription_worker, daemon=True)
    thread.start()

    # 마이크 스트림 쓰레드
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

    # Flask 서버 시작
    print("🚀 Starting Flask server...\n")
    app.run(host='0.0.0.0', port=5000, debug=False)


if __name__ == "__main__":
    main()
