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

import json
import sys
import threading
import time
import types

DET_MIN = 0.60     # 칸 하나를 검출로 인정하는 확신도 (EI 평가와 같음)
CONF_MIN = 0.80    # 확정 확신도 하한 (sorter.py 의 min_confidence 와 같게)
CONFIRM_N = 3      # 같은 결과가 이만큼 연속이어야 확정
CLEAR_N = 3        # 확정 뒤 물체가 이만큼 연속 없어야 다시 판정
STUCK_MS = 10000
JOIN_GAP = 2       # 두 칸 사이가 이 픽셀 이하면 붙은 것으로 본다


class Detector:
    """detect_logic.h 의 detect::Detector 를 옮긴 것. update 는 (event, 종류, 확신도, 물체 수)를 돌려준다."""

    def __init__(self, conf_min=CONF_MIN, confirm_n=CONFIRM_N, clear_n=CLEAR_N, stuck_ms=STUCK_MS, join_gap=JOIN_GAP):
        self.conf_min, self.confirm_n, self.clear_n, self.stuck_ms, self.join_gap = conf_min, confirm_n, clear_n, stuck_ms, join_gap
        self.reset()

    def reset(self) -> None:
        self.waiting = False        # True 면 WAIT_CLEAR (확정 뒤 트레이가 비길 기다림)
        self.cand, self.streak, self.clear_streak, self.wait_start = None, 0, 0, 0

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

    def update(self, dets, now_ms):
        objs = self.group(dets, self.join_gap)
        m = len(objs)
        top = max(objs, key=lambda o: o[1]) if objs else None
        if not self.waiting:
            if top is None or top[1] < self.conf_min:
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
        self.detector = Detector()
        self.last_ms: int | None = None
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
                    self._emit({"class": cls, "conf": round(conf, 2), "ms": ms, "n": m})
                else:
                    self._emit({"class": None, "conf": 0.0, "ms": ms, "n": m})
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
