"""보드(ESP32S3)가 USB 시리얼로 내보내는 판정 JSON 을 읽어 보여 주는 확인용 프로그램.
라즈봇(리눅스)과 노트북(Windows) 모두에서 쓴다.

  pip install pyserial
  python pi_reader.py /dev/ttyACM0        # 라즈봇
  python pi_reader.py COM4                # 노트북

보드가 한 줄에 하나씩 이런 JSON 을 내보낸다고 가정한다 (docs/A07-interface.md IF-02):
  {"class":"can","conf":0.93,"ms":173}   {"class":null,"conf":0.41,"ms":173}   {"error":"camera"}
'{' 로 시작하지 않는 줄(부팅·디버그 로그)은 버린다. 10초 동안 아무 줄도 없으면 경고한다.
"""
import json
import sys
import time
from collections import Counter


def parse_line(raw):
    """한 줄을 해석한다. JSON 객체면 dict, 아니면 None (로그 줄이거나 깨진 줄)."""
    line = raw.strip()
    if not line.startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def describe(obj):
    if "error" in obj:
        return "오류: %s" % obj["error"]
    if obj.get("class") is None:
        return "판정 없음 (확신도 %.2f)" % obj.get("conf", 0)
    return "%s  확신도 %.2f  (%s ms)" % (obj["class"], obj.get("conf", 0), obj.get("ms", "?"))


def main(port):
    import serial  # pyserial

    counts = Counter()
    last_rx = time.time()
    with serial.Serial(port, 115200, timeout=1) as ser:
        print("연결됨:", port, "(Ctrl+C 로 종료)")
        try:
            while True:
                raw = ser.readline().decode("utf-8", errors="replace")
                now = time.time()
                if not raw:
                    if now - last_rx > 10:
                        print("경고: 10초 동안 보드에서 아무것도 안 옴 (케이블/전원/펌웨어 확인)")
                        last_rx = now
                    continue
                last_rx = now
                obj = parse_line(raw)
                if obj is None:
                    continue
                counts["오류" if "error" in obj else (obj.get("class") or "판정없음")] += 1
                print(describe(obj))
        except KeyboardInterrupt:
            pass
    print("\n요약:", dict(counts))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("사용법: python pi_reader.py <포트>   예) /dev/ttyACM0 또는 COM4")
    main(sys.argv[1])
