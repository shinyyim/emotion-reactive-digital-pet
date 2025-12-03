import pygame
import cv2
import numpy as np
import pyaudio
import random
import time
import math

# --- 설정값 ---
CONFIG = {
    # [참고] HTML 버전(2694x4680)과 비율(9:16)은 같지만, 
    # PC 모니터에서 테스트하기 좋게 크기를 1/3 정도로 줄여두었습니다.
    # 전체화면으로 실행하려면 'fullscreen': True 로 바꾸세요.
    'width': 540,     
    'height': 960,    
    'fullscreen': False, 
    'max_particles': 500,
    'motion_sensitivity': 25, # HTML과 동일하게 조정
    'skip_pixels': 5,         # 촘촘한 검사 (HTML 최종본과 동일)
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
        # HTML 버전과 비슷한 크기 비율로 조정
        self.size = random.uniform(2, 6) + (volume * 0.15)
        self.speed_x = random.uniform(-2, 2)
        self.speed_y = random.uniform(-2, 2)
        
        # 색상 계산 (HSL 느낌 모방)
        r = int(math.sin(hue * 0.1) * 127 + 128)
        g = int(math.sin(hue * 0.1 + 2) * 127 + 128)
        b = int(math.sin(hue * 0.1 + 4) * 127 + 128)
        self.color = (r, g, b)
        self.life = 255 

    def update(self):
        self.x += self.speed_x
        self.y += self.speed_y
        self.life -= 4 # 수명 감소 속도 조정

    def draw(self, surface):
        if self.life > 0:
            s = pygame.Surface((int(self.size*2), int(self.size*2)), pygame.SRCALPHA)
            pygame.draw.circle(s, (*self.color, self.life), (int(self.size), int(self.size)), int(self.size))
            surface.blit(s, (int(self.x - self.size), int(self.y - self.size)))

def draw_text_with_shadow(surface, text, font, x, y, alpha):
    """자막에 그림자 효과를 주는 함수 (HTML의 text-shadow 효과 흉내)"""
    # 그림자 (검정색)
    shadow_surface = font.render(text, True, (0, 0, 0))
    shadow_surface.set_alpha(alpha)
    shadow_rect = shadow_surface.get_rect(center=(x + 2, y + 2)) # 2px 오프셋
    surface.blit(shadow_surface, shadow_rect)
    
    # 본문 (흰색)
    text_surface = font.render(text, True, (255, 255, 255))
    text_surface.set_alpha(alpha)
    text_rect = text_surface.get_rect(center=(x, y))
    surface.blit(text_surface, text_rect)

def main():
    pygame.init()
    
    if CONFIG['fullscreen']:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        W, H = screen.get_size()
    else:
        screen = pygame.display.set_mode((CONFIG['width'], CONFIG['height']))
        W, H = CONFIG['width'], CONFIG['height']
        
    pygame.display.set_caption("Interactive Art: The Small Presence")
    clock = pygame.time.Clock()

    # 폰트 설정 (명조체 계열 우선 탐색)
    try:
        # 윈도우/맥 공통적으로 있는 명조 계열 폰트 시도
        possible_fonts = ['georgia', 'batang', 'gungsuh', 'timesnewroman']
        font_path = None
        for f in possible_fonts:
            match = pygame.font.match_font(f)
            if match:
                font_path = match
                break
        
        font = pygame.font.Font(font_path, 30) if font_path else pygame.font.SysFont(None, 30)
    except:
        font = pygame.font.SysFont(None, 30)

    # --- 카메라 설정 ---
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CONFIG['cam_width'])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CONFIG['cam_height'])
    
    ret, prev_frame = cap.read()
    if ret:
        prev_frame = cv2.resize(prev_frame, (CONFIG['cam_width'], CONFIG['cam_height']))
        prev_frame = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        prev_frame = cv2.flip(prev_frame, 1)

    # --- 오디오 설정 ---
    p = pyaudio.PyAudio()
    try:
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
    except:
        print("마이크를 찾을 수 없습니다.")
        stream = None

    particles = []
    hue = 0
    volume = 0
    
    subtitle_index = 0
    subtitle_timer = time.time()
    current_subtitle = SUBTITLES[0]
    subtitle_alpha = 0
    subtitle_fading_in = True

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        # 오디오 볼륨
        if stream:
            try:
                if stream.get_read_available() > 0:
                    data = np.frombuffer(stream.read(1024, exception_on_overflow=False), dtype=np.int16)
                    volume = np.abs(data).mean() / 10 
                else:
                    volume *= 0.9 
            except:
                pass
        
        # 모션 감지
        ret, frame = cap.read()
        if ret:
            small_frame = cv2.resize(frame, (CONFIG['cam_width'], CONFIG['cam_height']))
            gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.flip(gray, 1)

            frame_diff = cv2.absdiff(prev_frame, gray)
            _, thresh = cv2.threshold(frame_diff, CONFIG['motion_sensitivity'], 255, cv2.THRESH_BINARY)
            
            ys, xs = np.where(thresh[::CONFIG['skip_pixels'], ::CONFIG['skip_pixels']] > 0)
            
            if len(xs) > 0:
                scale_x = W / (CONFIG['cam_width'] / CONFIG['skip_pixels'])
                scale_y = H / (CONFIG['cam_height'] / CONFIG['skip_pixels'])
                
                num_to_spawn = min(len(xs), 5) 
                indices = np.random.choice(len(xs), num_to_spawn)
                
                for i in indices:
                    if len(particles) < CONFIG['max_particles']:
                        px = xs[i] * scale_x + random.randint(-10, 10)
                        py = ys[i] * scale_y + random.randint(-10, 10)
                        particles.append(Particle(px, py, volume, hue))

            prev_frame = gray

        # 그리기
        fade_surface = pygame.Surface((W, H), pygame.SRCALPHA)
        fade_surface.fill((0, 0, 0, 40)) 
        screen.blit(fade_surface, (0, 0))

        hue += 0.5 # 색상 변화 속도 HTML과 비슷하게
        center_color = (
            int(math.sin(hue * 0.05) * 60 + 60),
            int(math.sin(hue * 0.05 + 2) * 60 + 60),
            int(math.sin(hue * 0.05 + 4) * 80 + 100)
        )
        
        # [수정] 중앙 원 크기: 화면 비율에 맞춰 반응성 대폭 확대 (HTML 최종본 반영)
        base_radius = min(W, H) * 0.15  # 화면 크기의 15%
        reaction_radius = volume * 4    # 반응성 키움
        pygame.draw.circle(screen, center_color, (W//2, H//2), int(base_radius + reaction_radius), 5)

        for p in particles[:]:
            p.update()
            p.draw(screen)
            if p.life <= 0:
                particles.remove(p)

        # 자막 처리
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
            
        # 자막 렌더링 (그림자 추가됨)
        lines = current_subtitle.split('\n')
        text_y = H * 0.75 # 위치 약간 조정
        for line in lines:
            draw_text_with_shadow(screen, line, font, W//2, text_y, subtitle_alpha)
            text_y += 40 

        pygame.display.flip()
        clock.tick(60)

    cap.release()
    if stream:
        stream.stop_stream()
        stream.close()
    p.terminate()
    pygame.quit()

if __name__ == "__main__":
    main()