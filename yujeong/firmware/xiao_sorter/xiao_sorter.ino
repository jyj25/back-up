// XIAO ESP32S3 Sense: 카메라로 찍어 보드 안에서 물체를 검출(FOMO)하고, 판정을 JSON 한 줄로 USB 로 내보낸다.
// 라즈봇(jeongmin/robot/server/board.py → sorter.py)이 이 줄을 읽는다. 형식은 IF-01:
//   {"class":"can","conf":0.93,"ms":173}   확정 판정 (종류 하나)
//   {"class":null,"conf":0.00,"ms":173}    판정 없음 (매 프레임)
//   {"error":"camera"}                     오류
// 추가 필드(n=물체 수, ev)는 라즈봇이 무시한다. "event" 필드는 쓰지 않는다 (있으면 라즈봇이 decision 만 받음).
//
// 준비: Arduino 라이브러리 폴더에 Edge Impulse 라이브러리(jyj25-project-1_inferencing, EI 에서 내려받은 것)가 있어야 한다.
// 보드: FQBN esp32:esp32:XIAO_ESP32S3:PSRAM=opi
// 모델 라이브러리를 EON 컴파일(tflite-eon) 판으로 쓰면 ESP-NN 가속이 모델 실행 중 힙을 깨뜨린다(free 에서 CORRUPT HEAP, 재부팅 반복).
// 그때는 빌드 옵션으로 가속을 꺼야 한다(느려짐): -DEI_CLASSIFIER_TFLITE_ENABLE_ESP_NN=0 (compiler.cpp.extra_flags / compiler.c.extra_flags).
// 일반 tflite 판 라이브러리면 기본 설정(가속 켜짐)으로 쓴다.
#include <jyj25-project-1_inferencing.h>
#include "esp_camera.h"
#include "detect_logic.h"

// Wi-Fi 영상(MJPEG): wifi_secrets.h 가 있으면 같은 Wi-Fi 에 붙어 :81/stream 으로 영상을 보낸다 (판정은 그대로 USB 로).
// wifi_secrets.h: static const char* STA_LIST[][2] = {{"이름1","비번1"}, {"이름2","비번2"}};  앞쪽이 우선 (git 에 안 올라감)
#if __has_include("wifi_secrets.h")
#include <WiFi.h>
#include "esp_http_server.h"
#include "img_converters.h"
#include "wifi_secrets.h"
#define USE_STREAM 1
#endif
static SemaphoreHandle_t cam_mutex = nullptr;  // 판정(capture_features)과 영상(stream)이 카메라를 번갈아 쓰게

// XIAO ESP32S3 Sense 카메라 핀 (xiao_stream 과 같음)
#define PWDN_GPIO_NUM  -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM  10
#define SIOD_GPIO_NUM  40
#define SIOC_GPIO_NUM  39
#define Y9_GPIO_NUM    48
#define Y8_GPIO_NUM    11
#define Y7_GPIO_NUM    12
#define Y6_GPIO_NUM    14
#define Y5_GPIO_NUM    16
#define Y4_GPIO_NUM    18
#define Y3_GPIO_NUM    17
#define Y2_GPIO_NUM    15
#define VSYNC_GPIO_NUM 38
#define HREF_GPIO_NUM  47
#define PCLK_GPIO_NUM  13

#define IN_W EI_CLASSIFIER_INPUT_WIDTH
#define IN_H EI_CLASSIFIER_INPUT_HEIGHT
#define DET_MIN 0.60f  // EI 평가와 같은 검출 하한 (판정 하한은 detect::Config::conf_min)
#define ROTATE 0       // 0/90/180/270. 수집 때와 카메라 방향이 다르면 맞춘다 (수집기 회전 설정과 같게)

static float* features = nullptr;  // 96x96, 값 = (r<<16)|(g<<8)|b
static detect::Detector detector;
static bool cam_ok = false;
static uint32_t frame_no = 0;

static int get_data(size_t offset, size_t length, float* out) {
  memcpy(out, features + offset, length * sizeof(float));
  return 0;
}

static bool camera_init() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0; c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM; c.pin_d1 = Y3_GPIO_NUM; c.pin_d2 = Y4_GPIO_NUM; c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM; c.pin_d5 = Y7_GPIO_NUM; c.pin_d6 = Y8_GPIO_NUM; c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM; c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM; c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_RGB565;
  c.frame_size = FRAMESIZE_QVGA;  // 320x240. 수집(VGA 640x480)과 화각이 같다
  c.fb_count = 1;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;
  return esp_camera_init(&c) == ESP_OK;
}

