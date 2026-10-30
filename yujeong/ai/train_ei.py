"""Edge Impulse 업로드 + 학습 + 결과 확인 (표준 라이브러리만 사용).

사용:  python train_ei.py upload  <dataset_dir>   # 폴더별(can/empty/paper/pet, general_trash 는 있으면) 업로드, 기존 샘플은 비활성화
       python train_ei.py train                    # 임펄스 설정 + 특징 생성 + 학습
       python train_ei.py status                   # 정확도·혼동행렬·메모리 확인
       python train_ei.py test                     # 보관해 둔 테스트 세트로 평가
       python train_ei.py wasm                     # 브라우저 테스트용 모델(tester/) 내려받기

키는 yujeong/.env 의 EI_API_KEY 에서 읽고 출력하지 않는다.
검증 세트를 시간 순으로 나누는 이유: 연사로 찍은 사진은 서로 거의 같아서
무작위로 나누면 학습 사진과 거의 같은 사진이 테스트에 섞여 정확도가 부풀려진다.
"""
import json, sys, time, uuid, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV = HERE.parent / ".env"
STUDIO = "https://studio.edgeimpulse.com/v1/api"
INGEST = "https://ingestion.edgeimpulse.com/api"
CLASSES = ["can", "empty", "general_trash", "paper", "pet"]
OTHER = "general_trash"  # 캔·페트·종이·빈 트레이 외의 모든 것
TEST_FRACTION = 0.2  # 클래스별로 가장 늦게 찍은 20% 는 테스트 세트


def api_key():
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("EI_API_KEY"):
            return line.split("=", 1)[1].strip().strip("\"'")
    sys.exit(".env 에 EI_API_KEY 가 없습니다")


KEY = api_key()


def call(method, url, body=None, headers=None, raw=False, timeout=120):
    h = {"x-api-key": KEY}
    h.update(headers or {})
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as f:
            out = f.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} {method} {url.split('?')[0]}: {e.read()[:300]!r}")
    if raw:
        return out
    j = json.loads(out)
    if not j.get("success", True):
        sys.exit(f"API 실패 {method} {url.split('?')[0]}: {j.get('error')}")
    return j


def project_id():
    ps = call("GET", f"{STUDIO}/projects")["projects"]
    if len(ps) != 1:
        sys.exit(f"프로젝트가 {len(ps)}개입니다. 키에 연결된 프로젝트를 확인하세요")
    return ps[0]["id"]


PID = project_id()
P = f"{STUDIO}/{PID}"


def multipart(fields, fname, content):
    b = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="data"; filename="{fname}"\r\n'
                 f'Content-Type: image/jpeg\r\n\r\n'.encode() + content + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={b}"


def list_samples(cat):
    out, off = [], 0
    while True:
        d = call("GET", f"{P}/raw-data?category={cat}&limit=500&offset={off}")
        out += d["samples"]
        if len(out) >= d["totalCount"] or not d["samples"]:
            return out
        off += 500


def adopt_old():
    """프로젝트에 원래 있던 다른 물건 사진(airpod 등)을 general_trash 로 옮긴다. 원본은 비활성화만."""
    n = 0
    have = {s["filename"] for c in ("training", "testing") for s in list_samples(c)}
    for cat in ("training", "testing"):
        for s in list_samples(cat):
            if s["label"] in CLASSES:
                continue
            img = call("GET", f"{P}/raw-data/{s['id']}/image", raw=True)
            name = f"{OTHER}.old{s['id']}.jpg"
            if name not in have:
                body, ct = multipart({}, name, img)
                call("POST", f"{INGEST}/{cat}/files", body, {"Content-Type": ct, "x-label": OTHER})
                n += 1
            call("POST", f"{P}/raw-data/{s['id']}/disable", {})
    print(f"기존 다른 물건 사진 {n}장을 {OTHER} 로 이동(원본은 비활성화)")


