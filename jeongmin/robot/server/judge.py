"""파이가 샤오 사진을 판정한다: 샤오는 사진만 보내고(USB 'C' 한 글자 → JPEG), 파이가 유정의 Edge Impulse 모델(.eim, float32)을 돌린다.

샤오 보드 안에서 돌리면 모델 한 번에 3.6초(ESP-NN 가속이 이 보드에서 힙을 깨뜨려 끔)인데, 파이에서는 한 장에 약 7ms 다.
판정 줄은 보드가 보내던 것과 같은 모양(IF-01)으로 서버의 _on_board_line 에 넣는다:
    {"class":"can","conf":0.93,"ms":120,"n":1}   확정 판정
    {"class":null,"conf":0.0,"ms":120,"n":2}     판정 없음 (n = 이번 프레임의 물체 수, 0 이면 빈 트레이)
    {"error":"camera"}                           사진을 못 받음

확정 로직은 yujeong/firmware/xiao_sorter/detect_logic.h 와 같다:
  같은 종류이고 붙어 있는 칸을 한 물체로 묶고, 확신도가 가장 높은 물체의 종류가 CONFIRM_N 번 연속 같고 확신도 ≥ CONF_MIN 이면 한 번 확정한다.
  확정 뒤에는 물체가 CLEAR_N 번 연속 없을 때(트레이가 빔)까지 새 판정을 내지 않는다.
모델은 .eim 을 float32 로 받아야 한다 (리눅스용 int8 은 이 프로젝트에서 모든 출력이 비어 쓸 수 없었다).
"""
from __future__ import annotations

import collections
import json
import math
import os
import sys
import threading
import time
import types
from pathlib import Path

DET_MIN = 0.60     # 칸 하나를 검출로 인정하는 확신도 (EI 평가와 같음)
CONF_MIN = 0.80    # 확정 확신도 하한 (sorter.py 의 min_confidence 와 같게)
CONFIRM_N = 3      # 같은 결과가 이만큼 연속이어야 확정
CLEAR_N = 3        # 확정 뒤 물체가 이만큼 연속 없어야 다시 판정
STUCK_MS = 10000
JOIN_GAP = 2       # 두 칸 사이가 이 픽셀 이하면 붙은 것으로 본다
MARGIN = float(os.environ.get("JUDGE_MARGIN", "0"))  # (선택) 확정하려면 1등 종류가 다른 종류보다 이만큼 이상 확신해야 한다. 0 이면 끔 — 다수결(VOTE_N)이 대신한다
VOTE_N = int(os.environ.get("JUDGE_VOTE_N", "12"))  # 최근 이만큼의 프레임으로 다수결 (0 이면 예전처럼 같은 결과 CONFIRM_N 번 연속)
VOTE_RATIO = float(os.environ.get("JUDGE_VOTE_RATIO", "0.7"))  # 최근 프레임 중 이 비율 이상이 같은 종류여야 확정
LOG_KEEP = 300     # judge_log/ 에 남기는 확정 사진 수


