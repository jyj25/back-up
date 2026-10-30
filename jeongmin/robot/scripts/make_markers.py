"""stations.json 의 정류장마다 인쇄용 ArUco 마커를 만든다 (노트북에서, opencv 필요).

    python scripts/make_markers.py        → markers/ 에 PNG + 인쇄용 markers.html

인쇄: markers.html 을 브라우저로 열고 인쇄 (배율 100%, '페이지에 맞춤' 끄기) → 한 변 10cm.
통 앞면, 로봇 카메라 높이(바닥에서 약 15cm)에 붙인다. 구기거나 접히면 인식이 안 된다.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import cv2

ROBOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROBOT))
from server.vision import MARKER_DICT  # noqa: E402

OUT = ROBOT / "markers"
SIDE_CM = 10


def main() -> None:
    stations = json.loads((ROBOT / "stations.json").read_text(encoding="utf-8"))["stations"]
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, MARKER_DICT))
    OUT.mkdir(exist_ok=True)
    cards = []
    for name, info in stations.items():
        img = cv2.aruco.generateImageMarker(d, info["marker"], 600)
        img = cv2.copyMakeBorder(img, 75, 75, 75, 75, cv2.BORDER_CONSTANT, value=255)  # 흰 테두리 필수
        path = OUT / f"marker_{info['marker']}_{name}.png"
        cv2.imwrite(str(path), img)
        b64 = base64.b64encode(path.read_bytes()).decode()
        cards.append(f'<div class="card"><img src="data:image/png;base64,{b64}">'
                     f'<p><b>{info["label"]}</b> · {name} · 마커 {info["marker"]}</p></div>')
        print("만듦:", path.name)
    # 마커 본체가 SIDE_CM 이 되도록 흰 테두리까지 포함한 크기로 인쇄
    total_cm = SIDE_CM * 750 / 600
    (OUT / "markers.html").write_text(f"""<!doctype html><meta charset="utf-8"><title>라즈봇 마커</title>
<style>
  @page {{ size: A4; margin: 10mm; }}
  body {{ font-family: sans-serif; margin: 0; }}
  .card {{ display: inline-block; text-align: center; margin: 4mm; page-break-inside: avoid; border: 1px dashed #bbb; }}
  .card img {{ width: {total_cm}cm; height: {total_cm}cm; display: block; }}
  p {{ margin: 2mm 0; font-size: 14pt; }}
</style>
<p>인쇄 배율 100% · 검은 사각형 한 변이 {SIDE_CM}cm 인지 자로 확인 · 점선을 따라 자르기</p>
{''.join(cards)}
""", encoding="utf-8")
    print("인쇄용:", OUT / "markers.html")


if __name__ == "__main__":
    main()
