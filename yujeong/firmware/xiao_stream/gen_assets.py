"""ai/collector 의 index.html, jszip.min.js 를 gzip 해서 펌웨어용 web_assets.h 로 만든다.
수집기를 고치면 이 스크립트를 다시 돌리고 펌웨어를 올린다:  python gen_assets.py"""
import gzip, pathlib

here = pathlib.Path(__file__).parent
src = here.parent.parent.parent / "ai" / "collector"
out = ["// 자동 생성 (gen_assets.py). 직접 수정하지 말 것.\n#pragma once\n#include <stdint.h>\n"]
for name, var in (("index.html", "INDEX_HTML"), ("jszip.min.js", "JSZIP_JS")):
    data = gzip.compress((src / name).read_bytes(), 9)
    body = ",".join(str(b) for b in data)
    out.append(f"const uint8_t {var}[] = {{{body}}};\nconst unsigned int {var}_LEN = {len(data)};\n")
(here / "web_assets.h").write_text("".join(out))
print("ok")
