# 파이 판정용 모델 (`jyj25.eim`)

`JUDGE=pi` 일 때 서버(`server/judge.py`)가 이 폴더의 `jyj25.eim` 으로 샤오 사진을 판정한다. 파일(약 13.7MB)은 저장소에 넣지 않았다.

받는 방법 (유정의 Edge Impulse 키가 `yujeong/.env` 에 있어야 함):

    cd yujeong/ai
    python build_eim.py ../../jeongmin/robot/model/jyj25.eim

- 반드시 **float32** 로 받는다. 리눅스용 int8 은 이 프로젝트에서 모든 입력의 출력이 비어 쓸 수 없었다.
- 파이에는 `pip install edge_impulse_linux six` 가 필요하다 (`pyaudio` 는 안 쓰며 judge.py 가 빈 모듈로 대신한다).
