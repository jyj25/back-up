// 객체 검출(FOMO) 결과로 "무엇을 집을지" 정하는 순수 로직 (모델·하드웨어와 무관)
// 입력: 프레임마다 검출 목록 / 출력: 판정 이벤트 (IF-01: 한 번에 종류 하나)
//
//   1. 같은 종류이고 붙어 있는 칸(FOMO 는 칸 단위)을 한 물체로 묶는다.
//   2. 물체가 여럿이면 확신도가 가장 높은 것 하나를 대상으로 고른다 (임시 기준 — 로봇 담당과 확정 필요).
//   3. 대상 종류가 confirm_n 번 연속 같고 확신도 ≥ conf_min 이면 DECISION 한 번.
//   4. 판정 뒤에는 검출이 clear_n 번 연속 없을 때(트레이가 빔)까지 새 판정을 내지 않는다. stuck_ms 안에 안 비면 STUCK.
#pragma once
#include <stdint.h>

namespace detect {

enum Event : uint8_t { EV_NONE = 0, EV_DECISION = 1, EV_STUCK = 2 };
enum State : uint8_t { ST_IDLE = 0, ST_WAIT_CLEAR = 1 };

struct Det {          // 검출 칸 하나 (모델 입력 좌표, 96x96)
  int8_t cls;         // 클래스 번호
  float conf;
  int16_t x, y, w, h;
};

struct Object {       // 묶은 물체
  int8_t cls;
  float conf;         // 칸 확신도의 최댓값
  int cells;
};

struct Config {
  float conf_min = 0.80f;    // 판정 확신도 하한 (라즈봇 sorter.py 의 min_confidence 와 같게)
  uint8_t confirm_n = 3;
  uint8_t clear_n = 3;
  uint32_t stuck_ms = 10000;
  int16_t join_gap = 2;      // 두 칸 사이가 이 픽셀 이하면 붙은 것으로 본다
};

struct Result {
  Event event;
  int8_t cls;       // DECISION 일 때
  float conf;
  int objects;      // 이번 프레임에서 묶은 물체 수
};

// 칸들을 같은 종류끼리 붙은 것으로 묶는다. objs 에 최대 max_objs 개를 쓰고 개수를 돌려준다.
inline int group(const Det* d, int n, int16_t gap, Object* objs, int max_objs) {
  int label[64];
  if (n > 64) n = 64;
  for (int i = 0; i < n; i++) label[i] = i;
  auto find = [&](int a) { while (label[a] != a) a = label[a] = label[label[a]]; return a; };
  for (int i = 0; i < n; i++)
    for (int j = i + 1; j < n; j++) {
      if (d[i].cls != d[j].cls) continue;
      bool apart = d[i].x > d[j].x + d[j].w + gap || d[j].x > d[i].x + d[i].w + gap ||
                   d[i].y > d[j].y + d[j].h + gap || d[j].y > d[i].y + d[i].h + gap;
      if (!apart) label[find(i)] = find(j);
    }
  int m = 0;
  bool used[64] = {false};
  for (int i = 0; i < n; i++) {
    int r = find(i);
    if (used[r]) continue;
    used[r] = true;
    if (m >= max_objs) break;
    Object o = {d[i].cls, 0, 0};
    for (int k = 0; k < n; k++)
      if (find(k) == r) { o.cells++; if (d[k].conf > o.conf) o.conf = d[k].conf; }
    objs[m++] = o;
  }
  return m;
}

class Detector {
 public:
  explicit Detector(const Config& c = Config()) : cfg_(c) { reset(); }
  void reset() { state_ = ST_IDLE; cand_ = -1; streak_ = 0; clear_streak_ = 0; wait_start_ = 0; }
  State state() const { return state_; }

  Result update(const Det* d, int n, uint32_t now_ms) {
    Object objs[16];
    int m = group(d, n, cfg_.join_gap, objs, 16);
    int top = -1;
    for (int i = 0; i < m; i++) if (top < 0 || objs[i].conf > objs[top].conf) top = i;

    if (state_ == ST_IDLE) {
      if (top < 0 || objs[top].conf < cfg_.conf_min) { cand_ = -1; streak_ = 0; return make(EV_NONE, m); }
      if (objs[top].cls == cand_) streak_++; else { cand_ = objs[top].cls; streak_ = 1; }
      if (streak_ >= cfg_.confirm_n) {
        Result r = {EV_DECISION, (int8_t)cand_, objs[top].conf, m};
        state_ = ST_WAIT_CLEAR; wait_start_ = now_ms; clear_streak_ = 0; cand_ = -1; streak_ = 0;
        return r;
      }
      return make(EV_NONE, m);
    }
    // WAIT_CLEAR
    if (m == 0) {
      if (++clear_streak_ >= cfg_.clear_n) { reset(); }
      return make(EV_NONE, m);
    }
    clear_streak_ = 0;
    if (now_ms - wait_start_ >= cfg_.stuck_ms) {
      wait_start_ = now_ms;  // 다음 STUCK 은 stuck_ms 뒤에 다시
      return make(EV_STUCK, m);
    }
    return make(EV_NONE, m);
  }

 private:
  static Result make(Event e, int m) { Result r = {e, -1, 0.0f, m}; return r; }
  Config cfg_;
  State state_;
  int8_t cand_;
  uint8_t streak_, clear_streak_;
  uint32_t wait_start_;
};

}  // namespace detect