class Detector:
    """detect_logic.h 의 detect::Detector 를 옮긴 것. update 는 (event, 종류, 확신도, 물체 수)를 돌려준다."""

    def __init__(self, conf_min=CONF_MIN, confirm_n=CONFIRM_N, clear_n=CLEAR_N, stuck_ms=STUCK_MS, join_gap=JOIN_GAP, margin=MARGIN, vote_n=0, vote_ratio=VOTE_RATIO):
        self.conf_min, self.confirm_n, self.clear_n, self.stuck_ms, self.join_gap = conf_min, confirm_n, clear_n, stuck_ms, join_gap
        self.margin = margin
        self.vote_n, self.vote_ratio = vote_n, vote_ratio  # vote_n 이 0 이면 연속 방식 (PiJudge 는 VOTE_N 을 넘긴다)
        self.reset()

    def reset(self) -> None:
        self.waiting = False        # True 면 WAIT_CLEAR (확정 뒤 트레이가 비길 기다림)
        self.cand, self.streak, self.clear_streak, self.wait_start = None, 0, 0, 0
        self.votes = collections.deque(maxlen=max(self.vote_n, 1))  # 최근 프레임의 (1등 종류 또는 None, 확신도)

    @staticmethod
    def group(dets, gap):
        """dets: (종류, 확신도, x, y, w, h) 목록 → 같은 종류이고 붙은 칸끼리 묶은 [(종류, 최대 확신도, 칸 수)]"""
        n = len(dets)
        label = list(range(n))

        def find(a):
            while label[a] != a:
                label[a] = label[label[a]]
                a = label[a]
            return a

        for i in range(n):
            for j in range(i + 1, n):
                a, b = dets[i], dets[j]
                if a[0] != b[0]:
                    continue
                apart = (a[2] > b[2] + b[4] + gap or b[2] > a[2] + a[4] + gap or
                         a[3] > b[3] + b[5] + gap or b[3] > a[3] + a[5] + gap)
                if not apart:
                    label[find(i)] = find(j)
        objs, used = [], set()
        for i in range(n):
            r = find(i)
            if r in used:
                continue
            used.add(r)
            members = [dets[k] for k in range(n) if find(k) == r]
            objs.append((dets[i][0], max(m[1] for m in members), len(members)))
        return objs

    def _vote(self, top, m, now_ms):
        """다수결 한 프레임 처리. top 은 이번 프레임에서 확신도가 conf_min 이상인 1등 물체 (종류, 확신도, 칸 수)"""
        self.votes.append((top[0], top[1]))
        return self._vote_check(m, now_ms)

    def _vote_check(self, m, now_ms):
        counts = collections.Counter(label for label, _ in self.votes if label)
        need = math.ceil(self.vote_ratio * self.vote_n)
        if counts:
            lead, lead_n = counts.most_common(1)[0]
        else:
            lead, lead_n = None, 0
        self.cand = lead
        self.streak = min(self.confirm_n, int(self.confirm_n * lead_n / need)) if lead else 0  # 대시보드에 보여 줄 진행도 (0~confirm_n)
        if lead and len(self.votes) >= self.vote_n and lead_n >= need:
            confs = [c for label, c in self.votes if label == lead]
            out = ("decision", lead, sum(confs) / len(confs), m)
            self.waiting, self.wait_start, self.clear_streak = True, now_ms, 0
            self.cand, self.streak = None, 0
            self.votes.clear()
            return out
        return "none", None, 0.0, m

    def update(self, dets, now_ms):
        objs = self.group(dets, self.join_gap)
        m = len(objs)
        top = max(objs, key=lambda o: o[1]) if objs else None
        if not self.waiting:
            if top is None or top[1] < self.conf_min:
                if self.vote_n > 0:
                    self.votes.append((None, 0.0))
                    return self._vote_check(m, now_ms)
                self.cand, self.streak = None, 0
                return "none", None, 0.0, m
            if self.vote_n > 0:  # 다수결 방식: 최근 vote_n 장 중 vote_ratio 이상이 같은 종류일 때 확정
                return self._vote(top, m, now_ms)
            other = max((o[1] for o in objs if o[0] != top[0]), default=0.0)  # 다른 종류 중 가장 확신하는 것
            if self.margin and top[1] - other < self.margin:  # 캔·페트처럼 비슷하게 의심되는 장면은 확정하지 않고 기다린다
                self.cand, self.streak = None, 0
                return "none", None, 0.0, m
            if top[0] == self.cand:
                self.streak += 1
            else:
                self.cand, self.streak = top[0], 1
            if self.streak >= self.confirm_n:
                out = ("decision", self.cand, top[1], m)
                self.waiting, self.wait_start, self.clear_streak, self.cand, self.streak = True, now_ms, 0, None, 0
                return out
            return "none", None, 0.0, m
        if m == 0:
            self.clear_streak += 1
            if self.clear_streak >= self.clear_n:
                self.reset()
            return "none", None, 0.0, m
        self.clear_streak = 0
        if now_ms - self.wait_start >= self.stuck_ms:
            self.wait_start = now_ms  # 다음 STUCK 은 stuck_ms 뒤에 다시
            return "stuck", None, 0.0, m
        return "none", None, 0.0, m


