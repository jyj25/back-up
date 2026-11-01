// sorter_logic.h 를 보드에서 직접 돌려 보는 시험. 시리얼 모니터(115200)에 PASS/FAIL 과 요약이 나온다.
#include "../sorter_logic.h"
using namespace sorter;

enum { CAN = 0, EMPTY = 1, PAPER = 2, PET = 3 };
static int fails = 0, total = 0;

static void mk(float* s, int top, float p, int second = -1, float q = 0) {
  float rest = (1.0f - p - q) / 2.0f;
  for (int i = 0; i < 4; i++) s[i] = rest;
  s[top] = p;
  if (second >= 0) s[second] = q;
}
static void check(const char* name, bool ok) {
  total++; if (!ok) fails++;
  Serial.printf("[%s] %s\n", ok ? "PASS" : "FAIL", name);
}
// 프레임을 n 번 넣고 DECISION/STUCK 횟수와 마지막 DECISION 클래스를 센다
struct Tally { int dec = 0, stuck = 0, last = -1, first_dec_at = -1; };
static uint32_t T = 0;
static void feed(Sorter& s, Tally& t, int top, float p, int n, int second = -1, float q = 0, uint32_t step = 200) {
  float sc[4]; mk(sc, top, p, second, q);
  for (int i = 0; i < n; i++) {
    T += step;
    Result r = s.update(sc, T);
    if (r.event == EV_DECISION) { t.dec++; t.last = r.cls; if (t.first_dec_at < 0) t.first_dec_at = i + 1; }
    if (r.event == EV_STUCK) t.stuck++;
  }
}

void setup() {
  Serial.begin(115200);
  delay(2000);
  Serial.println("--- sorter_logic 시험 시작 ---");

  { Sorter s; Tally t; feed(s, t, CAN, 0.9f, 2); feed(s, t, EMPTY, 0.95f, 1);
    check("T1 2번만 보이고 사라지면 판정 없음", t.dec == 0); }
  { Sorter s; Tally t; feed(s, t, CAN, 0.9f, 3);
    check("T2 같은 결과 3번 연속이면 3번째에 판정(can)", t.dec == 1 && t.last == CAN && t.first_dec_at == 3); }
  { Sorter s; Tally t; for (int i = 0; i < 6; i++) feed(s, t, i % 2 ? PET : CAN, 0.9f, 1);
    check("T3 결과가 계속 바뀌면 판정 없음", t.dec == 0); }
  { Sorter s; Tally t; feed(s, t, CAN, 0.6f, 6);
    check("T4 확신도가 낮으면 판정 없음", t.dec == 0); }
  { Sorter s; Tally t; feed(s, t, CAN, 0.50f, 6, PET, 0.46f);
    check("T5 1등·2등 격차가 작으면 판정 없음", t.dec == 0); }
  { Sorter s; Tally t; feed(s, t, CAN, 0.9f, 3); feed(s, t, CAN, 0.9f, 10);
    check("T6a 판정 뒤 같은 물건이 계속 보여도 두 번째 판정 없음", t.dec == 1);
    feed(s, t, EMPTY, 0.95f, 3); feed(s, t, PET, 0.9f, 3);
    check("T6b 트레이가 비면 다음 물건(pet)을 판정", t.dec == 2 && t.last == PET); }
  { Sorter s; Tally t; feed(s, t, CAN, 0.9f, 3); feed(s, t, CAN, 0.9f, 80);   // 80*200ms = 16초
    check("T7 물건이 안 떨어지면 STUCK 알림, 새 판정 없음", t.stuck >= 1 && t.dec == 1); }
  { Sorter s; Tally t; feed(s, t, CAN, 0.9f, 3);
    feed(s, t, EMPTY, 0.95f, 2); feed(s, t, CAN, 0.9f, 1); feed(s, t, EMPTY, 0.95f, 2); feed(s, t, PET, 0.9f, 3);
    check("T8 '비었음' 연속이 끊기면 다시 센다 (아직 대기 중이라 판정 없음)", t.dec == 1);
    feed(s, t, EMPTY, 0.95f, 3); feed(s, t, PET, 0.9f, 3);
    check("T8b 이후 3번 연속 비면 다시 판정 가능", t.dec == 2 && t.last == PET); }
  { Sorter s; Tally t; T = 0xFFFFFF00u; feed(s, t, CAN, 0.9f, 3, -1, 0, 50); feed(s, t, CAN, 0.9f, 300, -1, 0, 50);  // millis 오버플로 통과
    check("T9 시간값이 오버플로해도 STUCK 이 정상 동작", t.stuck >= 1); }

  Serial.printf("--- 결과: %d/%d 통과 ---\n", total - fails, total);
}
void loop() { delay(1000); }
