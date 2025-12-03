import cv2
from deepface import DeepFace
from collections import deque
import socket

# ---------- UDP 설정 ----------
UDP_IP = "127.0.0.1"
UDP_PORT = 5005
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# ---------- Emotion smoothing 설정 ----------
emotion_queue = deque(maxlen=10)
last_sent_emotion = None

def smooth_emotion():
    if not emotion_queue:
        return "none"
    return max(set(emotion_queue), key=emotion_queue.count)

# ---------- 카메라 ----------
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    try:
        result = DeepFace.analyze(
            frame,
            actions=['emotion'],
            enforce_detection=False
        )

        # 감정 데이터
        emotion = result[0]['dominant_emotion']
        emotion_scores = result[0]['emotion']   # dict 형태 (Happy: %, Sad: % ...)
    except:
        emotion = "no_face"
        emotion_scores = {}

    # smoothing
    emotion_queue.append(emotion)
    smoothed = smooth_emotion()

    # 감정 바뀔 때만 Unity로 보내기
    if smoothed != last_sent_emotion:
        msg = smoothed.encode("utf-8")
        sock.sendto(msg, (UDP_IP, UDP_PORT))
        print("send to Unity:", smoothed)
        last_sent_emotion = smoothed

    # dominant emotion 표시
    cv2.putText(
        frame,
        f"Emotion: {smoothed}",
        (30, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2
    )

    # 감정 확률 표시
    start_y = 80
    for emo, value in emotion_scores.items():
        text = f"{emo}: {value:.1f}%"
        cv2.putText(
            frame,
            text,
            (30, start_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )
        start_y += 30  # 다음 줄로 내림

    # 화면 표시
    cv2.imshow("Emotion Camera", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
sock.close()
