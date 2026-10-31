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
    ├── stations.json       통(정류장) 이름 ↔ 마커 번호, 찾아가기 설정값 (인쇄 마커 ArUco 4x4)
    ├── stations.blocks.json 키트 블록(AprilTag 1~4번)으로 시험할 때 (STATIONS_FILE 로 고름)
    ├── markers/            인쇄용 마커 (markers.html 을 열어 인쇄)
    ├── find_robot.py       같은 Wi-Fi 에서 로봇 IP 찾기 (노트북에서)
    ├── server/             FastAPI 조종 서버 + 조종 화면(static/)
    │   ├── main.py         API, 자동 정지 타이머
    │   ├── drivers.py      RealDriver(raspbot 라이브러리) / FakeDriver(하드웨어 없이)
    │   ├── camera.py       카메라 모듈 3(picamera2) → USB 카메라(라즈봇 기본, OpenCV, 최신 화면만) → 없음
    │   ├── vision.py       마커 찾기 (ArUco / AprilTag, 종류는 stations 파일에서)
    │   ├── navigator.py    통 찾아가기(카메라로 둘러보기) → 쏟기 → 출발점 복귀
    │   ├── sorter.py       AI 판정 → 통 임무 시작, 처리 기록
    │   ├── board.py        분류 보드(ESP32) USB 시리얼 읽기
    │   └── sim.py          가짜 모드용 2D 세계 (노트북에서 찾아가기 시험)
    ├── scripts/
    │   ├── hw_test.py      하드웨어 단계별 점검 (라즈베리파이에서)
    │   ├── wifi.sh         핫스팟 등 Wi-Fi 미리 등록·확인 (라즈베리파이에서)
    │   ├── autostart.sh    전원 켜면 조종 서버 자동 실행 (라즈베리파이에서)
    │   └── make_markers.py 인쇄용 마커 만들기 (노트북에서)
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
| `AUTO_SORT` | `0` | `1` 이면 AI 판정이 오면 자동 출발 (화면·API 로도 켜고 끔) |
| `BOARD_PORT` | 실제 `auto` / 가짜 `none` | 분류 보드 포트. `auto` = `/dev/ttyACM*` 첫 번째 |
| `HISTORY_FILE` | 실제 `data/history.jsonl` / 가짜 `none` | 처리 기록 파일 (서버를 다시 켜도 이어짐) |
| `CORS_ORIGINS` | (없음) | 브라우저로 API 를 부를 **팀원 웹 주소**, 쉼표로 여러 개. 예) `http://localhost:5173,http://127.0.0.1:5500` |
| `CAMERA` | `auto` | `picamera` / `usb` / `none`. `auto` 는 카메라 모듈 3 이 꽂혀 있으면 그걸 쓴다 → 모듈 3 을 꽂았는데 길 찾기는 USB 로 하려면 `usb` |
| `CAMERA_INDEX` | `0` | USB 웹캠 번호 |
| `STATIONS_FILE` | `stations.json` | 키트 블록으로 시험할 때 `stations.blocks.json` |
| `IR_STOP_KEY` | `0` (전원 버튼) | **리모컨 비상 정지** 버튼 코드. `none` 이면 끔 |
| `DUMP_REST` / `DUMP_ANGLE` | `0` / `90` | 쏟기 서보(S2) 평소 / 쏟을 때 각도 |
| `DUMP_SWEEP_MS` | `300` | 쏟기 서보가 90° 도는 시간 (클수록 천천히) |

자동 실행(`autostart.sh`)일 때는 `robot/robot.env.example` 을 `robot/robot.env` 로 복사해서 고치고 `sudo systemctl restart raspbot`.

**팀원 웹에서 부를 때 (CORS)**: 브라우저는 다른 주소의 페이지가 로봇 API 를 부르는 것을 막는다. 팀원 웹 주소를 `CORS_ORIGINS` 에 넣어야 한다 (파이썬·앱에서 부를 때는 필요 없음).
`https` 로 배포된 사이트(Vercel 등)에서 `http://<로봇 IP>` 는 CORS 와 별개로 브라우저가 막는다 → 팀원 웹은 노트북에서 `http://localhost…` 로 띄우거나 로봇 서버에 넣어서 쓴다.

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

