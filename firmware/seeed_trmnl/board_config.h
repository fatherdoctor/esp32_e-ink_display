#pragma once
// Seeed TRMNL 7.5-inch (OG) DIY Kit / XIAO ESP32-S3 PLUS, not
// the older XIAO ESP32-C3 ePaper Panel or the retail TRMNL OG.
// See Seeed's Arduino and ESPHome cookbook links in this folder's README.
constexpr int EPD_SCK = 7;
constexpr int EPD_MOSI = 9;
constexpr int EPD_CS = 44;
constexpr int EPD_DC = 10;
constexpr int EPD_RST = 38;
constexpr int EPD_BUSY = 4;
constexpr int SYNC_BUTTON = 2; // KEY1 / D1, active low; S3 RTC-capable GPIO.
constexpr int BATTERY_ADC = 1;
constexpr int BATTERY_ENABLE = 6;
// Calibrate against a multimeter; ADC calibration + resistor tolerances vary.
constexpr float BATTERY_CALIBRATION = 1.0f;
constexpr uint32_t MANUAL_WINDOW_MS = 120000;
constexpr uint32_t MORNING_WINDOW_MS = 720000;
// 0 preserves boundary-only wakeups. Nonzero enables additional BLE windows;
// it costs battery and windows must overlap laptop scans to guarantee discovery.
constexpr uint32_t PERIODIC_SYNC_SECONDS = 0;
constexpr uint32_t PERIODIC_WINDOW_MS = 30000;
