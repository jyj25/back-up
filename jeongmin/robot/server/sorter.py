"""AI 판정(IF-01) → 통 임무 시작, 그리고 처리 기록(IF-04).

판정 한 줄 (yujeong/docs/A07-interface.md 의 판정 JSON):
    {"class":"can","conf":0.93,"ms":173}     확정된 판정 → 자동 출발이 켜져 있으면 can 통으로
    {"class":null,"conf":0.41,"ms":173}      판정 없음 → 무시
    {"error":"camera"}                       보드 오류 → 무시 (마지막 판정에 기록)
'{' 로 시작하지 않는 줄(부팅·디버그 로그)은 parse_line 에서 버린다.
"event" 필드가 있으면 "decision" 일 때만 판정으로 본다 (확정 신호 방식이 바뀌어도 받도록).

출발 조건: 자동 출발 켜짐 · 임무 중 아님 · class 가 통 이름(home 제외) · conf ≥ min_confidence.
기록은 임무가 끝날 때 한 줄씩 (done / failed / cancelled). HISTORY_FILE 에 JSON 줄로 이어 쓴다.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path


EMPTY_MSG = "트레이가 비었습니다. 물건을 얹어 주세요"


def parse_line(raw: str | bytes) -> dict | None:
    """한 줄 → JSON 객체(dict). 로그 줄·깨진 줄은 None."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    line = raw.strip()
    if not line.startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


