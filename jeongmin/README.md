# jeongmin — 로봇 담당 (이정민)

Yahboom **Raspbot V2** + **Raspberry Pi 5** 로봇 파트. 다른 역할(AI · 웹 · 앱)이 로봇을 쓸 수 있게 **HTTP 로 조종하는 서버**를 제공한다.
작업은 `jeongmin` 브랜치에서 하고 Pull Request 로 main 에 합친다.

```
jeongmin/
├── README.md               이 문서
├── docs/
│   ├── robot-specs.md      로봇 성능 메모 (확인된 사양 + 조립 후 측정할 항목)
│   ├── kj-ideas.md         KJ법 아이디어 5개
│   └── troubleshooting.md  라즈베리파이·라즈봇 문제 해결 기록
└── robot/
    ├── requirements.txt
    ├── client.py           다른 역할이 파이썬으로 로봇을 부르는 클라이언트 (설치 불필요)
    ├── find_robot.py       같은 Wi-Fi 에서 로봇 IP 찾기 (노트북에서)
    ├── server/             FastAPI 조종 서버 + 조종 화면(static/)
    │   ├── main.py         API, 자동 정지 타이머
    │   ├── drivers.py      RealDriver(raspbot 라이브러리) / FakeDriver(하드웨어 없이)
    │   └── camera.py       카메라 모듈 3(picamera2) → USB 웹캠(OpenCV) → 없음
    ├── scripts/
    │   ├── hw_test.py      하드웨어 단계별 점검 (라즈베리파이에서)
    │   ├── wifi.sh         핫스팟 등 Wi-Fi 미리 등록·확인 (라즈베리파이에서)
    │   └── autostart.sh    전원 켜면 조종 서버 자동 실행 (라즈베리파이에서)
    └── tests/              가짜 로봇으로 하는 서버 테스트
```

## 실행

**노트북 (하드웨어 없이, 가짜 모드)**
```powershell
cd jeongmin/robot
python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
$env:ROBOT_MODE="fake"; .\.venv\Scripts\uvicorn server.main:app --port 8000
# → http://127.0.0.1:8000 (조종 화면), http://127.0.0.1:8000/docs (API 문서)
.\.venv\Scripts\python -m pytest -q
```

**라즈베리파이 (실제 로봇)** — 가상환경 `~/raspbot-venv` 에 `raspbot`, `picamera2` 가 준비돼 있다.
```bash
cd ~/ai2-8/jeongmin/robot
~/raspbot-venv/bin/pip install "fastapi[standard]"
~/raspbot-venv/bin/python scripts/hw_test.py              # 처음 한 번: 바퀴 띄우고 단계별 점검
~/raspbot-venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
# → 같은 Wi-Fi 의 휴대폰/노트북에서 http://<라즈베리파이 IP>:8000
```

| 환경변수 | 기본 | 뜻 |
| --- | --- | --- |
| `ROBOT_MODE` | 자동 (I2C 있으면 real) | `real` / `fake` |
| `MAX_SPEED` | `150` | 속도 상한 (0~255) |
| `OBSTACLE_CM` | `15` | 앞쪽 이동 중 이 거리(cm)보다 가까우면 멈춤. `0` 이면 끔 |
| `CORS_ORIGINS` | (없음) | 브라우저로 API 를 부를 **팀원 웹 주소**, 쉼표로 여러 개. 예) `http://localhost:5173,http://127.0.0.1:5500` |

자동 실행(`autostart.sh`)일 때는 `robot/robot.env.example` 을 `robot/robot.env` 로 복사해서 고치고 `sudo systemctl restart raspbot`.

**팀원 웹에서 부를 때 (CORS)**: 브라우저는 다른 주소의 페이지가 로봇 API 를 부르는 것을 막는다. 팀원 웹 주소를 `CORS_ORIGINS` 에 넣어야 한다 (파이썬·앱에서 부를 때는 필요 없음).
`https` 로 배포된 사이트(Vercel 등)에서 `http://<로봇 IP>` 는 CORS 와 별개로 브라우저가 막는다 → 팀원 웹은 노트북에서 `http://localhost…` 로 띄우거나 로봇 서버에 넣어서 쓴다.
| `CAMERA` | `auto` | `picamera` / `usb` / `none` |
| `CAMERA_INDEX` | `0` | USB 웹캠 번호 |

## 조작 전 준비: 학교·발표장 Wi-Fi (집에서 미리 한 번)

라즈베리파이는 **저장된 Wi-Fi 에만** 붙는다. 집 Wi-Fi 로 SSH 접속한 상태에서 휴대폰 핫스팟을 미리 등록해 둔다.

```bash
cd ~/ai2-8/jeongmin/robot
bash scripts/wifi.sh scan        # 핫스팟을 켜 두고 → 목록에 보이는지
bash scripts/wifi.sh add         # SSID·비밀번호·우선순위 입력 (sudo 비밀번호는 사람이)
bash scripts/wifi.sh list        # 집(0) + 핫스팟(10) 이 저장됐는지
bash scripts/autostart.sh install   # 전원만 켜면 조종 서버가 뜨게 (선택)
```

현장에서는:
1. 휴대폰 핫스팟 켜기 → 라즈베리파이 전원 → 1분 기다리기
2. 노트북도 같은 핫스팟에 연결 → `python find_robot.py` → `★ 로봇 조종 서버: http://…:8000` 주소로 접속
   (휴대폰에서는 `http://<호스트이름>.local:8000` 도 대부분 된다)
3. 조종 화면에서 상태가 "실제 로봇" 인지 확인하고 시작

