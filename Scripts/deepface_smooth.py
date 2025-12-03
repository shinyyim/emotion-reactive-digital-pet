import cv2
from deepface import DeepFace
from collections import deque

cap = cv2.VideoCapture(0)

# 최근 10개의 감정을 저장
emotion_queue = deque(maxlen=10)

def smooth_emotion():
    if not emotion_queue:
        return "None"
    return max(set(emotion_queue), key=emotion_queue.count)

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
        emotion = result[0]['dominant_emotion']
    except:
        emotion = "no_face"

    # queue에 넣고
    emotion_queue.append(emotion)

    # smoothing 된 감정
    smoothed = smooth_emotion()

    cv2.putText(frame, smoothed, (30, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)

    cv2.imshow("cam", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