// RGB565 프레임 → 중앙 정사각형 → IN_W x IN_H (상자 평균으로 줄임) → features
static bool capture_features() {
  xSemaphoreTake(cam_mutex, portMAX_DELAY);
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) { xSemaphoreGive(cam_mutex); return false; }
  int W = fb->width, H = fb->height, side = W < H ? W : H;
  int ox = (W - side) / 2, oy = (H - side) / 2;
  const uint16_t* px = (const uint16_t*)fb->buf;
  for (int y = 0; y < IN_H; y++) {
    int y0 = oy + y * side / IN_H, y1 = oy + (y + 1) * side / IN_H;
    if (y1 <= y0) y1 = y0 + 1;
    for (int x = 0; x < IN_W; x++) {
      int x0 = ox + x * side / IN_W, x1 = ox + (x + 1) * side / IN_W;
      if (x1 <= x0) x1 = x0 + 1;
      uint32_t r = 0, g = 0, b = 0, n = 0;
      for (int yy = y0; yy < y1; yy++)
        for (int xx = x0; xx < x1; xx++) {
          uint16_t v = px[yy * W + xx];
          v = (v >> 8) | (v << 8);  // 카메라가 보내는 바이트 순서 → 정상 RGB565
          r += ((v >> 11) & 0x1F) << 3; g += ((v >> 5) & 0x3F) << 2; b += (v & 0x1F) << 3; n++;
        }
      int dx = x, dy = y;
#if ROTATE == 90
      dx = IN_H - 1 - y; dy = x;
#elif ROTATE == 180
      dx = IN_W - 1 - x; dy = IN_H - 1 - y;
#elif ROTATE == 270
      dx = y; dy = IN_W - 1 - x;
#endif
      features[dy * IN_W + dx] = (float)(((r / n) << 16) | ((g / n) << 8) | (b / n));
    }
  }
  esp_camera_fb_return(fb);
  xSemaphoreGive(cam_mutex);
  return true;
}

#ifdef USE_STREAM
// RGB565 프레임 하나를 JPEG 로 줄여 보낸다. 판정이 카메라를 쓰는 동안은 기다린다.
static bool grab_jpeg(uint8_t** jpg, size_t* len) {
  xSemaphoreTake(cam_mutex, portMAX_DELAY);
  camera_fb_t* fb = esp_camera_fb_get();
  bool ok = fb && frame2jpg(fb, 60, jpg, len);
  if (fb) esp_camera_fb_return(fb);
  xSemaphoreGive(cam_mutex);
  return ok;
}

static bool wifi_ok = false;  // 한 번이라도 Wi-Fi 에 붙었나 (붙었다가 오래 끊기면 다시 찾으려고 재부팅한다)

static esp_err_t stream_handler(httpd_req_t* req) {
  httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=frame");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  char part[96];
  int fails = 0;
  while (true) {
    uint8_t* jpg = nullptr;
    size_t jl = 0;
    if (!grab_jpeg(&jpg, &jl)) {
      if (++fails > 20) return ESP_FAIL;
      delay(100);
      continue;
    }
    fails = 0;
    size_t n = snprintf(part, sizeof(part), "\r\n--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", (unsigned)jl);
    esp_err_t res = httpd_resp_send_chunk(req, part, n);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char*)jpg, jl);
    free(jpg);
    if (res != ESP_OK) return res;  // 보는 쪽이 끊으면 끝
    delay(150);                     // 약 6fps 로 제한해 판정(모델 실행)에 CPU 를 남긴다
  }
}

static esp_err_t capture_handler(httpd_req_t* req) {
  uint8_t* jpg = nullptr;
  size_t jl = 0;
  if (!grab_jpeg(&jpg, &jl)) { httpd_resp_send_500(req); return ESP_FAIL; }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  esp_err_t res = httpd_resp_send(req, (const char*)jpg, jl);
  free(jpg);
  return res;
}