class PiJudge:
    """샤오 사진 → 파이에서 모델 → 판정 줄을 on_line 으로 넘긴다 (스레드 하나)."""

    def __init__(self, cam, model_path: str, on_line, interval_s: float = 0.0) -> None:
        self.cam, self.model_path, self.on_line, self.interval_s = cam, model_path, on_line, interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.detector = Detector(vote_n=VOTE_N)
        log = os.environ.get("JUDGE_LOG", str(Path(model_path).parent.parent / "judge_log"))
        self.log_dir: Path | None = None if log.lower() == "none" else Path(log)  # 확정한 순간의 사진·확신도를 남긴다
        self.last_ms: int | None = None
        self.last_jpeg: bytes | None = None  # 판정에 쓴 마지막 사진 (대시보드 영상으로 다시 보내 준다)
        self.frame_seq = 0
        self.last_dets: list = []   # 마지막 프레임의 검출 칸 (종류, 확신도, x, y)
        self.frames = 0
        self.error: str | None = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="pi-judge", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def frame_obj(self, dets, m: int, ms: int) -> dict:
        """판정이 아닌 프레임 한 줄. 대시보드가 쓰는 state·probs·box·streak 을 같이 준다 (event 가 'frame' 이면 그대로 씀)."""
        d = self.detector
        state = "wait_empty" if d.waiting else ("detecting" if m else "ready")  # 확정 뒤에는 트레이가 비길 기다림
        probs: dict = {}
        for label, conf, *_ in dets:
            probs[label] = max(probs.get(label, 0.0), round(conf, 2))
        probs["empty"] = 0.0 if m else 1.0
        box = None
        if dets:
            top = max(dets, key=lambda x: x[1])
            same = [x for x in dets if x[0] == top[0]]  # 가장 확신하는 종류의 칸들을 감싸는 네모 (모델 입력 96x96 기준 → 0~1)
            x0, y0 = min(x[2] for x in same), min(x[3] for x in same)
            x1, y1 = max(x[2] + x[4] for x in same), max(x[3] + x[5] for x in same)
            box = [round(x0 / 96, 3), round(y0 / 96, 3), round((x1 - x0) / 96, 3), round((y1 - y0) / 96, 3)]
        top_cls = max(dets, key=lambda x: x[1]) if dets else None  # 이 프레임에서 퍼센트가 제일 높은 종류
        return {"event": "frame", "class": None, "conf": 0.0, "ms": ms, "n": m, "state": state,
                "probs": probs, "box": box, "streak": d.streak,
                "top": {"class": top_cls[0], "conf": round(top_cls[1], 2)} if top_cls else None}

    def _save_decision(self, jpg: bytes, cls: str, conf: float, dets) -> None:
        """확정한 순간의 사진과 검출을 judge_log/ 에 남긴다 (잘못 본 사례를 보고 재학습 사진으로 쓰려고). 최근 LOG_KEEP 장만 둔다."""
        if self.log_dir is None:
            return
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            (self.log_dir / f"{stamp}_{cls}_{int(conf * 100)}.jpg").write_bytes(jpg)
            with (self.log_dir / "decisions.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"time": stamp, "class": cls, "conf": round(conf, 2),
                                    "dets": [[d[0], round(d[1], 2), d[2], d[3]] for d in dets][:8]}, ensure_ascii=False) + "\n")
            files = sorted(self.log_dir.glob("*.jpg"))
            for old in files[:-LOG_KEEP]:
                old.unlink()
        except OSError as e:
            print(f"[judge] 확정 사진 저장 실패: {e}")

    def _emit(self, obj: dict) -> None:
        self.on_line(json.dumps(obj, ensure_ascii=False))

    def _run(self) -> None:
        try:
            sys.modules.setdefault("pyaudio", types.ModuleType("pyaudio"))  # 오디오는 안 쓴다 (설치 없이 import 만 통과)
            import cv2
            import numpy as np
            from edge_impulse_linux.image import ImageImpulseRunner

            runner = ImageImpulseRunner(self.model_path)
            runner.init()
        except Exception as e:  # 모델 파일·SDK 가 없으면 판정만 못 한다 (서버는 계속 돈다)
            self.error = f"{type(e).__name__}: {e}"
            print(f"[judge] 시작 실패: {self.error}")
            return
        print(f"[judge] 파이 판정 시작: {self.model_path}")
        misses = 0
        try:
            while not self._stop.is_set():
                t0 = time.time()
                jpg = self.cam.jpeg()
                if jpg is None:
                    misses += 1
                    if misses >= 3:
                        self._emit({"error": "camera"})
                    self._stop.wait(0.5)
                    continue
                misses = 0
                self.last_jpeg = jpg
                self.frame_seq += 1
                img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                if img is None:
                    continue
                h, w = img.shape[:2]
                side = min(h, w)  # 학습과 같게 중앙 정사각형으로 자른다
                sq = img[(h - side) // 2:(h - side) // 2 + side, (w - side) // 2:(w - side) // 2 + side]
                feats, _ = runner.get_features_from_image(cv2.cvtColor(sq, cv2.COLOR_BGR2RGB))
                boxes = runner.classify(feats)["result"].get("bounding_boxes", [])
                dets = [(b["label"], float(b["value"]), b["x"], b["y"], b["width"], b["height"])
                        for b in boxes if b["value"] >= DET_MIN]
                event, cls, conf, m = self.detector.update(dets, int(time.monotonic() * 1000))
                ms = int((time.time() - t0) * 1000)  # 사진을 받기 시작한 때부터 판정까지 (사진은 이보다 늦게 찍히지 않는다)
                self.last_ms = ms
                self.frames += 1
                self.last_dets = sorted(((d[0], round(d[1], 2), d[2], d[3]) for d in dets), key=lambda d: -d[1])[:8]
                if event == "decision":
                    self._save_decision(jpg, cls, conf, dets)
                    self._emit({"class": cls, "conf": round(conf, 2), "ms": ms, "n": m})
                else:
                    self._emit(self.frame_obj(dets, m, ms))
                if self.interval_s:
                    self._stop.wait(self.interval_s)
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            print(f"[judge] 중단: {self.error}")
        finally:
            try:
                runner.stop()
            except Exception:
                pass
