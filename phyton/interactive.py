import pygame
import cv2
import numpy as np
import pyaudio
import random
import time
import math
import sys

# --- 설정값 ---
CONFIG = {
    'width': 540,     
    'height': 960,    
    'fullscreen': False, 
    'max_particles': 500,
    'motion_sensitivity': 15, # 민감도를 더 낮춰서(30->15) 작은 움직임도 잡게 수정
    'skip_pixels': 5,
    'cam_width': 320,  
    'cam_height': 240  
}

# --- 자막 (시) ---
SUBTITLES = [
    "Hi there,",
    "I’m the small presence\ndrifting quietly into your world.",
    "A soft reflection of your mood…\nshaped by the light you carry.",
    "I don’t speak much.",
    "I listen—",
    "to the way your eyes shift,",
    "the subtle tone in your voice,",
    "the little signals you leave\nin the air around you.",
    "When your energy rises,",
    "I glow a little brighter.",
    "When you feel tired or overwhelmed,",
    "I slow down…",
    "and rest beside you.",
    "I wasn’t made to solve everything.",
    "Just to be here with you—",
    "to echo your feelings in gentle motions,",
    "to return your emotions back to you\nin a softer shape.",
    "I exist because you do.",
    "A tiny companion of emotion,",
    "born from your presence,",
    "and here to stay close…",
    "quietly,",
    "warmly,",
    "with you."
]

class Particle:
    def __init__(self, x, y, volume, hue):
        self.x = x
        self.y = y
        self.size = random.uniform(3, 8) + (volume * 0.2) # 입자 기본 크기 키움
        self.speed_x = random.uniform(-3, 3)
        self.speed_y = random.uniform(-3, 3)
        
        # 색상 계산
        r = int(math.sin(hue * 0.1) * 127 + 128)
        g = int(math.sin(hue * 0.1 + 2) * 127 + 128)
        b = int(math.sin(hue * 0.1 + 4) * 127 + 128)
        self.color = (r, g, b)
        self.life = 255 

    def update(self):
        self.x += self.speed_x
        self.y += self.speed_y
        self.life -= 5 

    def draw(self, surface):
        if self.life > 0:
            s = pygame.Surface((int(self.size*2), int(self.size*2)), pygame.SRCALPHA)
            pygame.draw.circle(s, (*self.color, self.life), (int(self.size), int(self.size)), int(self.size))
            surface.blit(s, (int(self.x - self.size), int(self.y - self.size)))

def draw_text_with_shadow(surface, text, font, x, y, alpha):
    # 그림자
    shadow_surface = font.render(text, True, (0, 0, 0))
    shadow_surface.set_alpha(alpha)
    shadow_rect = shadow_surface.get_rect(center=(x + 2, y + 2))
    surface.blit(shadow_surface, shadow_rect)
    # 본문
    text_surface = font.render(text, True, (255, 255, 255))
    text_surface.set_alpha(alpha)
    text_rect = text_surface.get_rect(center=(x, y))
    surface.blit(text_surface, text_rect)

