# 백업 2026-11-02 — 라즈봇 파이에만 있던 수정 + 샤오 펌웨어 + 수정한 대시보드

SD카드를 바꾸는 사이에 파이에만 있던 수정이 사라지지 않도록 이 PC 저장소로 가져온 백업이다. 기준은 `origin/main`(PR #3 머지, `27b82b1`).

## 들어 있는 것

| 위치 | 내용 |
|---|---|
| `jeongmin/robot/` | 파이의 로봇 코드 전체 (아래 "바뀐 동작" 포함) |
| `jeongmin/robot/robot.env.pi-2026-11-02.txt` | 파이의 `robot.env` 설정값 (`.env` 는 gitignore 대상이라 .txt 로 보관, 비밀번호 없음) |
| `jeongmin/robot/model/README.md` | 파이 판정용 모델(`jyj25.eim`, 약 13.7MB) 받는 방법. 파일은 저장소에 넣지 않았다 |
| `yujeong/ai/build_eim.py` | 유정의 Edge Impulse 프로젝트에서 파이용 모델(float32)을 받는 스크립트 |
| `yujeong/firmware/xiao_sorter/` | 샤오 인식 + Wi-Fi 영상 펌웨어 (폴더 전체) |
| `yujeong/firmware/xiao_stream/` | 사진 전송 + Wi-Fi 영상 펌웨어 (Wi-Fi 목록 순서 접속). 파이 판정(`JUDGE=pi`)에서 쓴다 |
| `backup/2026-11-02/dashboard-modified/` | 수정한 민형 대시보드 (`index.html`, `ui.js`). 민형 원본(`minhyeong/dashboard/`)은 건드리지 않았다 |

Wi-Fi 이름·비밀번호가 든 `wifi_secrets.h` 는 저장소에 넣지 않았다 (각 폴더의 `wifi_secrets.h.example` 을 복사해서 채운다). 파이 접속 정보(사용자·비밀번호)도 넣지 않았다.

## 판정 방식 두 가지 (`robot.env`)

| 방식 | 설정 | 샤오 펌웨어 | 판정 속도 |
|---|---|---|---|
| **파이 판정 (지금 쓰는 것)** | `JUDGE=pi`, `BOARD_PORT=none` | `xiao_stream` (사진만 USB 로 보냄) | 한 번에 약 44ms (모델 7ms + 사진), 초당 약 30프레임 |
| 보드 판정 | `BOARD_PORT=auto` (`JUDGE` 없음) | `xiao_sorter` (보드 안에서 모델 실행) | 한 번에 약 3.6초 (가속 끔), 확정까지 약 11초 |

- 보드 판정이 느린 이유: ESP32-S3 의 ESP-NN 가속이 이 모델에서 힙을 깨뜨려(`CORRUPT HEAP`, 재부팅 반복) 꺼야 했다. 가속을 켜 보는 시도(작업 메모리 내부 RAM 고정, 일반 tflite 판, 메모리 확대)는 모두 실패했다.
- 파이 판정: `server/judge.py` 가 샤오 사진(USB `C` 한 글자 → JPEG)을 받아 `.eim` 모델로 판정하고, 보드가 보내던 것과 같은 판정 줄(IF-01)로 서버에 넣는다. 확정 로직(확신도 ≥ 0.8, 같은 결과 3번 연속, 빈 트레이 3번 연속이어야 다음 판정)은 `detect_logic.h` 와 같다.
- 모델은 반드시 **float32** `.eim` 이어야 한다. 리눅스용 int8 은 이 프로젝트에서 모든 입력의 출력이 비어 쓸 수 없었다.

## 바뀐 동작 (`jeongmin/robot`)

- **알고리즘** (`server/navigator.py`)
  - 못 찾으면 실패하지 않고 처음부터 다시 둘러본다 (`nav.rescans`).
  - 도착하면 왼쪽 90° 돌고 쏟은 뒤 끝낸다 (`nav.finish_after_dump`, `nav.dock_steps: 0`).
  - 식별된 다른 번호 블록은 미식별 후보에서 제외한다 (`_unknowns`).
  - 한 바퀴 돌 때 조금 돌고 멈춰서 화면이 안정된 뒤 마커를 찾는다 (`nav.scan_pause_ms`).
- **샤오 판정으로 시작** (`server/sorter.py`, `main.py`)
  - `POST /api/sort/go` — 샤오가 확정한 라벨(캔/페트/종이)의 통(마커)으로 보낸다. 빈 트레이면 "트레이가 비었습니다. 물건을 얹어 주세요".
  - `GET /api/sort` 가 `last_decision` 을 따로 준다. 파이 판정은 초당 30프레임이라 확정 줄이 다음 프레임에 바로 덮어써져서, 대시보드(0.7초마다 읽음)가 확정을 못 보던 문제를 고쳤다.
  - `GET /api/judge` — 파이 판정의 마지막 검출·확정 진행 (왜 확정이 안 나는지 볼 때).
- **쏟은 뒤 확인** (`navigator._dump_with_tray`, `sorter.empty_after`, `drivers.dump(speed)`)
  - 샤오 판정에서 "빈 트레이"가 안 보이면 서보를 2배속으로 다시 쏟는다 (최대 2번).
- **트레이 사진 비교** (`server/tray_check.py`, `GET /api/tray`, `POST /api/tray/baseline`)
  - 샤오를 사진 모드로 쓸 때의 확인 방식. `JUDGE=pi` 에서는 판정 영상으로 비었는지 본다.
- **카메라 좌우(pan)** (`server/drivers.py`)
  - 2°씩 나눠 천천히 돌린다 (`PAN_DPS`, 기본 60도/초).
- **회전 속도·마커 설정** (`stations.blocks.json`)
  - 키 블록 AprilTag 36h11, 번호: 출발점 1 / 캔 2 / 페트 3 / 종이 4. `turn_speed 45`, `turn90_ms 667`, `scan_step_ms 250`, 샤오 감시 구역(`tray.roi`, `tray.drop_zone`).
- **시험**: `tests/test_algorithm.py`, `test_dump_retry.py`, `test_judge.py`, `test_decision.py` 추가, `test_sorting.py` 의 빈 트레이 메시지 갱신. 파이에서 전체 55개 통과.

## 샤오 펌웨어

- `xiao_sorter.ino`: 유정이 학습한 Edge Impulse 모델(`jyj25-project-1`, FOMO 96×96)로 판정해 USB 로 보내고, 같은 보드가 Wi-Fi `:81/stream` 으로 영상도 보낸다. 모델이 오류를 내면 `{"error":"model","code":...}` 로 코드를 같이 보낸다.
  - EON 컴파일 모델 라이브러리에서는 빌드 옵션으로 가속을 꺼야 한다 (소스에 주석 있음):
    ```
    arduino-cli compile --fqbn "esp32:esp32:XIAO_ESP32S3:PSRAM=opi" \
      --build-property "compiler.cpp.extra_flags=-DEI_CLASSIFIER_TFLITE_ENABLE_ESP_NN=0" \
      --build-property "compiler.c.extra_flags=-DEI_CLASSIFIER_TFLITE_ENABLE_ESP_NN=0" yujeong/firmware/xiao_sorter
    ```
  - Wi-Fi 는 `STA_LIST` 앞쪽부터 8초씩 시도한다. 붙어 있던 Wi-Fi 가 30초 넘게 끊기면 재부팅해서 다시 찾는다.
- `xiao_stream.ino`: 사진을 USB(`C` 한 글자)와 Wi-Fi(`:81/stream`, `/capture`)로 보낸다. Wi-Fi 는 `STA_LIST` 순서로 접속하고 실패하면 자체 AP.
- 보드는 파이 USB 에 꽂혀 있어서 PC 로 옮기지 않고 파이에서 `esptool` 로 올렸다 (`write-flash 0x0 <merged.bin>`).

## 알려진 한계

- 마커(블록 한 변 약 4cm)는 멀면 안 읽힌다. (이 줄은 예전 동작: 아래 "저녁 업데이트"의 `pan_look` 방식으로 바뀌어 더는 한 바퀴 돌지 않는다.)
- 자동 실행(`autostart.sh` 서비스 또는 `@reboot`)은 설치하지 않았다. 파이가 재부팅하면 서버를 다시 켜야 한다 (`robot.env` 를 불러 uvicorn 실행).
- 실제 로봇으로 찾기 → 도착 → 쏟기를 끝까지 돌려 본 것은 이 백업 이후다. 알고리즘은 시뮬레이션 시험으로 확인했다.
- 모델 정확도: 종이·`general_trash` 일부는 검출이 약하다 (모델 자체의 한계).

## 복원

1. 파이의 `~/ai2-8/jeongmin/robot` 을 이 브랜치의 `jeongmin/robot` 으로 바꾼다 (`robot.env.pi-2026-11-02.txt` 는 `robot.env` 로 이름 변경).
2. 가상환경(`raspbot-venv`)에 `fastapi[standard]`, `pyserial`, `pytest`, `opencv`, `raspbot`, `edge_impulse_linux`, `six` 를 설치한다 (`requirements.txt` 참고).
3. 모델: `jeongmin/robot/model/README.md` 대로 `jyj25.eim` (float32) 을 받는다.
4. 샤오: `xiao_stream` 펌웨어를 올린다 (`JUDGE=pi` 용). 보드 판정은 `xiao_sorter` + 위 빌드 명령.

## 저녁 업데이트 (같은 날, 실제 로봇으로 끝까지 성공)

환경: 마커(AprilTag 36h11: 1 홈, 2 캔, 3 페트, 4 종이)를 로봇 진행 방향 **오른쪽에 일렬**로 세우고, 로봇은 줄과 나란히 **앞뒤로만** 움직인다 (회전·옆걸음·한 바퀴 돌기 없음).

- `nav.pan_look` (`stations.blocks.json`): 한 걸음마다 멈춰서 카메라(오른쪽 `scan_pan`)로 마커를 본다. 목표(트레이 쓰레기와 같은 번호)가 보이면 바로 멈춰 쏟고, 다른 번호는 한 번 멈춰 판단(`pan_judge_ms`)한 뒤 전진한다. 줄 끝이거나 앞이 막히면 몸을 돌리지 않고 *후진*하며 같은 방법으로 다시 본다 (`fail_retries`+1 번 훑음).
- 카메라 각도: `travel_pan` = `scan_pan` = 15 (서보가 움직이지 않게 같은 값). 카메라가 바닥을 내려다봐서 마커가 화면 위쪽에 걸린다 → 카메라를 손으로 약간 들어 주면 더 안정적. 위아래 서보(S2)는 쏟기용이라 쓸 수 없다.
- 쏟기: `DUMP_ANGLE=105` (`robot.env`, 서보 한계 110). 안 비면 1배 → 2배 → 4배로 다시 쏟는다.
- 판정: `JUDGE_VOTE_N=0` (다수결 끔, 같은 1등 종류가 3프레임 연속 + 확신도 0.8 이상). 출발(READY)은 확정을 기다리지 않고 최근 프레임에서 퍼센트가 제일 높은 종류로 간다 (`top`).
- 기타 설정(`stations.blocks.json`): `row_mode`, `side_camera`/`side_*` (옆 카메라 모드, 지금은 `pan_look` 이 우선), `fail_retries`, `line_advance_steps`(40), `scan_pause_ms`(1500), `pan_judge_ms`(1500).
- 시험 111개 통과 (`tests/`). 대시보드는 같은 서버 API 를 부르므로 같은 동작이다.
- 서버 켜기: `cd ~/ai2-8/jeongmin/robot; set -a; . ./robot.env; set +a; uvicorn server.main:app --host 0.0.0.0 --port 8000`. (SSH 로 시작할 때 `pkill -f uvicorn ...` 처럼 명령줄에 같은 글자가 있으면 자기 세션까지 죽는다 → `pkill -f "[u]vicorn"` 사용)
