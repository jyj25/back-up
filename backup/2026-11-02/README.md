# 백업 2026-11-02 — 라즈봇 파이에만 있던 수정 + 샤오 펌웨어 + 수정한 대시보드

SD카드를 바꾸는 사이에 파이에만 있던 수정이 사라지지 않도록 이 PC 저장소로 가져온 백업이다. 기준은 `origin/main`(PR #3 머지, `27b82b1`).

## 들어 있는 것

| 위치 | 내용 |
|---|---|
| `jeongmin/robot/` | 파이의 로봇 코드 전체 (아래 "바뀐 동작" 포함) |
| `jeongmin/robot/robot.env.pi-2026-11-02.txt` | 파이의 `robot.env` 설정값 (`.env` 는 gitignore 대상이라 .txt 로 보관, 비밀번호 없음) |
| `yujeong/firmware/xiao_sorter/` | 샤오 인식 + Wi-Fi 영상 펌웨어 (폴더 전체) |
| `yujeong/firmware/xiao_stream/` | 영상용 펌웨어 (Wi-Fi 목록 순서 접속) |
| `backup/2026-11-02/dashboard-modified/` | 수정한 민형 대시보드 (`index.html`, `ui.js`). 민형 원본(`minhyeong/dashboard/`)은 건드리지 않았다 |

Wi-Fi 이름·비밀번호가 든 `wifi_secrets.h` 는 저장소에 넣지 않았다 (각 폴더의 `wifi_secrets.h.example` 을 복사해서 채운다). 파이 접속 정보(사용자·비밀번호)도 넣지 않았다.

## 바뀐 동작 (`jeongmin/robot`)

- **알고리즘** (`server/navigator.py`)
  - 못 찾으면 실패하지 않고 처음부터 다시 둘러본다 (`nav.rescans`).
  - 도착하면 왼쪽 90° 돌고 쏟은 뒤 끝낸다 (`nav.finish_after_dump`, `nav.dock_steps: 0`).
  - 식별된 다른 번호 블록은 미식별 후보에서 제외한다 (`_unknowns`).
- **쏟은 뒤 확인** (`navigator._dump_with_tray`, `sorter.empty_after`, `drivers.dump(speed)`)
  - 샤오 판정 영상에서 "빈 트레이"가 안 보이면 서보를 2배속으로 다시 쏟는다 (최대 2번).
- **샤오 판정으로 시작** (`server/sorter.py`, `main.py`)
  - `POST /api/sort/go` — 샤오가 확정한 라벨(캔/페트/종이)의 통으로 보낸다. 빈 트레이면 "트레이가 비었습니다. 물건을 얹어 주세요".
- **트레이 사진 비교** (`server/tray_check.py`, `GET /api/tray`, `POST /api/tray/baseline`)
  - 샤오를 사진 모드로 쓸 때만 동작.
- **카메라 좌우(pan)** (`server/drivers.py`)
  - 2°씩 나눠 천천히 돌린다 (`PAN_DPS`, 기본 60도/초).
- **회전 속도·마커 설정** (`stations.blocks.json`)
  - 키 블록 AprilTag 36h11, 번호: 출발점 1 / 캔 2 / 페트 3 / 종이 4. `turn_speed 45`, `turn90_ms 667`, `scan_step_ms 250`, 샤오 감시 구역(`tray.roi`, `tray.drop_zone`).
- **시험**: `tests/test_algorithm.py`, `tests/test_dump_retry.py` 추가, `tests/test_sorting.py` 의 빈 트레이 메시지 갱신. 파이에서 전체 45개 통과.

## 샤오 펌웨어

- `xiao_sorter.ino`: 유정이 학습한 Edge Impulse 모델(`jyj25-project-1`, FOMO 96×96)로 판정해 USB 로 보내고, 같은 보드가 Wi-Fi `:81/stream` 으로 영상도 보낸다.
  - ESP32-S3 의 ESP-NN 가속이 모델 실행 중 힙을 깨뜨려(`CORRUPT HEAP`, 재부팅 반복) 꺼야 한다. 빌드 옵션으로 전체에 적용:
    ```
    arduino-cli compile --fqbn "esp32:esp32:XIAO_ESP32S3:PSRAM=opi" \
      --build-property "compiler.cpp.extra_flags=-DEI_CLASSIFIER_TFLITE_ENABLE_ESP_NN=0" \
      --build-property "compiler.c.extra_flags=-DEI_CLASSIFIER_TFLITE_ENABLE_ESP_NN=0" yujeong/firmware/xiao_sorter
    ```
  - 가속을 꺼서 모델 한 번에 약 3.6~4초 걸린다.
  - Wi-Fi 는 `STA_LIST` 앞쪽부터 8초씩 시도한다. 붙어 있던 Wi-Fi 가 30초 넘게 끊기면 재부팅해서 다시 찾는다.
- 보드는 파이 USB 에 꽂혀 있어서 PC 로 옮기지 않고 파이에서 `esptool` 로 올렸다 (`write-flash 0x0 <merged.bin>`).

## 알려진 한계

- 판정이 한 프레임씩 흔들려 같은 결과 3번 연속 조건을 못 채우면 확정이 늦거나 안 난다.
- 샤오 판정(USB)과 트레이 사진 비교(사진 모드)는 한 USB 포트를 같이 못 써서 판정 모드에서는 사진 비교가 꺼진다.
- 파이 서버 자동 실행(`autostart.sh`)은 설치하지 않아 재부팅하면 서버를 다시 켜야 한다 (`robot.env` 를 불러 uvicorn 실행).

## 복원

1. 파이의 `~/ai2-8/jeongmin/robot` 을 이 브랜치의 `jeongmin/robot` 으로 바꾼다 (`robot.env.pi-2026-11-02.txt` 는 `robot.env` 로 이름 변경).
2. 가상환경(`raspbot-venv`)에 `fastapi[standard]`, `pyserial`, `pytest`, `opencv`, `raspbot` 을 설치한다 (`requirements.txt` 참고).
3. 샤오는 위 빌드 명령으로 만든 펌웨어를 올린다.
