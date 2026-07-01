# F25 — Emotion-Reactive Screen Pet

An interactive **AI companion ("pet")** that watches your face through the webcam and reacts in real time.
Facial-emotion recognition runs in Python (DeepFace) and streams the detected emotion to a Unity
front-end, which plays a matching animation clip — and optionally a generated pet voice/sound.

> Status: prototype / experiment. This repo is a working archive of the scripts, Unity scene, and
> media assets used to build the demo (the `HER`-style voice and `00-intro_christmas` clip suggest a
> seasonal exhibit demo).

## How it works

```
 Webcam ──► DeepFace (Python)              Unity (C#)
            emotion analysis  ── UDP ────►  EmotionReceiver
            + smoothing        127.0.0.1     └─ swaps VideoClip by emotion
                                :5005
            PetSounds server ── HTTP ─────►  fetch generated voice / sound
            (Flask + OpenAI)
```

1. **Python** grabs webcam frames, runs `DeepFace.analyze(...)` to get the dominant emotion
   (`happy` / `sad` / `angry` / `neutral` / …), smooths it over the last ~10 frames to avoid
   flicker, and sends it only when it changes.
2. Transport is **UDP** to `127.0.0.1:5005` (see `deepface_to_unity.py`). A **FastAPI** variant
   (`app.py`) instead exposes an HTTP `POST /emotion` endpoint that returns the scores as JSON.
3. **Unity** (`EmotionReciever.cs`) listens on the UDP port in a background thread and, on
   `FixedUpdate`, swaps the playing `VideoClip` to match the current emotion.
4. **PetSoundsFinalTest.py** is a separate Flask + OpenAI service that synthesizes a "pet voice"
   (phoneme synthesis) for Unity to fetch.

## Repository layout

```
F25/
├── python/                     # Python side (emotion detection + pet voice)
│   ├── deepface_to_unity.py    # MAIN: webcam → DeepFace → UDP to Unity (with smoothing)
│   ├── app.py                  # Alternative: FastAPI POST /emotion → JSON scores
│   ├── PetSoundsFinalTest.py   # Flask + OpenAI pet-voice / phoneme synth server
│   ├── deepface_smooth.py      # emotion smoothing experiment
│   ├── interactive.py          # interactive test
│   ├── camera_test.py          # webcam sanity check
│   ├── deepface_test.py        # DeepFace test
│   └── deepface_test_2.py      # DeepFace test (variant)
├── unity/                      # Unity side
│   ├── F25_test.unity          # scene
│   └── Scripts/
│       ├── EmotionReciever.cs         # UDP receiver → VideoClip switcher (main)
│       ├── EmotionReciever_Camera.cs  # camera-driven variant
│       └── NewMonoBehaviourScript.cs
└── assets/                     # media
    ├── video/                  # emotion animation clips (greeting, happy_jump, crying, fear, …)
    │   └── misc/               # raw / alternate / alpha-matte render exports
    ├── audio/                  # pet sounds (*.wav) + ElevenLabs "HER" voice takes (*.mp3)
    └── image/                  # UI icons, circle/round masks, background, emotion GIFs
```

## Running

### Python (emotion → Unity, UDP)
```bash
pip install opencv-python deepface numpy
python python/deepface_to_unity.py      # opens webcam, sends emotion to 127.0.0.1:5005
```
Press the emotion-camera window to see live scores; `q`/close to quit.

### Python (pet voice server)
```bash
pip install flask flask-cors openai sounddevice numpy
export OPENAI_API_KEY="sk-..."          # required
python python/PetSoundsFinalTest.py
```

### Unity
1. Open `unity/F25_test.unity` in Unity (uses `UnityEngine.Video`).
2. On the `EmotionReceiver` component, assign the emotion `VideoClip`s (happy / sad / angry /
   neutral) from `assets/video/`, and confirm the port matches the Python side (**5005**).
3. Start the Python emotion script, then enter Play mode.

## Notes
- The Python UDP script and the Unity port **must match** (`5005` by default).
- Two detection paths exist: **UDP push** (`deepface_to_unity.py`) and **HTTP pull**
  (`app.py`) — use whichever fits your Unity integration.
- `OPENAI_API_KEY` is required only for the pet-voice server, not for emotion detection.
- Unity `.meta` files were dropped in the cleanup; regenerate them by importing the scripts/scene
  into a Unity project (originals remain recoverable in git history).

## Stack
Python · DeepFace · OpenCV · Flask / FastAPI · OpenAI · ElevenLabs (voice) · Unity (C#, VideoPlayer, UDP)
