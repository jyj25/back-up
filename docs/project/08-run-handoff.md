# 08 · 실행·인계·다음 작업 (A17, A18)

## 실행 시작점

| 대상 | 어디서 | 방법 |
| --- | --- | --- |
| 로봇 서버 (가짜 모드) | 노트북 | `jeongmin/README.md` → "노트북 (하드웨어 없이)" — 조종 화면 `http://127.0.0.1:8000` |
| 로봇 서버 (실제) | 라즈베리파이 | `jeongmin/README.md` → "라즈베리파이" |
| 로봇 자동 시험 | 노트북 | `cd jeongmin/robot` → `python -m pytest -q` |
| 발표장 준비 | 라즈베리파이 | `jeongmin/README.md` → "조작 전 준비" (핫스팟 등록, 자동 실행) |
| 로봇 찾기 | 노트북 | `python jeongmin/robot/find_robot.py` |
| 마커 인쇄 | 노트북 | `jeongmin/robot/markers/markers.html` 을 받아 브라우저로 열고 100% 인쇄 |
| 사진 수집기 | 노트북 (Chrome/Edge) | `yujeong/ai/collector/index.html` — 보드를 노트북 USB 에 직접 연결 |
| 판정 JSON 확인 | 라즈베리파이·노트북 | `python yujeong/firmware/xiao_sorter/pi_reader.py /dev/ttyACM0` (노트북은 `COM 번호`) |
| 판정 로직 보드 시험 | 보드 | `yujeong/firmware/xiao_sorter/test_logic/` 업로드 → 시리얼 115200 |
| 대시보드 | — | 서민형 폴더에 추가 예정 |

`yujeong/` 파일은 아직 `yujeong` 브랜치에만 있다 (main 에 PR 전).

## 복구 (시연 중 문제가 생기면)

1. 로봇이 이상하게 움직이면 조종 화면 **■ 정지** (임무도 취소됨). 화면이 안 열리면 로봇 전원 스위치.
2. 조종 화면이 안 열리면: 노트북이 같은 핫스팟인지 → `find_robot.py` → 1분 기다렸다가 다시.
3. 자동 실행 서버 다시 시작: 라즈베리파이에서 `sudo systemctl restart raspbot` (사람이 실행).
4. 분류가 계속 틀리면: 조종 화면의 **통 버튼으로 수동 분류** (시연 계속).
5. 보드 포트가 안 잡히면: BOOT 버튼을 누른 채 USB 다시 꽂기 (부트로더), 재업로드 뒤 RESET.
6. 라이브 시연이 안 되면 시연 영상으로 전환.

## 현재 상태 (10/30)

- **사실**: 로봇 서버·통 찾아가기·안전장치가 가짜 모드 자동 시험 16개 PASS. 보드 영상 전송 PASS, 판정 확정 로직 보드 시험 PASS (담당자 기록).
- **미확인**: 실제 로봇 주행, 학습된 모델, 대시보드, 보드→로봇→웹 전체 연결, 발표장 Wi-Fi.
- **결정됨**: 분류·통 이름 `can / pet / paper / empty` (ADR-05).
- **로봇 쪽 준비됨**: 판정 JSON 수신(두 확정 방식 모두 수용), 처리 기록 API.
- **미결정**: 통에 넣는 방법(ADR-04), 발표자, 핫스팟 폰.

## 다음 작업 (11/1 모임 전)

| 누가 | 무엇 | 완료 확인 |
| --- | --- | --- |
| 정유정 | `yujeong` 브랜치 PR 올리기 (팀장 검토 후 main) | PR |
| 이정민 | TASK-R9 카메라 받침 위치 → 정유정에게 사진 각도 공유 | 사진 |
| 이정민 | 조립 → TC-09~11 실기 시험 → 06 에 RUN 기록 | 결과·영상 |
| 정유정 | TASK-A6~A8, TC-08·18 결과 | PR + 결과 |
| 서민형 | TASK-W1 (IF-02 로 시작), 슬라이드 틀 | PR |
| 팀 | 발표자·핫스팟 폰·통 넣는 방법 결정 → 02 회의 기록 | 카톡 결정 → PR |

## AI·다음 개발 전달문 (교재 CLAUDE-HANDOFF 양식)

```text
문제·사용자: 분리수거를 헷갈리는 사용자. 로봇 위 물건을 보드 AI 가 분류하고 로봇이 해당 통까지 간다 (docs/project/01).
현재 범위·제외: REQ-01~07, 09. 통에 넣는 장치(ADR-04 미결정), 원격 관제, SLAM, UNO 패널 제외.
관련 요구·설계·계약: REQ-05 / DES-02 / ADR-04, IF-02.
대상 작업·파일: TASK-R6 (ADR-04 가 정해진 뒤) — jeongmin/robot/server/drivers.py 의 RealDriver.dump()·FakeDriver.dump(),
  필요하면 새 장치 모듈. tests/ 에 가짜 모드 시험.
유지할 기능·인터페이스: IF-01 판정 수신 규칙(sorter.py), IF-02 엔드포인트·응답 필드, IF-04 기록 형식,
  자동 정지·속도 상한·장애물 정지, 수동 조작 시 임무 취소, FakeDriver/RealDriver 같은 메서드, stations.json 형식.
완료 기준·시험·실행 환경: 임무의 dumping 단계에서 정한 방법으로 물건을 넣고, 실패하면 임무를 failed 로 끝내며
  이유를 message 에 남긴다. pytest 전부 PASS (노트북 가짜 모드). 실제 장치 동작은 사람이 확인해 06 에 기록.
현재 사실·가정·미확인: 사실 — 로봇 가짜 모드 시험 21개 PASS (판정 수신·기록 포함), 보드 판정 로직 시험 PASS(담당자 기록).
  미확인 — 통에 넣는 방법(ADR-04), 실제 보드·로봇 연결. 장치·전원 정보를 지어내지 말 것.
```
