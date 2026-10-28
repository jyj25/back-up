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
    ├── server/             FastAPI 조종 서버 + 조종 화면(static/)
    │   ├── main.py         API, 자동 정지 타이머
    │   ├── drivers.py      RealDriver(raspbot 라이브러리) / FakeDriver(하드웨어 없이)
    │   └── camera.py       카메라 모듈 3(picamera2) → USB 웹캠(OpenCV) → 없음
    ├── scripts/hw_test.py  하드웨어 단계별 점검 (라즈베리파이에서)
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
| `CAMERA` | `auto` | `picamera` / `usb` / `none` |
| `CAMERA_INDEX` | `0` | USB 웹캠 번호 |

## API (다른 역할이 로봇을 쓰는 방법)

| 메서드 | 주소 | 본문 / 결과 |
| --- | --- | --- |
| POST | `/api/move` | `{"action": "forward", "speed": 100, "duration_ms": 500}` → **duration 뒤 자동 정지** |
| POST | `/api/stop` | 즉시 정지 |
| GET | `/api/status` | `mode, moving, speed, pan, tilt, led, camera, max_speed` |
| POST | `/api/servo` | `{"pan": 0~180, "tilt": 0~110}` (90 = 정면, 둘 중 하나만 보내도 됨) |
| GET | `/api/distance` | `{"cm": 42.3}` 초음파 |
| GET | `/api/line` | `{"sensors": [false, true, true, false]}` 바닥 라인 센서 (왼→오) |
| POST | `/api/beep` | `{"ms": 150}` |
| POST | `/api/led` | `{"color": "red"\|"green"\|"blue"\|"yellow"\|"purple"\|"cyan"\|"white"\|null}` |
| GET | `/api/camera.jpg` | 사진 한 장 (카메라 없으면 503) |
| GET | `/api/stream` | MJPEG 실시간 영상 (`<img src>` 로 바로 표시) |

`action` 종류: `forward`, `backward`, `turn_left`, `turn_right`, `strafe_left`, `strafe_right`(옆 이동), `diag_forward_left`, `diag_forward_right`, `diag_backward_left`, `diag_backward_right`

예) 파이썬에서 2초 동안 앞으로:
```python
import httpx
httpx.post("http://<라즈베리파이 IP>:8000/api/move", json={"action": "forward", "speed": 100, "duration_ms": 2000})
```
**계속 움직이려면 0.2~0.5초마다 같은 명령을 다시 보낸다.** 보내지 않으면 멈춘다 (연결이 끊겨도 안전하게 서도록 일부러 이렇게 만들었다).

## 상태 (2026-10-28)

- [x] 라즈베리파이 OS 설치, Wi-Fi·SSH(키 로그인), I2C 켜기, `raspbot` 라이브러리 설치
- [x] 조종 서버 · 조종 화면 · 가짜 모드 · 테스트 (6개 통과)
- [ ] 라즈봇 조립 (라즈베리파이 장착 직전에서 멈춤)
- [ ] `hw_test.py` 로 실제 하드웨어 점검 → `docs/robot-specs.md` 측정값 채우기
- [ ] 학교·발표장용 Wi-Fi(휴대폰 핫스팟) 라즈베리파이에 추가
- [ ] 최종 아이디어가 정해지면 로봇 동작(라인 따라가기, 물체 쪽으로 가기 등)을 API 로 추가

## AI 코딩 도우미에게 (이 폴더를 수정할 때 지킬 것)

- **브랜치 규칙**: main 에 직접 push 하지 않는다. `jeongmin` 브랜치에서 작업 → Pull Request. 다른 사람 폴더는 고치지 않는다.
- **비밀값 금지**: Wi-Fi 이름·비밀번호, 라즈베리파이 비밀번호, API 키, 라즈베리파이 IP·사용자 이름을 커밋하지 않는다 (공개 저장소).
- **하드웨어 기능을 추가할 때** `drivers.py` 의 `FakeDriver` 와 `RealDriver` 에 **같은 메서드**를 넣고, `tests/` 에 가짜 모드 테스트를 추가한다. 테스트는 하드웨어 없이 돌아야 한다.
- **안전**: 이동 명령에는 항상 자동 정지(duration)를 둔다. 속도 상한(`MAX_SPEED`)을 없애지 않는다. 처음 모터를 돌릴 때는 바퀴를 띄운 상태라고 사람에게 확인받는다.
- **재부팅·종료**: 라즈베리파이를 재부팅·종료하기 전에 사람에게 묻고, 항상 "**라즈베리파이** 재부팅" 처럼 어느 장치인지 밝힌다. `sudo` 는 비밀번호가 필요하므로 사람이 직접 실행한다.
- 라즈봇 라이브러리는 `raspbot` 0.1.2 (비공식, I2C 0x2B). 함수 이름은 `drivers.py` 에 정리돼 있다. 서보 위아래는 110° 가 한계.
