import pyaudio
import wave
import speech_recognition as sr
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
import os
import datetime

class AudioSTTApp:
    def __init__(self, root):
        self.root = root
        self.root.title("STT 변환기")
        self.root.geometry("600x400")
        
        self.is_recording = False
        self.transcript = ""
        self.recent_transcript = ""  # 최근 텍스트 (마지막 100자)를 저장하는 변수
        self.recent_history = []  # 최근 인식된 텍스트 히스토리를 저장하는 리스트
        self.error_count = 0  # 오류 발생 횟수를 추적하는 변수 추가
        
        # UI 구성
        self.create_widgets()
        
    def create_widgets(self):
        # 메인 프레임
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 상단 제어 프레임
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 녹음 시작/중지 버튼
        self.record_button = ttk.Button(control_frame, text="녹음 시작", command=self.toggle_recording)
        self.record_button.pack(side=tk.LEFT, padx=5)
        
        # 텍스트 초기화 버튼
        self.clear_button = ttk.Button(control_frame, text="텍스트 초기화", command=self.clear_transcript)
        self.clear_button.pack(side=tk.LEFT, padx=5)
        
        # 저장 버튼
        self.save_button = ttk.Button(control_frame, text="텍스트 저장", command=self.save_transcript)
        self.save_button.pack(side=tk.LEFT, padx=5)
        
        # 상태 표시
        self.status_label = ttk.Label(control_frame, text="대기 중")
        self.status_label.pack(side=tk.RIGHT, padx=5)
        
        # 컨텐츠 프레임 (텍스트 영역들을 담을 프레임)
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 전체 텍스트 레이블
        ttk.Label(content_frame, text="전체 텍스트:").pack(anchor=tk.W, padx=5, pady=(0, 5))
        
        # 텍스트 영역
        self.text_area = scrolledtext.ScrolledText(content_frame, wrap=tk.WORD, font=("맑은 고딕", 10), height=10)
        self.text_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 10))
        
        # 최근 텍스트 레이블 
        ttk.Label(content_frame, text="최근 인식 히스토리:").pack(anchor=tk.W, padx=5, pady=(0, 5))
        
        # 최근 텍스트 영역
        self.recent_text_area = scrolledtext.ScrolledText(content_frame, wrap=tk.WORD, font=("맑은 고딕", 10), height=5)
        self.recent_text_area.pack(fill=tk.X, padx=5)
        
        # 디바이스 정보 표시
        self.show_available_devices()
        
    def show_available_devices(self):
        # 디바이스 정보 프레임
        device_frame = ttk.LabelFrame(self.root, text="사용 가능한 오디오 장치")
        device_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # 스크롤 가능한 텍스트 영역
        device_text = scrolledtext.ScrolledText(device_frame, height=5, wrap=tk.WORD)
        device_text.pack(fill=tk.X, expand=True)
        
        # 디바이스 정보 가져오기
        try:
            p = pyaudio.PyAudio()
            device_info = "사용 가능한 오디오 입력 장치:\n"
            
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info.get('maxInputChannels') > 0:  # 입력 장치만 표시
                    device_info += f"장치 {i}: {info.get('name')}\n"
                    if "스테레오 믹스" in info.get('name') or "Stereo Mix" in info.get('name'):
                        device_info += "   (스피커 출력 캡처에 사용 가능)\n"
            
            device_text.insert(tk.END, device_info)
            p.terminate()
        except Exception as e:
            device_text.insert(tk.END, f"오디오 장치 정보를 가져오는 중 오류 발생: {str(e)}")
        
    def toggle_recording(self):
        if self.is_recording:
            self.is_recording = False
            self.record_button.config(text="녹음 시작")
            self.status_label.config(text="대기 중")
        else:
            self.is_recording = True
            self.record_button.config(text="녹음 중지")
            self.status_label.config(text="녹음 중...")
            
            # 백그라운드 스레드에서 녹음 및 STT 변환 실행
            threading.Thread(target=self.record_and_transcribe, daemon=True).start()
    
    def record_and_transcribe(self):
        try:
            # PyAudio 설정
            p = pyaudio.PyAudio()
            
            # 스테레오 믹스 장치 찾기
            loopback_device_index = None
            for i in range(p.get_device_count()):
                device_info = p.get_device_info_by_index(i)
                device_name = device_info.get("name", "")
                if "스테레오 믹스" in device_name or "Stereo Mix" in device_name:
                    loopback_device_index = i
                    break
            
            if loopback_device_index is None:
                self.update_status("스테레오 믹스 장치를 찾을 수 없습니다. Windows 사운드 설정에서 활성화하세요.")
                self.is_recording = False
                self.record_button.config(text="녹음 시작")
                return
            
            # 오디오 스트림 설정
            CHUNK = 1024
            FORMAT = pyaudio.paInt16
            CHANNELS = 2
            RATE = 44100
            RECORD_SECONDS = 10  # 10초 단위로 녹음 후 변환
            
            stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        input_device_index=loopback_device_index,
                        frames_per_buffer=CHUNK)
            
            self.update_status("녹음 시작...")
            
            r = sr.Recognizer()
            
            # 녹음 루프
            while self.is_recording:
                frames = []
                for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
                    if not self.is_recording:
                        break
                    data = stream.read(CHUNK)
                    frames.append(data)
                
                if not frames:
                    continue
                
                # 임시 WAV 파일로 저장
                temp_wav = "temp_audio.wav"
                with wave.open(temp_wav, "wb") as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(p.get_sample_size(FORMAT))
                    wf.setframerate(RATE)
                    wf.writeframes(b''.join(frames))
                
                # STT 변환
                try:
                    with sr.AudioFile(temp_wav) as source:
                        audio = r.record(source)
                        text = r.recognize_google(audio, language="ko-KR")
                        self.update_transcript(text, success=True)  # 성공 플래그 추가
                except sr.UnknownValueError:
                    self.update_status("음성을 인식할 수 없습니다.")
                    self.error_count += 1  # 오류 카운트 증가
                except sr.RequestError:
                    self.update_status("Google STT 서비스에 접근할 수 없습니다.")
                    self.error_count += 1  # 오류 카운트 증가
                
                # 임시 파일 삭제
                try:
                    os.remove(temp_wav)
                except:
                    pass
            
            # 스트림 정리
            stream.stop_stream()
            stream.close()
            p.terminate()
            
        except Exception as e:
            self.update_status(f"오류 발생: {str(e)}")
            self.error_count += 1  # 오류 카운트 증가
            self.is_recording = False
            self.record_button.config(text="녹음 시작")
    
    def update_transcript(self, text, success=False):
        # 현재 시간 가져오기
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        # 성공적인 인식이고 이전에 오류가 2회 이상 발생했을 경우 줄바꿈 추가
        if success and self.error_count >= 2:
            self.transcript += "\n" + text + " "
            self.error_count = 0  # 오류 카운트 초기화
        else:
            self.transcript += text + " "
            
        # 마지막 100자 추출하여 recent_transcript 업데이트
        if len(self.transcript) <= 100:
            self.recent_transcript = self.transcript
        else:
            self.recent_transcript = self.transcript[-100:]
        
        # 인식된 텍스트를 히스토리에 추가 (타임스탬프 포함)
        if text.strip():  # 빈 텍스트가 아닌 경우만 추가
            self.recent_history.append(f"[{current_time}] {text}")
            # 최대 20개 항목만 유지
            if len(self.recent_history) > 20:
                self.recent_history = self.recent_history[-20:]
            
        # 전체 텍스트 영역 업데이트
        self.text_area.delete(1.0, tk.END)
        self.text_area.insert(tk.END, self.transcript)
        self.text_area.see(tk.END)
        
        # 최근 텍스트 히스토리 영역 업데이트
        self.recent_text_area.delete(1.0, tk.END)
        self.recent_text_area.insert(tk.END, "\n".join(self.recent_history))
        self.recent_text_area.see(tk.END)
    
    def update_status(self, message):
        self.root.after(0, lambda: self.status_label.config(text=message))
    
    def clear_transcript(self):
        self.transcript = ""
        self.recent_transcript = ""  # recent_transcript도 함께 초기화
        self.recent_history = []  # 히스토리도 초기화
        self.text_area.delete(1.0, tk.END)
        self.recent_text_area.delete(1.0, tk.END)  # 최근 텍스트 영역도 초기화
    
    def save_transcript(self):
        filename = "transcript.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(self.transcript)
        self.update_status(f"텍스트가 {filename}에 저장되었습니다")

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioSTTApp(root)
    root.mainloop() 