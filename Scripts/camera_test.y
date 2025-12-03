import cv2

def test_camera():
    print("[시작] 카메라를 켭니다...")
    
    # 0번 카메라 열기
    cap = cv2.VideoCapture(0)
    
    # 맥북 호환성 설정 (혹시 몰라서 넣음)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("[에러] ❌ 카메라를 열 수 없습니다! (권한 문제일 수 있음)")
        return

    print("[성공] ✅ 카메라가 열렸습니다! 창이 떴나요? (끄려면 'q' 누르세요)")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[에러] 화면을 읽을 수 없습니다.")
            break
        
        # 윈도우 창에 내 얼굴 띄우기
        cv2.imshow('Camera Test (Press q to quit)', frame)
        
        # q를 누르면 종료
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    test_camera()