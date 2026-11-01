"""CORS_ORIGINS 는 서버를 불러올 때 읽으므로, 값을 바꿔 새로 불러와서 시험한다."""
import importlib
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from fastapi.testclient import TestClient  # noqa: E402

from server import main  # noqa: E402

TEAM = "http://localhost:5173"


def load(origins: str):
    os.environ["CORS_ORIGINS"] = origins
    try:
        return importlib.reload(main)
    finally:
        del os.environ["CORS_ORIGINS"]


def preflight(c, origin):
    return c.options("/api/move", headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                           "Access-Control-Request-Headers": "content-type"})


def test_listed_origin_allowed():
    m = load(f"{TEAM}/, http://127.0.0.1:5500")  # 끝의 / 와 띄어쓰기도 괜찮다
    with TestClient(m.app) as c:
        assert preflight(c, TEAM).headers.get("access-control-allow-origin") == TEAM
        r = c.get("/api/status", headers={"Origin": "http://127.0.0.1:5500"})
        assert r.headers.get("access-control-allow-origin") == "http://127.0.0.1:5500"
        assert "access-control-allow-origin" not in preflight(c, "http://evil.example").headers


def test_default_no_cors():
    m = load("")
    with TestClient(m.app) as c:
        r = c.get("/api/status", headers={"Origin": TEAM})
        assert r.status_code == 200 and "access-control-allow-origin" not in r.headers