def cmd_upload(ds):
    ds = Path(ds)
    adopt_old()
    have = {s["filename"].rsplit(".", 1)[0] for c in ("training", "testing") for s in list_samples(c)}
    n = 0
    for cls in CLASSES:
        if not (ds / cls).is_dir():
            continue
        files = sorted((ds / cls).glob("*.jpg"))  # 파일명에 시각이 있어 이름순 = 촬영순
        cut = len(files) - round(len(files) * TEST_FRACTION)
        for i, f in enumerate(files):
            if f.stem in have or f.name in have:
                continue
            cat = "training" if i < cut else "testing"
            body, ct = multipart({}, f.name, f.read_bytes())
            call("POST", f"{INGEST}/{cat}/files", body,
                 {"Content-Type": ct, "x-label": cls, "x-disallow-duplicates": "1"})
            n += 1
        print(f"{cls}: {len(files)}장 (학습 {cut} / 테스트 {len(files) - cut})")
    print(f"업로드 {n}장")


def job_wait(job_id, label):
    last = 0
    while True:
        d = call("GET", f"{P}/jobs/{job_id}/status")["job"]
        if d.get("finished"):
            if not d.get("finishedSuccessful"):
                logs = call("GET", f"{P}/jobs/{job_id}/stdout")
                tail = "".join(x["data"] for x in logs["stdout"][-15:])
                sys.exit(f"{label} 실패:\n{tail}")
            print(f"{label} 완료")
            return
        time.sleep(5)


def cmd_train(cycles=50):
    imp = call("GET", f"{P}/impulse")["impulse"]
    learn = imp["learnBlocks"][0]["id"]
    dsp = imp["dspBlocks"][0]["id"]
    # 파라미터는 기존 값(MobileNetV2 0.35 96x96, 증강 all, 클래스 가중치 자동)을 유지하고 학습 횟수만 지정
    call("POST", f"{P}/training/keras/{learn}", {"trainingCycles": cycles})
    j = call("POST", f"{P}/jobs/generate-features",
             {"dspId": dsp, "calculateFeatureImportance": False, "skipFeatureExplorer": True})
    job_wait(j["id"], "특징 생성")
    j = call("POST", f"{P}/jobs/train/keras/{learn}", {"mode": "visual", "trainingCycles": cycles})
    job_wait(j["id"], "학습")
    cmd_status()


def cmd_wasm(out="tester"):
    """브라우저에서 모델을 돌리는 WebAssembly 배포본을 받아 tester/ 에 풀고, wasm 은 gzip+base64 JS 로 변환
    (file:// 로 열어도 fetch 없이 동작하게 하려는 것)."""
    import base64, gzip, io, zipfile
    out = Path(out) if Path(out).is_absolute() else HERE / out
    j = call("POST", f"{P}/jobs/build-ondevice-model?type=wasm", {"engine": "tflite", "modelType": "int8"})
    job_wait(j["id"], "WASM 빌드")
    z = zipfile.ZipFile(io.BytesIO(call("GET", f"{P}/deployment/download?type=wasm&modelType=int8", raw=True)))
    out.mkdir(exist_ok=True)
    for n in ("edge-impulse-standalone.js", "run-impulse.js"):
        (out / n).write_bytes(z.read("browser/" + n))
    gz = gzip.compress(z.read("browser/edge-impulse-standalone.wasm"), 9)
    (out / "model-wasm.js").write_text("window.MODEL_WASM_GZ_B64='" + base64.b64encode(gz).decode() + "';" + chr(10))
    print("저장:", out)


def cmd_status():
    imp = call("GET", f"{P}/impulse")["impulse"]
    learn = imp["learnBlocks"][0]["id"]
    d = call("GET", f"{P}/training/keras/{learn}/metadata")
    for m in d.get("modelValidationMetrics", []):
        print(f"[검증 {m['type']}] 정확도 {m.get('isSupportedOnDevice')}")
    print(json.dumps(d, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "upload":
        cmd_upload(a[1])
    elif a[0] == "train":
        cmd_train(*(int(x) for x in a[1:2]))
    elif a[0] == "wasm":
        cmd_wasm(*a[1:2])
    elif a[0] == "status":
        cmd_status()
    else:
        sys.exit(__doc__)
