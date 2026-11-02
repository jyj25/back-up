"""파이 판정이 받은 샤오 사진을 대시보드로 다시 보내 준다."""
import asyncio
import os
import types

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from fastapi.testclient import TestClient  # noqa: E402

from server import main  # noqa: E402


def test_frame_endpoint_returns_the_last_photo():
    with TestClient(main.app) as c:
        assert c.get("/api/judge/frame.jpg").status_code == 503                  # 파이 판정을 안 쓰면 알려 준다
        main.robot.judge = types.SimpleNamespace(last_jpeg=b"\xff\xd8photo", frame_seq=3)
        try:
            r = c.get("/api/judge/frame.jpg")
            assert r.status_code == 200 and r.content == b"\xff\xd8photo" and r.headers["content-type"] == "image/jpeg"
        finally:
            main.robot.judge = None


def test_stream_endpoint_yields_a_new_frame_only_when_it_changes():
    j = types.SimpleNamespace(last_jpeg=b"\xff\xd8A", frame_seq=1)
    main.robot = main.Robot()
    main.robot.judge = j

    async def run():
        it = main.judge_stream().body_iterator              # 동기 생성기도 서버가 비동기로 감싸 준다
        first = await it.__anext__()
        j.last_jpeg, j.frame_seq = b"\xff\xd8B", 2           # 사진이 바뀌면 새로 한 장
        second = await it.__anext__()
        return first, second

    try:
        first, second = asyncio.run(run())
    finally:
        main.robot.judge = None
        main.robot.close()
        main.robot = None
    assert first.startswith(b"--frame") and b"\xff\xd8A" in first
    assert b"\xff\xd8B" in second