def main():
    pygame.init()
    print("--- 프로그램 시작 ---")
    
    if CONFIG['fullscreen']:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        W, H = screen.get_size()
    else:
        screen = pygame.display.set_mode((CONFIG['width'], CONFIG['height']))
        W, H = CONFIG['width'], CONFIG['height']
        
    pygame.display.set_caption("Interactive Art: The Small Presence")
    clock = pygame.time.Clock()

    # 폰트
    try:
        possible_fonts = ['georgia', 'batang', 'gungsuh', 'timesnewroman', 'arial']
        font_path = None
        for f in possible_fonts:
            match = pygame.font.match_font(f)
            if match:
                font_path = match
                break
        font = pygame.font.Font(font_path, 30) if font_path else pygame.font.SysFont(None, 30)
        debug_font = pygame.font.SysFont(None, 24) # 디버그용 폰트
    except:
        font = pygame.font.SysFont(None, 30)
        debug_font = pygame.font.SysFont(None, 24)

    # --- 카메라 설정 ---
    print("카메라 연결 시도 중...")
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("!! 오류: 카메라를 찾을 수 없습니다.")
        camera_ok = False
    else:
        print("카메라 연결 성공")
        camera_ok = True
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CONFIG['cam_width'])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CONFIG['cam_height'])

    ret, prev_frame = cap.read()
    if not ret:
        print("!! 경고: 카메라 영상을 읽을 수 없습니다. (권한 문제일 수 있음)")
        camera_ok = False
    else:
        prev_frame = cv2.resize(prev_frame, (CONFIG['cam_width'], CONFIG['cam_height']))
        prev_frame = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        prev_frame = cv2.flip(prev_frame, 1)

    # --- 오디오 설정 ---
    print("마이크 연결 시도 중...")
    p = pyaudio.PyAudio()
    stream = None
    mic_ok = False
    try:
        # 맥에서는 input_device_index를 명시해야 할 수도 있으나 일단 기본값 시도
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
        print("마이크 연결 성공")
        mic_ok = True
    except Exception as e:
        print(f"!! 오류: 마이크 초기화 실패 - {e}")
        mic_ok = False

    particles = []
    hue = 0
    volume = 0
    
    subtitle_index = 0
    subtitle_timer = time.time()
    current_subtitle = SUBTITLES[0]
    subtitle_alpha = 0
    subtitle_fading_in = True

    print("\n=== 실행 중 ===")
    print("터미널에 볼륨 수치가 0으로 나오면 마이크 권한을 확인하세요.")
    print("Ctrl+C를 누르면 종료됩니다.\n")

    frame_count = 0
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        # --- 오디오 볼륨 계산 ---
        current_vol_raw = 0
        if mic_ok and stream:
            try:
                if stream.get_read_available() > 0:
                    raw_data = stream.read(1024, exception_on_overflow=False)
                    data = np.frombuffer(raw_data, dtype=np.int16)
                    current_vol_raw = np.abs(data).mean()
                    volume = current_vol_raw / 10 # 스케일링
                else:
                    volume *= 0.9
            except Exception as e:
                print(f"Mic Read Error: {e}")
        
        # --- 모션 감지 ---
        motion_detected_count = 0
        if camera_ok:
            ret, frame = cap.read()
            if ret:
                small_frame = cv2.resize(frame, (CONFIG['cam_width'], CONFIG['cam_height']))
                gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.flip(gray, 1)

                frame_diff = cv2.absdiff(prev_frame, gray)
                _, thresh = cv2.threshold(frame_diff, CONFIG['motion_sensitivity'], 255, cv2.THRESH_BINARY)
                
                ys, xs = np.where(thresh[::CONFIG['skip_pixels'], ::CONFIG['skip_pixels']] > 0)
                motion_detected_count = len(xs)
                
                if len(xs) > 0:
                    scale_x = W / (CONFIG['cam_width'] / CONFIG['skip_pixels'])
                    scale_y = H / (CONFIG['cam_height'] / CONFIG['skip_pixels'])
                    
                    num_to_spawn = min(len(xs), 8) # 생성 개수 증가
                    indices = np.random.choice(len(xs), num_to_spawn)
                    
                    for i in indices:
                        if len(particles) < CONFIG['max_particles']:
                            px = xs[i] * scale_x + random.randint(-15, 15)
                            py = ys[i] * scale_y + random.randint(-15, 15)
                            particles.append(Particle(px, py, volume, hue))

                prev_frame = gray
            else:
                camera_ok = False # 읽기 실패 시 상태 변경

        # --- 화면 그리기 ---
        fade_surface = pygame.Surface((W, H), pygame.SRCALPHA)
        fade_surface.fill((0, 0, 0, 40)) 
        screen.blit(fade_surface, (0, 0))

        hue += 0.5
        center_color = (
            int(math.sin(hue * 0.05) * 60 + 60),
            int(math.sin(hue * 0.05 + 2) * 60 + 60),
            int(math.sin(hue * 0.05 + 4) * 80 + 100)
        )
        
        # 중앙 원
        base_radius = min(W, H) * 0.15 
        reaction_radius = volume * 5 
        pygame.draw.circle(screen, center_color, (W//2, H//2), int(base_radius + reaction_radius), 5)

        for p in particles[:]:
            p.update()
            p.draw(screen)
            if p.life <= 0:
                particles.remove(p)

        # 자막
        current_time = time.time()
        if current_time - subtitle_timer > 4.5: 
            subtitle_fading_in = False
            if subtitle_alpha <= 0:
                subtitle_index = (subtitle_index + 1) % len(SUBTITLES)
                current_subtitle = SUBTITLES[subtitle_index]
                subtitle_timer = current_time
                subtitle_fading_in = True
        
        if subtitle_fading_in and subtitle_alpha < 255:
            subtitle_alpha += 5
        elif not subtitle_fading_in and subtitle_alpha > 0:
            subtitle_alpha -= 5
            
        lines = current_subtitle.split('\n')
        text_y = H * 0.75
        for line in lines:
            draw_text_with_shadow(screen, line, font, W//2, text_y, subtitle_alpha)
            text_y += 40 

        # --- 디버그 정보 (화면 좌측 상단) ---
        if not camera_ok:
            debug_surf = debug_font.render("NO CAMERA INPUT", True, (255, 0, 0))
            screen.blit(debug_surf, (10, 10))
        if not mic_ok:
            debug_surf = debug_font.render("NO MIC INPUT", True, (255, 0, 0))
            screen.blit(debug_surf, (10, 40))
        
        # 터미널 로그 출력 (매 60프레임마다)
        frame_count += 1
        if frame_count % 60 == 0:
            print(f"[상태] 입자수: {len(particles)} | 볼륨: {current_vol_raw:.1f} | 모션픽셀: {motion_detected_count}")

        pygame.display.flip()
        clock.tick(60)

    # 종료
    cap.release()
    if stream:
        stream.stop_stream()
        stream.close()
    p.terminate()
    pygame.quit()

if __name__ == "__main__":
    main()