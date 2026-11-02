"""파이(리눅스 aarch64)용 모델 파일(.eim)을 받는다:  python build_eim.py [저장할 경로]

float32 로 받아야 한다. 리눅스용 int8 은 이 프로젝트에서 모든 출력이 비어 쓸 수 없었다 (jeongmin/robot/server/judge.py 참고).
키는 yujeong/.env 의 EI_API_KEY 에서 읽고 출력하지 않는다 (train_ei.py 와 같다). 프로젝트 데이터는 바꾸지 않고 빌드만 요청한다.
"""
import sys
from pathlib import Path

import train_ei as t

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("jyj25.eim")
TYPE = "runner-linux-aarch64"
j = t.call("POST", f"{t.P}/jobs/build-ondevice-model?type={TYPE}", {"engine": "tflite", "modelType": "float32"})
t.job_wait(j["id"], "Linux aarch64 float32 모델 빌드")
raw = t.call("GET", f"{t.P}/deployment/download?type={TYPE}&modelType=float32", raw=True)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(raw)
print("저장:", out, len(raw), "bytes")