## 통 찾아가기 (분리수거)

```
물건 싣기 → (C270 + AI) 종류 판단 → POST /api/mission {"station": "can"}
         → 캔 통 마커 찾기 → 다가가기 → 쏟기 → 뒤로 빠지기 → 출발점(home) 마커로 복귀
```
- 통마다 **ArUco 마커**(번호표)를 붙인다: `markers/markers.html` 인쇄, 한 변 10cm, 통 앞면 로봇 카메라 높이(약 15cm). **세워서** 붙인다 — 카메라가 정면 고정이라 바닥에 눕힌 마커는 못 읽는다.
- 이름·마커 번호·속도 등 설정은 `stations.json`. 통을 늘리면 여기에 추가하고 `python scripts/make_markers.py`.
- **키트 블록으로 시험**: 라즈봇 키트의 블록 윗면은 AprilTag 36h11 (1번 출발점, 2번 캔, 3번 페트, 4번 종이). 마커 면을 로봇 쪽으로 세우고 `STATIONS_FILE=stations.blocks.json`.
- 움직임: **조금 움직이고 → 멈춰서 보고 → 다시 판단** (`navigator.decide`). 마커가 안 보이면 **몸은 두고 카메라만 좌우로 돌려 둘러보고**(`look`), 찾으면 그쪽으로 회전한다. 그래도 없으면 제자리 회전 (12걸음마다 다시 둘러봄), 한 바퀴 반 돌아도 없으면 `failed`.
- 도착 판단: 마커가 화면 너비의 30% 이상, 마커를 정면으로 보고 초음파 25cm 이하, 또는 **크게 보이던 마커가 가까이서 사라짐**(낮은 마커가 화면 아래로 빠짐). 블록 설정은 초음파 판단을 끈다 (블록이 작아 뒤쪽 물체를 잼).
- **수동 조종·정지 버튼을 누르면 임무는 바로 취소**된다.
- **리모컨 비상 정지**: 라즈봇 키트 리모컨의 **전원 버튼** → 바퀴 정지 + 임무 취소. Wi-Fi 가 끊겨도 된다. (실측: 버튼마다 코드를 보내고 떼면 255. 전원 버튼만 코드 0 이라 "코드 없이 255" 로 알아본다.)
- **쏟기**: 고장 난 위아래 서보 자리(**S2**)에 아두이노 키트 서보(SG90)를 꽂고, 서보 팔에 트레이(두부 통 크기 PP)를 붙였다. 도착하면 노란 LED + 짧은 삐 → **반시계 90° 로 천천히 기울이기** → 1.5초 → 수평. 트레이는 OLED 반대쪽으로 쏟는다. 가벼운 것만 (SG90 약 1.6kg·cm).
- **AI 판정 받기**: 분류 보드가 USB 로 `{"class":"can","conf":0.93,"ms":173}` 한 줄을 보내면 (`{` 로 시작하지 않는 줄은 무시) — 자동 출발이 켜져 있고, 임무 중이 아니고, `class` 가 통 이름이고, 확신도가 `stations.json` 의 `sort.min_confidence`(0.8) 이상이면 출발. `class: null`·`empty`·`error`·`event` 가 `decision` 이 아닌 줄은 출발하지 않는다. 라즈베리파이에서 권한 오류가 나면 사용자를 `dialout` 그룹에 (sudo, 사람이).
- 노트북 가짜 모드에서도 `sim.py` 의 가짜 세계(출발점 뒤, 통 3개 앞)로 처음부터 끝까지 돌아간다. 조종 화면의 "통 찾아가기" 버튼으로 확인.

## API (다른 역할이 로봇을 쓰는 방법)

