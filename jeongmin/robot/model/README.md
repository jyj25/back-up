# 파이 판정용 모델 (`jyj25.eim`)

`JUDGE=pi` 일 때 서버(`server/judge.py`)가 이 폴더의 `jyj25.eim` 으로 샤오 사진을 판정한다. 파일(약 13.7MB)은 저장소에 넣지 않았다.

받는 방법 (유정의 Edge Impulse 키가 `yujeong/.env` 에 있어야 함):

    cd yujeong/ai
    python build_eim.py ../../jeongmin/robot/model/jyj25.eim

- 반드시 **float32** 로 받는다. 리눅스용 int8 은 이 프로젝트에서 모든 입력의 출력이 비어 쓸 수 없었다.
- 파이에는 `pip install edge_impulse_linux six` 가 필요하다 (`pyaudio` 는 안 쓰며 judge.py 가 빈 모듈로 대신한다).

## 확정 모델 (2026-11-02)

- Edge Impulse 프로젝트 1149702, FOMO(MobileNetV2 0.35, 96×96). 트레이 위 빈 트레이 50장·캔 80장·페트 27+5장·종이 29장을 더해 재학습한 float32 모델.
- 파이에서 실제 트레이 위 물건을 20장씩 찍어 판정한 결과 (같은 자리·같은 물건이라 처음 보는 물건이면 더 낮을 수 있다):

| 실제 | 옛 모델 | 확정 모델 |
|---|---|---|
| 빈 트레이 | 0/20 (전부 캔) | 20/20 |
| 캔 | 20/20 | 20/20 |
| 페트 | 19/20 | 20/20 |
| 종이 | 13/20 (7장 빈 트레이) | 20/20 |

- 옛 모델은 `jyj25_prev.eim` 으로 파이에 남겨 두었다. 빈 트레이 기준 사진 비교(`PAPER_BY_TRAY_DIFF=1`)는 안전장치로 계속 켠다.
- 쏟기 위치: `pan_center: true` — 목표 마커가 화면 가운데(마커 바로 옆)에 올 때까지 앞뒤로 맞춘 뒤 쏟는다.
