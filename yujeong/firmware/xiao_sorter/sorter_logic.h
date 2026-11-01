// 쓰레기 판정 로직 (모델과 무관, 하드웨어와 무관한 순수 로직)
// 입력: 프레임마다 클래스별 확신도 / 출력: "이번에 서보를 움직일지" 이벤트
//
// 상태 2개
//   IDLE        빈 트레이 또는 물건 확인 중. 같은 물건이 N번 연속 + 확신도·격차 기준을 넘으면 DECISION 한 번.
//   WAIT_CLEAR  판정을 낸 뒤. 트레이가 비었다(empty)고 M번 연속 나올 때까지 새 판정을 내지 않는다
//               (같은 물건을 두 번 세거나, 서보가 움직이는 동안의 흔들림에 반응하는 것을 막음).
//               stuck_ms 안에 비지 않으면 STUCK 이벤트 (물건이 안 떨어졌다).
#pragma once
#include <stdint.h>

namespace sorter {

enum Event : uint8_t { EV_NONE = 0, EV_DECISION = 1, EV_STUCK = 2 };
enum State : uint8_t { ST_IDLE = 0, ST_WAIT_CLEAR = 1 };

struct Config {
  uint8_t num_classes = 4;
  uint8_t empty_idx = 1;        // Edge Impulse 라벨은 알파벳순: can(0) empty(1) paper(2) pet(3)
  float conf_min = 0.80f;       // 1등 확신도 하한
  float margin_min = 0.20f;     // 1등과 2등의 차이 하한 (애매한 경우 거절)
  uint8_t confirm_n = 3;        // 같은 결과 연속 횟수
  uint8_t clear_n = 3;          // 판정 후 "비었음" 연속 횟수
  float empty_conf_min = 0.70f; // "비었음"으로 인정할 확신도
  uint32_t stuck_ms = 10000;    // 판정 후 이 시간 안에 안 비면 STUCK
};

struct Result {
  Event event;
  int8_t cls;    // DECISION 일 때 클래스 번호, 아니면 -1
  float conf;    // DECISION 일 때 확신도
};

class Sorter {
 public:
  explicit Sorter(const Config& c = Config()) : cfg_(c) { reset(); }

  void reset() { state_ = ST_IDLE; cand_ = -1; streak_ = 0; clear_streak_ = 0; wait_start_ = 0; }
  State state() const { return state_; }

  // scores: num_classes 개 (0~1). 서보가 움직이는 중에는 호출해도 되고 안 해도 된다.
  Result update(const float* scores, uint32_t now_ms) {
    int top = 0, second = -1;
    for (int i = 1; i < cfg_.num_classes; i++) {
      if (scores[i] > scores[top]) { second = top; top = i; }
      else if (second < 0 || scores[i] > scores[second]) second = i;
    }
    float conf = scores[top];
    float margin = second >= 0 ? conf - scores[second] : conf;

    if (state_ == ST_IDLE) {
      bool ok = conf >= cfg_.conf_min && margin >= cfg_.margin_min && top != cfg_.empty_idx;
      if (!ok) { cand_ = -1; streak_ = 0; return none(); }
      if (top == cand_) streak_++; else { cand_ = top; streak_ = 1; }
      if (streak_ >= cfg_.confirm_n) {
        Result r = {EV_DECISION, (int8_t)cand_, conf};
        state_ = ST_WAIT_CLEAR; wait_start_ = now_ms; clear_streak_ = 0; cand_ = -1; streak_ = 0;
        return r;
      }
      return none();
    }

    // ST_WAIT_CLEAR
    if (top == cfg_.empty_idx && conf >= cfg_.empty_conf_min) clear_streak_++; else clear_streak_ = 0;
    if (clear_streak_ >= cfg_.clear_n) { state_ = ST_IDLE; cand_ = -1; streak_ = 0; return none(); }
    if (now_ms - wait_start_ >= cfg_.stuck_ms) {   // 부호 없는 뺄셈이라 millis() 오버플로에도 안전
      wait_start_ = now_ms;                         // 같은 간격으로 다시 알림
      return {EV_STUCK, -1, 0};
    }
    return none();
  }

 private:
  static Result none() { return {EV_NONE, -1, 0}; }
  Config cfg_;
  State state_;
  int8_t cand_;
  uint8_t streak_, clear_streak_;
  uint32_t wait_start_;
};

}  // namespace sorter
