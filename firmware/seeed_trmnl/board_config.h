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
// User options/timers live in config.local.json and settings_schema.h, not here.
