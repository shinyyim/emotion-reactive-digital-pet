from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from deepface import DeepFace
import numpy as np
import cv2

app = FastAPI()


@app.post("/emotion")
async def detect_emotion(file: UploadFile = File(...)):
    """
    이미지 1장을 받아서 DeepFace로 감정 분석하고,
    지배적인 감정 + 각 감정 퍼센트(%)를 리턴한다.
    """
    # 업로드된 파일 → OpenCV 이미지로 변환
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return JSONResponse(
            status_code=400,
            content={"error": "이미지 파일을 읽을 수 없어요."},
        )

    try:
        # DeepFace 감정 분석
        result = DeepFace.analyze(
            img,
            actions=["emotion"],
            enforce_detection=False  # 얼굴이 조금 옆으로 있어도 계속 돌도록
        )

        # 버전/설치에 따라 리스트로 나오는 경우가 있어서 처리
        if isinstance(result, list):
            result = result[0]

        # 각 감정의 raw 점수(dict)
        raw_emotions = result["emotion"]  # 예: {"angry": 0.1, "happy": 95.3, ...}

        # 퍼센트로 normalizing
        total = sum(raw_emotions.values()) or 1.0
        emotions_percent = {
            name: round(score / total * 100, 2)
            for name, score in raw_emotions.items()
        }

        dominant = result.get("dominant_emotion", "neutral")

        return {
            "dominant_emotion": dominant,
            "emotions_percent": emotions_percent,
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"DeepFace 에러: {str(e)}"},
        )


# uvicorn으로 바로 실행하고 싶을 때: python app.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