class Sorter:
    def __init__(self, robot, stations: dict, min_confidence: float = 0.8,
                 auto: bool = False, history_file: Path | None = None) -> None:
        self.robot, self.stations = robot, stations
        self.min_confidence = min_confidence
        self.auto = auto
        self.history_file = history_file
        self.last_verdict: dict | None = None
        self.last_decision: dict | None = None  # 마지막 확정 판정 (프레임이 last_verdict 를 덮어써도 남는다)
        self._decided: tuple | None = None  # 샤오가 확정한 (라벨, 확신도, 시각). 빈 트레이가 보이면 지운다
        self._empty = False                 # 가장 최근 프레임이 빈 트레이였나
        self._top: tuple | None = None      # 가장 최근 프레임에서 퍼센트가 제일 높은 (라벨, 확신도, 시각)
        self._last_frame: tuple | None = None  # (찍은 시각 monotonic, 빈 트레이였나)
        self.current: dict | None = None  # 지금 임무의 {label, confidence, by}
        self.items: list[dict] = []
        self.bins = {name: 0 for name in stations if name != "home"}
        self._load()

    # ---- 판정 받기 ----

    def handle(self, obj: dict, source: str = "board") -> dict:
        """판정 하나를 처리하고 {accepted, reason} 를 돌려준다. 이벤트 루프 안에서 부를 것."""
        self.last_verdict = {**obj, "source": source, "time": _now()}
        if isinstance(obj.get("class"), str) and "error" not in obj:
            self.last_decision = self.last_verdict  # 같은 dict 라서 아래에서 result 가 채워지면 같이 보인다
        self._note(obj)
        reason = self._reject_reason(obj)
        if reason:
            self.last_verdict["result"] = reason
            return {"accepted": False, "reason": reason}
        label = obj["class"]
        self.start(label, by="ai", confidence=float(obj.get("conf", 0)),
                   return_home=not getattr(self.robot.mission.cfg, "finish_after_dump", False))
        self.last_verdict["result"] = "출발"
        return {"accepted": True, "reason": f"{self.stations[label]['label']} 통으로 출발"}

    def _note(self, obj: dict) -> None:
        """샤오가 본 것을 기억한다: 빈 트레이면 확정 판정을 잊고, 라벨이 확정되면 적어 둔다."""
        label = obj.get("class")
        if "error" in obj:
            return
        is_empty = label == "empty" or (label is None and obj.get("n") == 0)
        try:
            took = float(obj.get("ms", 0)) / 1000  # 모델이 도는 동안 걸린 시간 → 사진은 그만큼 전에 찍었다
        except (TypeError, ValueError):
            took = 0.0
        self._last_frame = (time.monotonic() - took, is_empty)
        top = obj.get("top")
        if is_empty:
            self._top = None
        elif isinstance(top, dict) and top.get("class") in self.bins:
            self._top = (top["class"], float(top.get("conf", 0)), time.monotonic())
        if label == "empty" or (label is None and obj.get("n") == 0):
            self._decided, self._empty = None, True
        elif label in self.bins and obj.get("event", "decision") == "decision":
            try:
                conf = float(obj.get("conf", 0))
            except (TypeError, ValueError):
                conf = 0.0
            if conf >= self.min_confidence:
                self._decided, self._empty = (label, conf, time.monotonic()), False
        elif label is None and obj.get("n"):
            self._empty = False

    def empty_after(self, t: float) -> bool | None:
        """t(monotonic) 뒤에 찍은 샤오 프레임이 빈 트레이면 True, 물건이 보이면 False, 아직 그런 프레임이 없으면 None"""
        lf = self._last_frame
        if lf is None or lf[0] <= t:
            return None
        return lf[1]

    def go_now(self) -> dict:
        """READY 버튼: 샤오가 트레이 위 물건을 보고 정한 라벨의 통(마커)으로 보낸다. {ok, reason, status}"""
        if self.robot.mission.running:
            return {"ok": False, "status": 409, "reason": "이미 임무 중입니다"}
        t = self._top
        if t is not None and time.monotonic() - t[2] <= 3.0:  # 확정을 기다리지 않고, 지금 퍼센트가 제일 높은 종류로 간다
            label, conf, _ = t
            self.start(label, by="ai", confidence=conf,
                       return_home=not getattr(self.robot.mission.cfg, "finish_after_dump", False))
            self._decided = None
            return {"ok": True, "status": 200, "reason": f"{self.stations[label]['label']} 통으로 출발 (제일 높은 {conf:.0%})"}
        if self._decided is not None:
            label, conf, _ = self._decided
            self.start(label, by="ai", confidence=conf,
                       return_home=not getattr(self.robot.mission.cfg, "finish_after_dump", False))
            self._decided = None
            return {"ok": True, "status": 200, "reason": f"{self.stations[label]['label']} 통으로 출발"}
        if self._empty:
            return {"ok": False, "status": 422, "reason": EMPTY_MSG}
        if self.last_verdict is None:
            return {"ok": False, "status": 503, "reason": "샤오 카메라 판정이 아직 안 왔습니다 (보드 연결 확인)"}
        return {"ok": False, "status": 425, "reason": "물건을 확인하는 중입니다. 잠시 뒤 다시 눌러 주세요"}

    def _reject_reason(self, obj: dict) -> str | None:
        if "error" in obj:
            return f"보드 오류: {obj['error']}"
        label = obj.get("class")
        if label is None and obj.get("n") == 0:
            return EMPTY_MSG
        if "event" in obj and obj["event"] != "decision":
            return f"판정 아님 ({obj['event']})"
        if label is None:
            return "판정 없음"
        if label == "empty":
            return EMPTY_MSG
        if label not in self.bins:
            return f"모르는 종류: {label}"
        try:
            conf = float(obj.get("conf", 0))
        except (TypeError, ValueError):
            return "확신도 형식 오류"
        if conf < self.min_confidence:
            return f"확신도 낮음 ({conf:.2f} < {self.min_confidence})"
        if not self.auto:
            return "자동 출발 꺼짐"
        if self.robot.mission.running:
            return "임무 중"
        return None

    # ---- 임무 시작·기록 ----

    def start(self, station: str, by: str = "web", confidence: float | None = None,
              dump: bool = True, return_home: bool = True) -> None:
        """임무 시작 + 끝나면 기록. 웹(/api/mission)과 AI 판정이 모두 여기를 지난다."""
        self.robot.mission.start(station, dump, return_home)
        self.current = {"label": station, "confidence": confidence, "by": by, "_t0": time.monotonic()}
        asyncio.get_running_loop().create_task(self._record_when_done(self.current))

    async def _record_when_done(self, cur: dict) -> None:
        await self.robot.mission.wait()
        st = self.robot.mission.state
        phase = st["phase"] if st["phase"] in ("done", "failed", "cancelled") else "cancelled"
        item = {
            "id": len(self.items) + 1, "time": _now(), "label": cur["label"],
            "confidence": cur["confidence"], "by": cur["by"], "result": phase,
            "seconds": round(time.monotonic() - cur["_t0"], 1), "steps": st["steps"], "message": st["message"],
        }
        self.items.append(item)
        if phase == "done" and cur["label"] in self.bins:
            self.bins[cur["label"]] += 1
        if self.current is cur:
            self.current = None
        self._append(item)

    def reset(self, station: str | None = None) -> None:
        """통 비우기: 개수만 0 으로 (기록은 남긴다)"""
        for name in ([station] if station else list(self.bins)):
            self.bins[name] = 0
        self._append({"reset": station or "all", "time": _now()})

    def history(self) -> dict:
        return {"bins": dict(self.bins), "items": list(self.items)}

    # ---- 파일 ----

    def _append(self, row: dict) -> None:
        if not self.history_file:
            return
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with self.history_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"[sorter] 기록 저장 실패: {e}")

    def _load(self) -> None:
        """서버를 다시 켜도 기록·개수가 이어지게 파일을 다시 읽는다."""
        if not self.history_file or not self.history_file.exists():
            return
        for line in self.history_file.read_text(encoding="utf-8").splitlines():
            row = parse_line(line)
            if not row:
                continue
            if "reset" in row:
                for name in (list(self.bins) if row["reset"] == "all" else [row["reset"]]):
                    if name in self.bins:
                        self.bins[name] = 0
            elif "result" in row:
                self.items.append(row)
                if row["result"] == "done" and row.get("label") in self.bins:
                    self.bins[row["label"]] += 1


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
