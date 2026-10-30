# minhyeong — 웹 · 앱 담당 (서민형)

분리수거 로봇의 **대시보드**와 **휴대폰 웹앱**, 발표 웹 슬라이드 배포를 맡는다. 취미는 축구.
작업은 `minhyeong` 브랜치에서 하고 Pull Request 로 main 에 합친다.

```
minhyeong/
├── README.md         이 문서
└── dashboard/        대시보드 (설치·빌드 없음, 파일 3개)
    ├── index.html    화면 배치 (휴대폰은 아래 탭, 넓은 화면은 왼쪽 메뉴)
    ├── ui.js         7개 기능 화면
    └── robot.js      로봇 API 를 읽어 화면용 상태를 만듦 (+ 로봇 없이 도는 가짜 로봇)
```

## 실행

```powershell
cd minhyeong/dashboard
python -m http.server 8765
```

| 주소 | 뜻 |
| --- | --- |
| `http://localhost:8765/` | 가짜 로봇으로 동작 (로봇 없이 화면 확인) |
| `http://localhost:8765/?robot=http://<로봇 IP>:8000` | 로봇 조종 서버에 연결 (실제 로봇 또는 `ROBOT_MODE=fake`) |

- 로봇 서버의 `CORS_ORIGINS` 에 **`http://localhost:8765`** 를 넣어야 브라우저가 로봇 API 를 부를 수 있다.
- 배포된(https) 사이트에서는 로봇 접속이 막히므로 시연 대시보드는 노트북에서 `http://localhost` 로 띄운다 (04-design 경계).
- 글꼴·아이콘·Tailwind 를 CDN 에서 받으므로 처음 열 때는 인터넷이 필요하다. 핫스팟에 인터넷이 없으면 화면 모양이 깨질 수 있다 → 시연 전에 확인.

## 화면 (DES-04)

| 메뉴 | 기능 | 데이터 |
| --- | --- | --- |
| 실시간 | ① 로봇 카메라 영상 + 보이는 통 마커에 박스, 갱신 시각, 카메라 연결 상태 | `GET /api/stream`, `GET /api/mission` 의 `seen` |
| | ② AI 분류 결과: 종류, 확신도, 판정 시각 | 임무가 시작될 때의 `station` (확신도는 아래 요청) |
| | ③ 로봇 상태 + 임무 단계: AI 판정 → 통 찾기 → 도착 → 쏟기 → 복귀 → 완료 | `GET /api/status`, `GET /api/mission` 의 `phase`·`target`·`steps`·`message` |
| 통계 | ④ 오늘 처리량, 임무 성공률, 평균 임무 시간, 평균 확신도, 통별·시간대별 개수, 탄소 절감량(출처 확인 전 "—") | 완료된 임무를 셈 (IF-04 가 생기면 그쪽 값) |
| 기록 | ⑤ 임무별 결과(완료/실패/취소)·걸린 시간·걸음 수, 통 앞 도착 사진, CSV 내보내기 | `GET /api/camera.jpg` (도착·쏟는 중 한 장) |
| 알림 | ⑥ 연결 끊김, 장애물로 멈춤, 카메라 없음, 임무 실패·취소, 통 가득 참 | 위 값의 변화 |
| 제어 | ⑦ 정지, 임무 취소, 통으로 보내기(1초 누르고 있기), 로봇 조종 화면 링크, 관리자(통 가득 참 기준, 통 비우기) | `POST /api/stop`, `/api/mission/cancel`, `/api/mission` |

임무 단계는 로봇 `phase` 를 이렇게 묶는다: `starting` → AI 판정, `search·align·approach`(목표가 통) → 통 찾기, `arrived` → 도착, `dumping·backing` → 쏟기, 목표가 `home` → 복귀, `done` → 완료. `failed`·`cancelled` 는 빨간/회색 줄로 이유(`message`)를 보여 준다.

## 안전 (제어 화면)

- 웹에서 보내기 전 인터록: 로봇 서버 연결 · 임무 중 아님 · 앞 장애물 없음 · 통 여유. 로봇 서버가 다시 검사한다 (임무 중이면 409, 앞이 막히면 이동 거절).
- 통으로 보내기는 **1초 동안 누르고 있어야** 실행된다 (잘못 눌러 출발하는 것을 막음).
- 웹 정지 = `POST /api/stop` (바퀴 정지 + 임무 취소). **웹 연결이 끊기면 정지 명령이 전달되지 않는다.** 이동 명령은 로봇이 3초 안에 스스로 멈추지만, 로봇이 스스로 하는 임무는 계속되므로 **로봇 본체 전원 스위치**로 끈다 → 시연 때 전원 스위치 담당을 정해 두자.

## 팀원에게 받을 데이터 (제안 — 합의 전)

**이정민 (로봇) — IF-04 처리 기록 API.** 04-design 의 `GET /api/history` 에 아래 필드를 제안한다. 지금 대시보드는 같은 값을 브라우저 안에서 모으고 있어서 새로고침하면 사라진다.

```json
{
  "bins": { "recycle": 4, "general": 2, "vinyl": 1 },
  "items": [
    { "id": 12, "time": "2026-11-01T14:03:22", "label": "recycle", "confidence": 0.93,
      "by": "ai", "result": "done", "seconds": 31.8, "steps": 81, "message": "완료" }
  ]
}
```
- `label`·`confidence`: ESP32 가 보낸 `RESULT recycle 0.93` 그대로 (IF-01). 웹에서 보낸 임무는 `by: "web"`, `confidence: null`.
- `result`: `done` / `failed` / `cancelled`, 실패·취소면 `message` 에 이유.
- `bins` 는 통을 비우면 0 으로 돌릴 수 있게 `POST /api/history/reset {"station": "recycle"}` 같은 것이 있으면 좋다.
- 그 전까지 임시로 **`GET /api/mission` 에 `confidence` 만 넣어 줘도** AI 확신도를 표시할 수 있다.
- 로봇 서버 `CORS_ORIGINS` 에 `http://localhost:8765` 등록.

**정유정 (AI)** — 라벨 이름 `recycle / general / vinyl / empty` 와 `RESULT <label> <confidence>` 형식(IF-01)을 그대로 쓴다. 바뀌면 알려 주기.

**팀 결정이 필요한 것**
- 통 "가득 참" 기준 개수 (지금 가정 10개, 관리자 화면에서 바꿀 수 있음)
- 탄소 절감 계수와 출처 (출처를 찾기 전에는 "— kg" 로 둔다)

## 상태

- [x] 대시보드 화면 7개 기능, 가짜 로봇으로 동작
- [x] 로봇 조종 서버(`ROBOT_MODE=fake`)에 연결해 확인: 웹에서 보내기 → 통 찾기 → 쏟기 → 복귀 → 완료 기록, 임무 중 다시 보내면 거절, 취소·정지
- [ ] 실제 로봇에서 카메라 영상·도착 사진 확인 (가짜 모드 서버에는 카메라가 없어 못 봄)
- [ ] IF-04 기록 API 연결 → 통별 개수·확신도를 서버 값으로
- [ ] 탄소 절감 계수 출처 찾기
- [ ] 휴대폰에서 홈 화면에 추가해 보기, 알림
- [ ] 발표 웹 슬라이드 → Vercel 배포
