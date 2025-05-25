import pyaudio
import wave
import speech_recognition as sr
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
import os
import datetime
from openai import OpenAI
import time
import queue
import collections
import pynput
from pynput import mouse

class AudioSTTApp:
    def __init__(self, root):
        self.root = root
        self.root.title("STT 변환기")
        self.root.geometry("800x600")  # 창 크기 확대
        
        # STT 처리 간격 설정 (초)
        self.RECORD_SECONDS = 5  # 5초마다 처리
        
        self.is_recording = False
        self.transcript = ""
        self.recent_transcript = ""  # 최근 텍스트 (마지막 300자)를 저장하는 변수
        self.recent_history = []  # 마지막 300자 텍스트 히스토리를 저장하는 리스트 (ChatGPT에 전송되는 내용)
        self.error_count = 0  # 오류 발생 횟수를 추적하는 변수 추가
        
        # 오디오 스트리밍을 위한 변수들
        self.audio_queue = queue.Queue()
        self.audio_buffer = collections.deque(maxlen=44100*2*2*self.RECORD_SECONDS)  # 설정된 시간만큼 버퍼 (44.1kHz, 16bit, 2ch)
        self.recording_lock = threading.Lock()
        
        # ChatGPT 관련 변수
        self.chatgpt_api_key = ""
        self.chatgpt_prompt = "적절한 답장을 해라"
        self.chatgpt_response = ""
        
        # 마우스 움직임 감지 관련 변수
        self.isGPT = False  # ChatGPT 호출 플래그
        self.last_mouse_pos = None  # 마지막 마우스 위치
        self.mouse_listener = None  # 마우스 리스너
        
        # UI 구성
        self.create_widgets()
        
        # 마우스 움직임 감지 시작
        self.start_mouse_listener()
        
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
        
        # ChatGPT 요청 버튼
        self.chatgpt_button = ttk.Button(control_frame, text="AI 응답 요청", command=self.request_chatgpt_response)
        self.chatgpt_button.pack(side=tk.LEFT, padx=5)
        
        # 상태 표시
        self.status_label = ttk.Label(control_frame, text="대기 중")
        self.status_label.pack(side=tk.RIGHT, padx=5)
        
        # API 키 프레임
        api_frame = ttk.Frame(main_frame)
        api_frame.pack(fill=tk.X, pady=(0, 10))
        
        # API 키 입력 필드
        ttk.Label(api_frame, text="OpenAI API 키:").pack(side=tk.LEFT, padx=5)
        self.api_key_entry = ttk.Entry(api_frame, width=50, show="*")
        self.api_key_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # 기본 API 키 값 설정
        self.api_key_entry.insert(0, "")  # "귀찮으면 여기다 미리 API 키를 넣으시오 (* 대신 키값 그대로 깃허브에 푸시하면 인생망함)
        
        # 컨텐츠 프레임 (텍스트 영역들을 담을 프레임)
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 전체 텍스트 레이블 (숨김 처리)
        # ttk.Label(content_frame, text="전체 텍스트:").pack(anchor=tk.W, padx=5, pady=(0, 5))
        
        # 텍스트 영역 (숨김 처리)
        # self.text_area = scrolledtext.ScrolledText(content_frame, wrap=tk.WORD, font=("맑은 고딕", 10), height=5)
        # self.text_area.pack(fill=tk.X, padx=5, pady=(0, 10))
        
        # 전체 텍스트 레이블 (시간대별 정리)
        ttk.Label(content_frame, text="전체 텍스트:").pack(anchor=tk.W, padx=5, pady=(0, 5))
        
        # 전체 텍스트 영역 (시간대별 정리)
        self.recent_text_area = scrolledtext.ScrolledText(content_frame, wrap=tk.WORD, font=("맑은 고딕", 10), height=5)
        self.recent_text_area.pack(fill=tk.X, padx=5, pady=(0, 10))
        
        # ChatGPT 응답 레이블
        ttk.Label(content_frame, text="AI 응답:").pack(anchor=tk.W, padx=5, pady=(0, 5))
        
        # ChatGPT 응답 영역 (화면 꽉 차게!)
        self.chatgpt_response_area = scrolledtext.ScrolledText(content_frame, wrap=tk.WORD, font=("맑은 고딕", 10), height=20, bg="#f8f8f8")
        self.chatgpt_response_area.pack(fill=tk.BOTH, expand=True, padx=5)
        
        # 디바이스 정보 표시
        # self.show_available_devices()
    
    def start_mouse_listener(self):
        """마우스 움직임 감지 시작"""
        def on_move(x, y):
            if self.last_mouse_pos is None:
                self.last_mouse_pos = (x, y)
                return
            
            # 마우스가 움직였는지 확인 (약간의 임계값 설정)
            dx = abs(x - self.last_mouse_pos[0])
            dy = abs(y - self.last_mouse_pos[1])
            
            if dx > 10 or dy > 10:  # 10픽셀 이상 움직였을 때만 감지
                if not self.isGPT:  # 현재 GPT 호출 중이 아닐 때만
                    print(f"[DEBUG] 마우스 움직임 감지! 위치: ({x}, {y})")
                    self.isGPT = True
                    self.update_status("마우스 감지됨 - AI 답변 준비 중...")
                
                self.last_mouse_pos = (x, y)
        
        # 마우스 리스너 시작
        self.mouse_listener = mouse.Listener(on_move=on_move)
        self.mouse_listener.start()
        print("[DEBUG] 마우스 움직임 감지 시작됨")
    
    def stop_mouse_listener(self):
        """마우스 움직임 감지 중지"""
        if self.mouse_listener:
            self.mouse_listener.stop()
            print("[DEBUG] 마우스 움직임 감지 중지됨")
        
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
            
            stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        input_device_index=loopback_device_index,
                        frames_per_buffer=CHUNK)
            
            self.update_status("녹음 시작...")
            
            # OpenAI Whisper 사용을 위한 클라이언트 설정
            api_key = self.api_key_entry.get().strip()
            if not api_key:
                self.update_status("OpenAI API 키가 필요합니다.")
                self.is_recording = False
                self.record_button.config(text="녹음 시작")
                return
            
            # STT 처리 스레드 시작
            stt_thread = threading.Thread(target=self.stt_processor, args=(api_key,), daemon=True)
            stt_thread.start()
            
            # 연속 오디오 수집 루프 (절대 멈추지 않음)
            print("[DEBUG] 연속 오디오 수집 시작...")
            while self.is_recording:
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    
                    # 오디오 데이터를 버퍼에 추가
                    with self.recording_lock:
                        for byte in data:
                            self.audio_buffer.append(byte)
                    
                    # 큐에도 추가 (STT 처리용)
                    self.audio_queue.put(data)
                    
                except Exception as e:
                    print(f"[ERROR] 오디오 읽기 오류: {str(e)}")
                    continue
            
            # 스트림 정리
            stream.stop_stream()
            stream.close()
            p.terminate()
            print("[DEBUG] 오디오 수집 종료")
            
        except Exception as e:
            print(f"[ERROR] 녹음 오류: {str(e)}")
            self.update_status(f"오류 발생: {str(e)}")
            self.error_count += 1
            self.is_recording = False
            self.record_button.config(text="녹음 시작")
    
    def stt_processor(self, api_key):
        """별도 스레드에서 STT 처리"""
        client = OpenAI(api_key=api_key)
        RATE = 44100
        CHANNELS = 2
        FORMAT = pyaudio.paInt16
        
        # PyAudio 인스턴스 생성 (sample width 얻기 위해)
        p = pyaudio.PyAudio()
        sample_width = p.get_sample_size(FORMAT)
        p.terminate()
        
        print("[DEBUG] STT 처리 스레드 시작...")
        
        last_process_time = time.time()
        
        while self.is_recording:
            current_time = time.time()
            
            # 설정된 간격마다 처리
            if current_time - last_process_time >= self.RECORD_SECONDS:
                try:
                    # 현재 버퍼에서 설정된 시간분 데이터 추출
                    with self.recording_lock:
                        if len(self.audio_buffer) > 0:
                            # 버퍼의 모든 데이터를 복사 (최대 설정된 시간분)
                            audio_data = bytes(self.audio_buffer)
                        else:
                            audio_data = b''
                    
                    if len(audio_data) > 0:
                        # 임시 WAV 파일로 저장
                        temp_wav = f"temp_audio_{int(current_time)}.wav"
                        try:
                            with wave.open(temp_wav, "wb") as wf:
                                wf.setnchannels(CHANNELS)
                                wf.setsampwidth(sample_width)
                                wf.setframerate(RATE)
                                wf.writeframes(audio_data)
                            
                            # OpenAI Whisper STT 변환
                            print(f"[DEBUG] OpenAI Whisper STT 변환 시작... (파일 크기: {len(audio_data)} bytes)")
                            
                            with open(temp_wav, "rb") as audio_file:
                                transcript = client.audio.transcriptions.create(
                                    model="whisper-1",
                                    file=audio_file,
                                    language="ko"
                                )
                            
                            text = transcript.text
                            print(f"[DEBUG] Whisper STT 결과: '{text}'")
                            
                            if text.strip():
                                self.update_transcript(text, success=True)
                                self.error_count = 0
                                
                                # 마우스 움직임이 감지되었을 때만 ChatGPT API 호출
                                if self.isGPT and self.recent_transcript.strip():
                                    print("[DEBUG] 마우스 트리거로 ChatGPT API 호출 시작...")
                                    threading.Thread(target=self._call_chatgpt_api, args=(api_key, self.recent_transcript), daemon=True).start()
                            else:
                                print("[DEBUG] 빈 텍스트 결과, 건너뜀")
                                
                        except Exception as stt_error:
                            print(f"[ERROR] Whisper STT 오류: {str(stt_error)}")
                            self.update_status(f"음성 인식 오류: {str(stt_error)}")
                            self.error_count += 1
                        
                        finally:
                            # 임시 파일 삭제
                            try:
                                os.remove(temp_wav)
                            except:
                                pass
                    
                    last_process_time = current_time
                    
                except Exception as e:
                    print(f"[ERROR] STT 처리 오류: {str(e)}")
            
            # 0.1초 대기 (이거 없으면 while문 미친듯이 돌면서 CPU 100% 소모함;;)
            time.sleep(0.1)
        
        print("[DEBUG] STT 처리 스레드 종료")
    
    def update_transcript(self, text, success=False):
        # 현재 시간 가져오기
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        # 성공적인 인식이고 이전에 오류가 2회 이상 발생했을 경우 줄바꿈 추가
        if success and self.error_count >= 2:
            self.transcript += "\n" + text + " "
            self.error_count = 0  # 오류 카운트 초기화
        else:
            self.transcript += text + " "
            
        # 마지막 300자 추출하여 recent_transcript 업데이트
        if len(self.transcript) <= 300:
            self.recent_transcript = self.transcript
        else:
            self.recent_transcript = self.transcript[-300:]
        
        # STT 결과를 시간대별 히스토리에 추가
        if text.strip():  # 빈 텍스트가 아닌 경우만 추가
            # 새로운 STT 결과를 시간과 함께 히스토리에 추가
            self.recent_history.append(f"[{current_time}] {text.strip()}")
            # 최대 20개 항목만 유지
            if len(self.recent_history) > 20:
                self.recent_history = self.recent_history[-20:]
            
        # 전체 텍스트 영역 업데이트 (숨김 처리로 주석)
        # self.text_area.delete(1.0, tk.END)
        # self.text_area.insert(tk.END, self.transcript)
        # self.text_area.see(tk.END)
        
        # 시간대별 전체 텍스트 영역 업데이트
        self.recent_text_area.delete(1.0, tk.END)
        self.recent_text_area.insert(tk.END, "\n".join(self.recent_history))
        self.recent_text_area.see(tk.END)
    
    def update_status(self, message):
        self.root.after(0, lambda: self.status_label.config(text=message))
    
    def clear_transcript(self):
        self.transcript = ""
        self.recent_transcript = ""  # recent_transcript도 함께 초기화
        self.recent_history = []  # 히스토리도 초기화
        self.chatgpt_response = ""  # ChatGPT 응답도 초기화
        # self.text_area.delete(1.0, tk.END)  # 기존 전체 텍스트 영역 (숨김 처리로 주석)
        self.recent_text_area.delete(1.0, tk.END)  # 시간대별 전체 텍스트 영역 초기화
        self.chatgpt_response_area.delete(1.0, tk.END)  # ChatGPT 응답 영역도 초기화
    
    def save_transcript(self):
        filename = "transcript.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(self.transcript)
        self.update_status(f"텍스트가 {filename}에 저장되었습니다")

    def request_chatgpt_response(self):
        # API 키 가져오기
        api_key = self.api_key_entry.get().strip()
        if not api_key:
            self.update_status("OpenAI API 키가 필요합니다.")
            return
        
        # 최근 텍스트가 없으면 처리하지 않음
        if not self.recent_transcript:
            self.update_status("처리할 텍스트가 없습니다.")
            return
        
        # 상태 업데이트
        self.update_status("AI 응답 요청 중...")
        
        # 백그라운드 스레드에서 API 요청 실행
        threading.Thread(target=self._call_chatgpt_api, args=(api_key, self.recent_transcript), daemon=True).start()
    
    def _call_chatgpt_api(self, api_key, text):
        try:
            # OpenAI API 설정 (새로운 방식)
            client = OpenAI(api_key=api_key)
            
            # 프롬프트 준비
            prompt = f"{self.chatgpt_prompt}\n\n텍스트: {text}"
            
            print(f"[DEBUG] ChatGPT API 호출 시작 - 텍스트 길이: {len(text)}자")  # 터미널 출력
            print(f"[DEBUG] 전송되는 텍스트: '{text}'")  # 실제 텍스트 내용 출력
            print(f"[DEBUG] 완전한 프롬프트:\n{prompt}")  # 전체 프롬프트 출력
            print("-" * 50)  # 구분선
            
            # API 호출 (새로운 방식)
            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": "질문에 답변을 해야 합니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.7
            )
            
            # 응답 추출 (새로운 방식)
            response_text = response.choices[0].message.content.strip()
            self.chatgpt_response = response_text
            
            print(f"[DEBUG] ChatGPT API 응답 성공 - 응답 길이: {len(response_text)}자")  # 터미널 출력
            print(f"[DEBUG] ChatGPT 응답 내용:\n{response_text}")  # 응답 내용도 출력
            print("=" * 50)  # 구분선
            
            # UI 업데이트 (메인 스레드에서 실행)
            self.root.after(0, self._update_chatgpt_response_area)
            self.root.after(0, lambda: self.update_status("AI 응답 완료"))
            
            # ChatGPT 호출 완료 후 플래그 리셋
            self.isGPT = False
            print("[DEBUG] ChatGPT 호출 완료, 플래그 리셋됨")
            
        except Exception as e:
            # 오류 메시지를 터미널과 UI 모두에 출력
            error_message = f"AI 응답 오류: {str(e)}"
            print(f"[ERROR] {error_message}")  # 터미널 출력
            self.root.after(0, lambda: self.update_status(error_message))
            
            # 오류 발생 시에도 플래그 리셋
            self.isGPT = False
    
    def _update_chatgpt_response_area(self):
        self.chatgpt_response_area.delete(1.0, tk.END)
        self.chatgpt_response_area.insert(tk.END, self.chatgpt_response)

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioSTTApp(root)
    root.mainloop() 