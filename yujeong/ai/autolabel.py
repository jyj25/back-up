"""물체 박스 자동 라벨링 (GrabCut) — 바닥 위의 물체만 잡아서 객체 검출(FOMO) 학습용 박스를 만든다.

사용:  python autolabel.py <사진폴더 여러 개> --out boxes.json [--preview preview_dir]
        폴더 이름이 클래스 (can / paper / pet / general_trash). empty 폴더는 박스 없음(빈 트레이)으로 기록한다.
필요:  pip install opencv-python-headless numpy pillow

자동 박스는 틀릴 수 있다 (물체가 바닥과 비슷하거나 화면을 가득 채우면). 반드시 preview 로 눈으로 확인하고,
이상한 것은 제외한다 (--drop 파일이름목록).
"""
import argparse, hashlib, json, os, sys
import cv2
import numpy as np

MIN_AREA = 0.02   # 화면 대비 이 비율보다 작은 덩어리는 무시
MAX_AREA = 0.92   # 거의 화면 전체면 실패로 본다 (바닥을 물체로 잡음)


def boxes_for(img):
    h, w = img.shape[:2]
    m = np.zeros((h, w), np.uint8)
    mx, my = max(2, int(w * 0.03)), max(2, int(h * 0.03))
    rect = (mx, my, w - 2 * mx, h - 2 * my)
    bgd, fgd = np.zeros((1, 65)), np.zeros((1, 65))
    try:
        cv2.grabCut(img, m, rect, bgd, fgd, 6, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        return []
    fg = np.where((m == 1) | (m == 3), 255, 0).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(fg)
    out = []
    for i in range(1, n):
        x, y, bw, bh, a = stats[i]
        if a / (w * h) >= MIN_AREA:
            out.append([int(x), int(y), int(bw), int(bh)])
    if len(out) == 1 and out[0][2] * out[0][3] / (w * h) > MAX_AREA:
        return []
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview")
    a = ap.parse_args()
    seen, res = set(), {}
    for d in a.dirs:
        for cls in sorted(os.listdir(d)):
            cd = os.path.join(d, cls)
            if not os.path.isdir(cd):
                continue
            for f in sorted(os.listdir(cd)):
                if not f.lower().endswith(".jpg"):
                    continue
                p = os.path.join(cd, f)
                hsh = hashlib.md5(open(p, "rb").read()).hexdigest()
                if hsh in seen:
                    continue
                seen.add(hsh)
                img = cv2.imread(p)
                if img is None:
                    continue
                h, w = img.shape[:2]
                boxes = [] if cls == "empty" else boxes_for(img)
                res[p] = {"label": cls, "w": w, "h": h, "boxes": boxes, "md5": hsh}
                if a.preview:
                    os.makedirs(a.preview, exist_ok=True)
                    v = img.copy()
                    for x, y, bw, bh in boxes:
                        cv2.rectangle(v, (x, y), (x + bw, y + bh), (0, 0, 255), 2)
                    cv2.imwrite(os.path.join(a.preview, f), v)
    json.dump(res, open(a.out, "w"), ensure_ascii=False)
    objs = [r for r in res.values() if r["label"] != "empty"]
    print(f"{len(res)}장 (물체 {len(objs)}장, 박스 못 찾음 {sum(1 for r in objs if not r['boxes'])}장)")


if __name__ == "__main__":
    main()