| 메서드 | 주소 | 본문 / 결과 |
| --- | --- | --- |
| POST | `/api/move` | `{"action": "forward", "speed": 100, "duration_ms": 500}` → **duration 뒤 자동 정지** |
| POST | `/api/stop` | 즉시 정지 |
| GET | `/api/status` | `mode, moving, speed, pan, tilt, led, camera, max_speed, blocked, obstacle_cm` (`blocked` = 장애물 때문에 멈춤) |
| POST | `/api/servo` | `{"pan": 0~180, "tilt": 0~110}` — `pan` 은 카메라 좌우 (90 정면, 클수록 왼쪽), `tilt` 는 이제 **쏟기 서보**(0 수평, 90 쏟기) |
| GET | `/api/distance` | `{"cm": 42.3}` 초음파 |
| GET | `/api/line` | `{"sensors": [false, true, true, false]}` 바닥 라인 센서 (왼→오) |
| POST | `/api/beep` | `{"ms": 150}` |
| POST | `/api/led` | `{"color": "red"\|"green"\|"blue"\|"yellow"\|"purple"\|"cyan"\|"white"\|null}` |
| GET | `/api/camera.jpg` | 사진 한 장 (카메라 없으면 503) |
| GET | `/api/stream` | MJPEG 실시간 영상 (`<img src>` 로 바로 표시) |
| GET | `/api/stations` | 정류장 목록 `{"can": {"marker": 1, "label": "캔"}, ...}` — 통 이름 = AI 분류 이름 |
| POST | `/api/mission` | `{"station": "can", "dump": true, "return_home": true}` → 202, 백그라운드로 시작 (이미 하는 중이면 409) |
| GET | `/api/mission` | `phase` (look·search·align·approach·arrived·dumping·backing·done·failed·cancelled), `message`, `running`, `seen` |
| POST | `/api/mission/cancel` | 임무 취소 + 정지 |
| POST | `/api/verdict` | 보드와 같은 판정 JSON `{"class":"can","conf":0.93}` → `{accepted, reason}` (시험용·다른 분류기) |
| GET / POST | `/api/sort` | 자동 출발 상태·보드 연결·최근 판정 / `{"auto": true}` 로 켜기 |
| GET | `/api/history` | `{"bins": {"can": 3, ...}, "items": [{id, time, label, confidence, by, result, seconds, steps, message}]}` — `by` 는 `ai`/`web`, `result` 는 `done`/`failed`/`cancelled` |
| POST | `/api/history/reset` | `{"station": "can"}` 통 비우기 (빼면 전부). 개수만 0, 기록은 남음 |
| GET | `/api/markers` | 지금 보이는 마커 `[{id, cx(-1 왼쪽~+1 오른쪽), size(화면 너비 대비)}]` |

`action` 종류: `forward`, `backward`, `turn_left`, `turn_right`, `strafe_left`, `strafe_right`(옆 이동), `diag_forward_left`, `diag_forward_right`, `diag_backward_left`, `diag_backward_right`

**계속 움직이려면 0.2~0.5초마다 같은 명령을 다시 보낸다.** 보내지 않으면 멈춘다 (연결이 끊겨도 안전하게 서도록 일부러 이렇게 만들었다).
**앞에 물체가 `OBSTACLE_CM` 보다 가까우면** 앞쪽 이동(`forward`, `diag_forward_*`)은 거절되고 `blocked: true` 가 온다. 뒤·옆·회전은 된다.

파이썬에서는 `robot/client.py` 를 복사해 쓰면 위 규칙을 알아서 지킨다:
```python
from client import RobotClient
bot = RobotClient("http://<라즈베리파이 IP>:8000")
bot.move("forward", speed=100, seconds=2)   # 2초 앞으로, 끝나면 정지 (3초 넘어도 됨)
bot.servo(pan=60); bot.snapshot("now.jpg")   # 카메라 돌려서 사진 저장 → AI 인식에 사용
result = bot.go("paper")                      # 종이 통까지 가서 쏟고 복귀, 끝날 때까지 기다림
print(result["phase"])                        # done / failed / cancelled
if bot.distance() < 20: bot.beep()
```
웹(자바스크립트)에서는 `fetch("/api/move", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...})})` — `server/static/app.js` 가 예시.

## 상태 (2026-11-01)

