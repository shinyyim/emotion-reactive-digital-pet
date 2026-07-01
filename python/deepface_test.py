import cv2
from deepface import DeepFace

# 0번 웹캠 열기
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("웹캠을 열 수 없어요 ㅠㅠ")
    exit()

while True:
    ret, frame = cap.read()
    if not ret:
        print("프레임을 읽을 수 없어요.")
        break

    try:
        # 감정 분석
        result = DeepFace.analyze(
            frame,
            actions=["emotion"],
            enforce_detection=False
        )

        if isinstance(result, list):
            result = result[0]

        emotions = result["emotion"]          # raw 점수
        dominant = result["dominant_emotion"] # 제일 큰 감정

        # 상위 3개 감정 퍼센트로 계산
        total = sum(emotions.values()) or 1.0
        sorted_emotions = sorted(
            emotions.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

        text_lines = [f"{dominant.upper()}"]
        for name, score in sorted_emotions:
            percent = score / total * 100
            text_lines.append(f"{name}: {percent:.1f}%")

        # 화면에 텍스트 그리기
        y = 30
        for line in text_lines:
            cv2.putText(
                frame,
                line,
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            y += 25

    except Exception as e:
        # 인식 안되면 그냥 넘어가고 계속 재생
        cv2.putText(
            frame,
            "no face / error",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    cv2.imshow("DeepFace Realtime", frame)

    # q 누르면 종료
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