주의: 아이폰 핫스팟은 **'호환성 최대화'** 켜기. 핫스팟 이름·비밀번호를 바꾸면 다시 `wifi.sh add`. Wi-Fi 비밀번호는 이 저장소에 적지 않는다.

## API (다른 역할이 로봇을 쓰는 방법)

| 메서드 | 주소 | 본문 / 결과 |
| --- | --- | --- |
| POST | `/api/move` | `{"action": "forward", "speed": 100, "duration_ms": 500}` → **duration 뒤 자동 정지** |
| POST | `/api/stop` | 즉시 정지 |
| GET | `/api/status` | `mode, moving, speed, pan, tilt, led, camera, max_speed, blocked, obstacle_cm` (`blocked` = 장애물 때문에 멈춤) |
| POST | `/api/servo` | `{"pan": 0~180, "tilt": 0~110}` (90 = 정면, 둘 중 하나만 보내도 됨) |
| GET | `/api/distance` | `{"cm": 42.3}` 초음파 |
| GET | `/api/line` | `{"sensors": [false, true, true, false]}` 바닥 라인 센서 (왼→오) |
| POST | `/api/beep` | `{"ms": 150}` |
| POST | `/api/led` | `{"color": "red"\|"green"\|"blue"\|"yellow"\|"purple"\|"cyan"\|"white"\|null}` |
| GET | `/api/camera.jpg` | 사진 한 장 (카메라 없으면 503) |
| GET | `/api/stream` | MJPEG 실시간 영상 (`<img src>` 로 바로 표시) |

`action` 종류: `forward`, `backward`, `turn_left`, `turn_right`, `strafe_left`, `strafe_right`(옆 이동), `diag_forward_left`, `diag_forward_right`, `diag_backward_left`, `diag_backward_right`

**계속 움직이려면 0.2~0.5초마다 같은 명령을 다시 보낸다.** 보내지 않으면 멈춘다 (연결이 끊겨도 안전하게 서도록 일부러 이렇게 만들었다).
**앞에 물체가 `OBSTACLE_CM` 보다 가까우면** 앞쪽 이동(`forward`, `diag_forward_*`)은 거절되고 `blocked: true` 가 온다. 뒤·옆·회전은 된다.

파이썬에서는 `robot/client.py` 를 복사해 쓰면 위 규칙을 알아서 지킨다:
```python
from client import RobotClient
bot = RobotClient("http://<라즈베리파이 IP>:8000")
bot.move("forward", speed=100, seconds=2)   # 2초 앞으로, 끝나면 정지 (3초 넘어도 됨)
bot.servo(pan=60); bot.snapshot("now.jpg")   # 카메라 돌려서 사진 저장 → AI 인식에 사용
if bot.distance() < 20: bot.beep()
```
웹(자바스크립트)에서는 `fetch("/api/move", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...})})` — `server/static/app.js` 가 예시.

## 상태 (2026-10-28)

- [x] 라즈베리파이 OS 설치, Wi-Fi·SSH(키 로그인), I2C 켜기, `raspbot` 라이브러리 설치
- [x] 조종 서버 · 조종 화면 · 가짜 모드 · 테스트 (8개 통과)
- [x] 장애물 자동 정지(초음파), 팀원용 파이썬 클라이언트
- [ ] 라즈봇 조립 (라즈베리파이 장착 직전에서 멈춤)
- [ ] `hw_test.py` 로 실제 하드웨어 점검 → `docs/robot-specs.md` 측정값 채우기 (`OBSTACLE_CM` 도 실제 제동 거리 보고 조정)
- [x] Wi-Fi 등록(`wifi.sh`)·자동 실행(`autostart.sh`)·로봇 찾기(`find_robot.py`) 도구
- [ ] 위 도구로 휴대폰 핫스팟 실제 등록 + 자동 실행 켜기 (라즈베리파이에서, sudo 필요)
- [ ] 최종 아이디어가 정해지면 로봇 동작(라인 따라가기, 물체 쪽으로 가기 등)을 API 로 추가

## AI 코딩 도우미에게 (이 폴더를 수정할 때 지킬 것)

- **브랜치 규칙**: main 에 직접 push 하지 않는다. `jeongmin` 브랜치에서 작업 → Pull Request. 다른 사람 폴더는 고치지 않는다.
- **비밀값 금지**: Wi-Fi 이름·비밀번호, 라즈베리파이 비밀번호, API 키, 라즈베리파이 IP·사용자 이름을 커밋하지 않는다 (공개 저장소).
- **하드웨어 기능을 추가할 때** `drivers.py` 의 `FakeDriver` 와 `RealDriver` 에 **같은 메서드**를 넣고, `tests/` 에 가짜 모드 테스트를 추가한다. 테스트는 하드웨어 없이 돌아야 한다.
- **안전**: 이동 명령에는 항상 자동 정지(duration)를 둔다. 속도 상한(`MAX_SPEED`)과 장애물 정지(`OBSTACLE_CM`)를 없애지 않는다. 처음 모터를 돌릴 때는 바퀴를 띄운 상태라고 사람에게 확인받는다.
- **재부팅·종료**: 라즈베리파이를 재부팅·종료하기 전에 사람에게 묻고, 항상 "**라즈베리파이** 재부팅" 처럼 어느 장치인지 밝힌다. `sudo` 는 비밀번호가 필요하므로 사람이 직접 실행한다.
- 라즈봇 라이브러리는 `raspbot` 0.1.2 (비공식, I2C 0x2B). 함수 이름은 `drivers.py` 에 정리돼 있다. 서보 위아래는 110° 가 한계.