- [x] 라즈베리파이 OS 설치, Wi-Fi·SSH(키 로그인), I2C 켜기, `raspbot` 라이브러리 설치
- [x] 조종 서버 · 조종 화면 · 가짜 모드 · 테스트 (8개 통과)
- [x] 장애물 자동 정지(초음파), 팀원용 파이썬 클라이언트
- [x] 통 찾아가기(ArUco 마커) + 쏟기 자리 + 출발점 복귀, 가짜 세계 시뮬레이션, 인쇄용 마커
- [x] AI 판정 USB 수신 → 자동 출발(기본 꺼짐), 처리 기록 API (테스트 21개 통과)
- [x] 라즈봇 조립, 하드웨어 점검 → `docs/robot-specs.md` (위아래 서보 고장 → 그 자리를 쏟기 서보로)
- [x] 키트 블록(AprilTag) 마커 지원, 실제 카메라로 블록 1~4번 인식
- [x] 실제 로봇 찾아가기 시험에서 나온 문제 고침: USB 카메라를 picamera2 가 잡던 문제, 쌓인 예전 화면으로 판단하던 문제, 가까이서 낮은 마커를 놓치던 문제 → 카메라로 둘러보기 추가 (테스트 26개)
- [x] 리모컨 비상 정지 (전원 버튼), 쏟기 서보 + 트레이
- [ ] `OBSTACLE_CM` 을 실제 제동 거리 보고 조정
- [x] Wi-Fi 등록(`wifi.sh`)·자동 실행(`autostart.sh`)·로봇 찾기(`find_robot.py`) 도구
- [ ] 위 도구로 휴대폰 핫스팟 실제 등록 + 자동 실행 켜기 (라즈베리파이에서, sudo 필요)
- [ ] 실제 로봇으로 찾아가기 → 쏟기 → 복귀를 처음부터 끝까지 성공시키기 (선이 바퀴에 걸리지 않게 정리), `nav` 값 조정
- [ ] 쏟을 때 통 쪽으로 옆면 대기 (지금은 통을 정면으로 보고 멈춤 → 옆으로 쏟는 트레이라 회전·옆걸음 필요)

## AI 코딩 도우미에게 (이 폴더를 수정할 때 지킬 것)

- **브랜치 규칙**: main 에 직접 push 하지 않는다. `jeongmin` 브랜치에서 작업 → Pull Request. 다른 사람 폴더는 고치지 않는다.
- **비밀값 금지**: Wi-Fi 이름·비밀번호, 라즈베리파이 비밀번호, API 키, 라즈베리파이 IP·사용자 이름을 커밋하지 않는다 (공개 저장소).
- **하드웨어 기능을 추가할 때** `drivers.py` 의 `FakeDriver` 와 `RealDriver` 에 **같은 메서드**를 넣고, `tests/` 에 가짜 모드 테스트를 추가한다. 테스트는 하드웨어 없이 돌아야 한다.
- **안전**: 이동 명령에는 항상 자동 정지(duration)를 둔다. 속도 상한(`MAX_SPEED`)과 장애물 정지(`OBSTACLE_CM`)를 없애지 않는다. 처음 모터를 돌릴 때는 바퀴를 띄운 상태라고 사람에게 확인받는다.
- **재부팅·종료**: 라즈베리파이를 재부팅·종료하기 전에 사람에게 묻고, 항상 "**라즈베리파이** 재부팅" 처럼 어느 장치인지 밝힌다. `sudo` 는 비밀번호가 필요하므로 사람이 직접 실행한다.
- 찾아가기 판단은 `navigator.decide()` (순수 함수) 에 모으고 `tests/test_navigation.py` 에 경우를 추가한다. 가짜 세계 시험은 가상 시계(`VirtualClock`)로 즉시 끝난다.
- 라즈봇 라이브러리는 `raspbot` 0.1.2 (비공식, I2C 0x2B). 함수 이름은 `drivers.py` 에 정리돼 있다. S2(tilt 채널)는 110° 가 한계이고, 지금은 **쏟기 서보**다.
- 서버를 끄고 다시 켤 때 `pkill -f "uvicorn server.main"` 은 그 명령을 담은 ssh 셸까지 죽인다 → 스크립트 파일로 실행하거나 `pkill -f "^/home/.*/python.*uvicorn"` 처럼 좁힌다.