// STA_LIST 앞쪽부터 8초씩 시도해 붙으면 영상 서버를 켠다. 못 붙으면 영상 없이 판정만 한다.
static void start_stream() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  String ip;
  for (size_t k = 0; k < sizeof(STA_LIST) / sizeof(STA_LIST[0]) && ip.length() == 0; k++) {
    WiFi.disconnect();
    WiFi.begin(STA_LIST[k][0], STA_LIST[k][1]);
    for (int i = 0; i < 16 && WiFi.status() != WL_CONNECTED; i++) delay(500);
    if (WiFi.status() == WL_CONNECTED) ip = WiFi.localIP().toString();
  }
  if (ip.length() == 0) { Serial.println("# Wi-Fi 접속 실패: 영상 없이 판정만"); return; }
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = 81;
  cfg.ctrl_port = 32769;
  httpd_uri_t stream = {"/stream", HTTP_GET, stream_handler, NULL};
  httpd_uri_t capture = {"/capture", HTTP_GET, capture_handler, NULL};
  httpd_handle_t h = NULL;
  if (httpd_start(&h, &cfg) == ESP_OK) {
    httpd_register_uri_handler(h, &stream);
    httpd_register_uri_handler(h, &capture);
  }
  Serial.printf("# 영상: http://%s:81/stream\n", ip.c_str());
  wifi_ok = true;
}
#endif

static void send_verdict(const char* label, float conf, uint32_t ms, int n) {
  if (label) Serial.printf("{\"class\":\"%s\",\"conf\":%.2f,\"ms\":%lu,\"n\":%d}\n", label, conf, (unsigned long)ms, n);
  else Serial.printf("{\"class\":null,\"conf\":%.2f,\"ms\":%lu,\"n\":%d}\n", conf, (unsigned long)ms, n);
}

void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(200);  // 읽는 쪽이 없어도 멈추지 않게
  delay(500);
  features = (float*)ps_malloc(IN_W * IN_H * sizeof(float));
  cam_mutex = xSemaphoreCreateMutex();
  cam_ok = features && camera_init();
  Serial.printf("# xiao_sorter 시작 (모델 %dx%d, 카메라 %s)\n", IN_W, IN_H, cam_ok ? "OK" : "실패");
#ifdef USE_STREAM
  if (cam_ok) start_stream();
#endif
}

void loop() {
#ifdef USE_STREAM
  // 붙어 있던 Wi-Fi 가 30초 넘게 끊기면(핫스팟을 껐거나 자리를 옮김) 재부팅해서 목록의 다른 Wi-Fi 로 다시 붙는다.
  // 한 번도 못 붙었으면(근처에 아는 Wi-Fi 없음) 재부팅하지 않고 판정(USB)만 계속한다.
  static uint32_t wifi_lost_at = 0;
  if (wifi_ok && WiFi.status() != WL_CONNECTED) {
    if (!wifi_lost_at) wifi_lost_at = millis();
    else if (millis() - wifi_lost_at > 30000) { Serial.println("# Wi-Fi 끊김 → 재부팅해서 다시 찾기"); delay(200); ESP.restart(); }
  } else {
    wifi_lost_at = 0;
  }
#endif
  if (!cam_ok) { Serial.println("{\"error\":\"camera\"}"); delay(1000); return; }
  uint32_t t0 = millis();
  if (!capture_features()) { Serial.println("{\"error\":\"camera\"}"); delay(200); return; }

  signal_t signal;
  signal.total_length = IN_W * IN_H;
  signal.get_data = &get_data;
  ei_impulse_result_t res = {0};
  EI_IMPULSE_ERROR rc = run_classifier(&signal, &res, false);
  if (rc != EI_IMPULSE_OK) {
    Serial.printf("{\"error\":\"model\",\"code\":%d,\"heap\":%u,\"psram\":%u}\n", (int)rc, (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getFreePsram());
    delay(200);
    return;
  }

  detect::Det dets[32];
  int n = 0;
  for (uint32_t i = 0; i < res.bounding_boxes_count && n < 32; i++) {
    auto bb = res.bounding_boxes[i];
    if (bb.value < DET_MIN) continue;
    int cls = 0;
    for (int k = 0; k < EI_CLASSIFIER_LABEL_COUNT; k++)
      if (strcmp(bb.label, ei_classifier_inferencing_categories[k]) == 0) { cls = k; break; }
    dets[n++] = {(int8_t)cls, bb.value, (int16_t)bb.x, (int16_t)bb.y, (int16_t)bb.width, (int16_t)bb.height};
  }

  uint32_t ms = millis() - t0;
  detect::Result r = detector.update(dets, n, millis());
  if (r.event == detect::EV_DECISION) {
    send_verdict(ei_classifier_inferencing_categories[r.cls], r.conf, ms, r.objects);
  } else {
    send_verdict(nullptr, 0.0f, ms, r.objects);
    if (r.event == detect::EV_STUCK) Serial.println("# STUCK: 물건이 안 치워짐");
  }
  frame_no++;
}
