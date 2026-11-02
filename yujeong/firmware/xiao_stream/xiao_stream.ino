// XIAO ESP32S3 Sense: 카메라 MJPEG 스트림 (사진 수집기용)
// 보드가 Wi-Fi AP 를 만들고, 노트북이 여기에 접속해서 http://192.168.4.1/ 을 열면 수집 대시보드가 뜬다.
//   :80 /          사진 수집 대시보드 (yujeong/ai/collector, gen_assets.py 로 내장)
//   :81 /stream   MJPEG 스트림
//   /capture  JPEG 한 장
#include "esp_camera.h"
#include "esp_http_server.h"
#include <WiFi.h>
#include "web_assets.h"

// 같은 Wi-Fi(공유기·핫스팟)에 붙이려면 wifi_secrets.h 를 만든다 (wifi_secrets.h.example 복사, 저장소에는 올라가지 않음).
// 파일이 없거나 20초 안에 못 붙으면 아래 AP 모드로 동작한다.
#if __has_include("wifi_secrets.h")
#include "wifi_secrets.h"   // static const char* STA_LIST[][2] = {{"이름1","비번1"}, {"이름2","비번2"}};  앞쪽이 우선
#define USE_STA 1
#endif

const char* AP_SSID = "XIAO_ESP32S3_Sense";
const char* AP_PASS = "seeedstudio";

// XIAO ESP32S3 Sense 카메라 핀
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

static esp_err_t stream_handler(httpd_req_t* req) {
  httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=frame");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");  // 수집기 캔버스 캡처에 필요
  char part[96];
  while (true) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) return ESP_FAIL;
    size_t n = snprintf(part, sizeof(part),
                        "\r\n--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", (unsigned)fb->len);
    esp_err_t res = httpd_resp_send_chunk(req, part, n);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char*)fb->buf, fb->len);
    esp_camera_fb_return(fb);
    if (res != ESP_OK) return res;  // 클라이언트가 끊으면 종료
  }
}

static esp_err_t capture_handler(httpd_req_t* req) {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) { httpd_resp_send_500(req); return ESP_FAIL; }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  esp_err_t res = httpd_resp_send(req, (const char*)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

static esp_err_t send_gz(httpd_req_t* req, const char* type, const uint8_t* d, unsigned len) {
  httpd_resp_set_type(req, type);
  httpd_resp_set_hdr(req, "Content-Encoding", "gzip");
  return httpd_resp_send(req, (const char*)d, len);
}
static esp_err_t index_handler(httpd_req_t* req) { return send_gz(req, "text/html; charset=utf-8", INDEX_HTML, INDEX_HTML_LEN); }
static esp_err_t jszip_handler(httpd_req_t* req) { return send_gz(req, "application/javascript", JSZIP_JS, JSZIP_JS_LEN); }

void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(1000);  // 호스트가 읽는 동안 프레임이 잘리지 않게
  delay(500);

  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM; c.pin_d1 = Y3_GPIO_NUM; c.pin_d2 = Y4_GPIO_NUM; c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM; c.pin_d5 = Y7_GPIO_NUM; c.pin_d6 = Y8_GPIO_NUM; c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM; c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM; c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = FRAMESIZE_VGA;  // 640x480
  c.jpeg_quality = 12;
  c.fb_count = 2;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("카메라 초기화 실패: 0x%x\n", err);
    return;
  }
  sensor_t* s = esp_camera_sensor_get();
  Serial.printf("카메라 센서 PID: 0x%x\n", s->id.PID);

  String ip;
#ifdef USE_STA
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // 스트림이 끊기지 않게
  // STA_LIST 앞쪽이 우선순위가 높다 (라즈베리파이의 저장 Wi-Fi 순서와 같게). 하나씩 8초씩 시도한다.
  for (size_t k = 0; k < sizeof(STA_LIST) / sizeof(STA_LIST[0]) && ip.length() == 0; k++) {
    WiFi.disconnect();
    WiFi.begin(STA_LIST[k][0], STA_LIST[k][1]);
    for (int i = 0; i < 16 && WiFi.status() != WL_CONNECTED; i++) delay(500);
    if (WiFi.status() == WL_CONNECTED) {
      ip = WiFi.localIP().toString();
      Serial.printf("Wi-Fi 접속: %s  IP %s\n", STA_LIST[k][0], ip.c_str());
    } else {
      Serial.printf("Wi-Fi(%s) 접속 실패\n", STA_LIST[k][0]);
    }
  }
#endif
  if (ip.length() == 0) {
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASS);
    ip = WiFi.softAPIP().toString();
    Serial.printf("AP: %s / %s\n", AP_SSID, AP_PASS);
  }

  // 스트림은 연결을 오래 점유하므로 페이지(80)와 별도 서버(81)로 분리
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

  httpd_config_t pcfg = HTTPD_DEFAULT_CONFIG();
  pcfg.max_uri_handlers = 4;
  httpd_uri_t idx = {"/", HTTP_GET, index_handler, NULL};
  httpd_uri_t jszip = {"/jszip.min.js", HTTP_GET, jszip_handler, NULL};
  httpd_handle_t ph = NULL;
  if (httpd_start(&ph, &pcfg) == ESP_OK) {
    httpd_register_uri_handler(ph, &idx);
    httpd_register_uri_handler(ph, &jszip);
  }
  Serial.printf("대시보드: http://%s/  스트림: http://%s:81/stream\n", ip.c_str(), ip.c_str());
}

// USB 시리얼 모드: 'C' 한 글자를 받으면 JPEG 한 장을 [AA 55 AA 55][길이 u32 LE][JPEG] 로 보낸다.
// 브라우저(Web Serial)에서 Wi-Fi 전환 없이 USB 만으로 수집할 때 쓴다.
void loop() {
  if (Serial.available()) {
    int ch = Serial.read();
    if (ch == 'C') {
      camera_fb_t* fb = esp_camera_fb_get();
      if (fb) {
        const uint8_t head[8] = {0xAA, 0x55, 0xAA, 0x55,
                                 (uint8_t)fb->len, (uint8_t)(fb->len >> 8), (uint8_t)(fb->len >> 16), (uint8_t)(fb->len >> 24)};
        Serial.write(head, 8);
        Serial.write(fb->buf, fb->len);
        esp_camera_fb_return(fb);
      }
    }
  } else {
    delay(2);
  }
}
