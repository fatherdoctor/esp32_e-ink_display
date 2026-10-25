/* Seeed TRMNL 7.5-inch (OG) DIY Kit, XIAO ESP32-S3 PLUS.
 * Custom offline BLE calendar firmware. No TRMNL service or Wi-Fi is used.
 * Pin references and build instructions: README.md in this folder.
 */
#ifndef CONFIG_IDF_TARGET_ESP32S3
#error This variant requires the Seeed XIAO ESP32-S3 PLUS hardware.
#endif
#include <Arduino.h>
#include <SPI.h>
#include <GxEPD2_BW.h>
#include <ArduinoJson.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLESecurity.h>
#include <esp_sleep.h>
#include <esp_arduino_version.h>
#include <esp_system.h>
#include <esp_random.h>
#include <driver/rtc_io.h>
#include <mbedtls/md.h>
#include <mbedtls/gcm.h>
#include <sys/time.h>
#include <time.h>
#include "board_config.h"
#include "secrets.h"

static const char *SERVICE = "79dc1000-48c5-4b86-b403-184557b01e14";
static const char *WRITE = "79dc1001-48c5-4b86-b403-184557b01e14";
static const char *STATUS_UUID = "79dc1002-48c5-4b86-b403-184557b01e14";
static const uint32_t MAGIC = 0xCA1E0003;
static const size_t MAX_PACKET = 2048;

struct Event {
    uint32_t start, end;
    char subject[33], location[21];
    uint8_t status;
};
struct ZoneOffset { uint32_t at; int32_t seconds; };
struct Calendar {
    uint32_t magic, synced, day, end, morning, until, tomorrowEnd, tomorrowUntil;
    char id[9];
    uint8_t count, zoneCount;
    ZoneOffset zones[4];
    Event events[12];
};
RTC_DATA_ATTR Calendar calendar = {};
RTC_DATA_ATTR uint32_t nextSyncWake = 0;
RTC_DATA_ATTR uint32_t clockMagic = 0;
RTC_DATA_ATTR uint32_t nextPeriodicSync = 0;
static const uint32_t CLOCK_MAGIC = 0x53435254;
GxEPD2_BW<GxEPD2_750_T7, GxEPD2_750_T7::HEIGHT> display(
    GxEPD2_750_T7(EPD_CS, EPD_DC, EPD_RST, EPD_BUSY));
BLECharacteristic *statusCharacteristic;
SemaphoreHandle_t rxMutex;
uint8_t receiveBuffer[MAX_PACKET], commitBuffer[MAX_PACKET], plaintextBuffer[MAX_PACKET];
size_t received = 0, expected = 0;
uint32_t receiveStarted = 0;
bool committed = false;
bool haveChallenge = false;
uint8_t authNonce[32];
static const char AUTH_DOMAIN[] = "calendar-display-auth-v2";
static const char KEY_DOMAIN[] = "calendar-display-encryption-v2";
static const char PAYLOAD_DOMAIN[] = "calendar-display-payload-v2";
volatile bool connected = false;

uint32_t clockNow() {
    // ESP-IDF system time advances using the S3 RTC slow clock during deep sleep.
    return clockMagic == CLOCK_MAGIC ? uint32_t(time(nullptr)) : 0;
}
bool validClock(uint32_t value) { return value >= 1704067200UL && value < 4102444800UL; }
bool retained() { return calendar.magic == MAGIC; }
bool currentDay(uint32_t now) {
    return retained() && validClock(now) && now >= calendar.day && now < calendar.tomorrowEnd;
}
uint32_t calendarDayEnd(uint32_t now) { return now < calendar.end ? calendar.end : calendar.tomorrowEnd; }
uint32_t knowledgeUntil(uint32_t now) { return now < calendar.end ? calendar.until : calendar.tomorrowUntil; }
int32_t utcOffset(uint32_t value) {
    int32_t result = calendar.zoneCount ? calendar.zones[0].seconds : 0;
    for (int i = 0; i < calendar.zoneCount; ++i)
        if (calendar.zones[i].at <= value) result = calendar.zones[i].seconds;
    return result;
}
String hhmm(uint32_t value) {
    time_t local = (time_t)value + utcOffset(value);
    struct tm t;
    gmtime_r(&local, &t);
    char buffer[12];
    snprintf(buffer, sizeof(buffer), "%d:%02d %s", t.tm_hour % 12 ? t.tm_hour % 12 : 12,
             t.tm_min, t.tm_hour < 12 ? "AM" : "PM");
    return String(buffer);
}

class ServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer *) override { connected = true; }
    void onDisconnect(BLEServer *server) override {
        connected = false;
        xSemaphoreTake(rxMutex, portMAX_DELAY);
        // A committed transaction belongs to the main loop even after disconnect.
        if (!committed) { received = expected = 0; haveChallenge = false; }
        xSemaphoreGive(rxMutex);
        server->startAdvertising();
    }
};

// Callbacks only assemble bounded frames. Parsing, RTC I/O and drawing run in setup().
class WriteCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *characteristic) override {
        auto value = characteristic->getValue(); // std::string on ESP32 2.x; String on 3.x
        const uint8_t *bytes = reinterpret_cast<const uint8_t *>(value.c_str());
        size_t n = value.length();
        if (!n) return;
        xSemaphoreTake(rxMutex, portMAX_DELAY);
        if (committed) { xSemaphoreGive(rxMutex); return; }
        if (bytes[0] == 'A' && n == 17) {
            received = expected = 0;
            memcpy(authNonce, bytes + 1, 16);
            esp_fill_random(authNonce + 16, 16);
            uint8_t input[sizeof(AUTH_DOMAIN) - 1 + 32], proof[49];
            memcpy(input, AUTH_DOMAIN, sizeof(AUTH_DOMAIN) - 1);
            memcpy(input + sizeof(AUTH_DOMAIN) - 1, authNonce, 32);
            proof[0] = 'P';
            memcpy(proof + 1, authNonce + 16, 16);
            haveChallenge = mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),
                SYNC_KEY, sizeof(SYNC_KEY), input, sizeof(input), proof + 17) == 0;
            if (haveChallenge) statusCharacteristic->setValue(proof, sizeof(proof));
            else statusCharacteristic->setValue("ERR:auth");
        } else if (bytes[0] == 'B' && n == 3 && haveChallenge) {
            received = 0;
            receiveStarted = millis();
            expected = bytes[1] | (size_t(bytes[2]) << 8);
            if (expected <= 28 || expected > MAX_PACKET) {
                expected = 0;
                statusCharacteristic->setValue("ERR:length");
            } else statusCharacteristic->setValue("RX");
        } else if (bytes[0] == 'D' && expected && n > 1 && received + n - 1 <= expected) {
            memcpy(receiveBuffer + received, bytes + 1, n - 1);
            received += n - 1;
        } else if (bytes[0] == 'C' && n == 1 && expected && received == expected) {
            committed = true;
            statusCharacteristic->setValue("CHECK");
        } else {
            received = expected = 0;
            statusCharacteristic->setValue("ERR:frame");
        }
        xSemaphoreGive(rxMutex);
    }
};

bool acceptPacket(const uint8_t *packet, size_t length, uint32_t transferSeconds,
                  const uint8_t *challenge) {
    if (length <= 28 || length > MAX_PACKET) return false;
    const size_t bodyLength = length - 28;
    uint8_t encryptionKey[32];
    uint8_t *plaintext = plaintextBuffer;
    uint8_t aad[sizeof(PAYLOAD_DOMAIN) - 1 + 32];
    memcpy(aad, PAYLOAD_DOMAIN, sizeof(PAYLOAD_DOMAIN) - 1);
    memcpy(aad + sizeof(PAYLOAD_DOMAIN) - 1, challenge, 32);
    if (mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),
        SYNC_KEY, sizeof(SYNC_KEY), reinterpret_cast<const uint8_t *>(KEY_DOMAIN),
        sizeof(KEY_DOMAIN) - 1, encryptionKey)) return false;
    mbedtls_gcm_context gcm;
    mbedtls_gcm_init(&gcm);
    int result = mbedtls_gcm_setkey(&gcm, MBEDTLS_CIPHER_ID_AES, encryptionKey, 256);
    if (!result) result = mbedtls_gcm_auth_decrypt(&gcm, bodyLength, packet, 12,
        aad, sizeof(aad), packet + length - 16, 16, packet + 12, plaintext);
    mbedtls_gcm_free(&gcm);
    if (result) return false;
    // Const input forces owned strings. ArduinoJson 6.21.x is the tested API target.
    DynamicJsonDocument doc(8192);
    if (deserializeJson(doc, reinterpret_cast<const char *>(plaintext), bodyLength)) return false;
    int schema = doc["v"] | 0;
    if ((schema != 2 && schema != 3) || !doc["id"].is<const char *>()) return false;
    if (schema == 3 && strcmp(doc["kind"] | "", "calendar")) return false;
    const char *id = doc["id"];
    if (strlen(id) != 8) return false;
    for (int i = 0; i < 8; ++i) if (!isxdigit(id[i])) return false;
    const char *fields[] = {"now", "day", "end", "morning", "until"};
    for (auto field : fields)
        if (!doc[field].is<uint32_t>() || !validClock(doc[field].as<uint32_t>())) return false;
    Calendar next = {};
    next.synced = doc["now"]; next.day = doc["day"]; next.end = doc["end"];
    next.morning = doc["morning"]; next.until = doc["until"];
    if (next.day > next.synced || next.synced >= next.end ||
        next.end - next.day < 22 * 3600 || next.end - next.day > 26 * 3600 ||
        next.until < next.synced || next.until > next.end ||
        next.morning <= next.end || next.morning - next.end > 9 * 3600) return false;
    next.tomorrowEnd = next.end; next.tomorrowUntil = next.end;
    if (schema == 3) {
        if (!doc["tomorrow_end"].is<uint32_t>() || !doc["tomorrow_until"].is<uint32_t>()) return false;
        next.tomorrowEnd = doc["tomorrow_end"]; next.tomorrowUntil = doc["tomorrow_until"];
        if (!validClock(next.tomorrowEnd) || next.tomorrowEnd <= next.end ||
            next.tomorrowEnd - next.end < 22 * 3600 || next.tomorrowEnd - next.end > 26 * 3600 ||
            next.tomorrowUntil < next.end || next.tomorrowUntil > next.tomorrowEnd) return false;
    }
    // Reject replayed/older schedules while RTC retention is intact.
    if (retained() && (next.synced < calendar.synced || !strcmp(id, calendar.id))) return false;
    if (!doc["events"].is<JsonArray>() || !doc["tz"].is<JsonArray>()) return false;
    JsonArray events = doc["events"];
    JsonArray zones = doc["tz"];
    if (events.size() > (schema == 3 ? 12 : 6) || zones.size() < 1 || zones.size() > 4) return false;
    for (JsonVariant value : zones) {
        if (!value.is<JsonArray>()) return false;
        JsonArray row = value.as<JsonArray>();
        if (row.size() != 2 || !row[0].is<uint32_t>() || !row[1].is<int32_t>()) return false;
        uint32_t at = row[0]; int32_t offset = row[1];
        if (offset < -50400 || offset > 50400 || at > max(next.morning, next.tomorrowEnd) ||
            (next.zoneCount && at <= next.zones[next.zoneCount - 1].at)) return false;
        next.zones[next.zoneCount++] = {at, offset};
    }
    if (next.zones[0].at > next.day) return false;
    for (JsonVariant value : events) {
        if (!value.is<JsonArray>()) return false;
        JsonArray row = value.as<JsonArray>();
        if (row.size() != 5 || !row[0].is<uint32_t>() || !row[1].is<uint32_t>() ||
            !row[2].is<const char *>() || !row[3].is<const char *>() || !row[4].is<int>()) return false;
        Event e = {};
        e.start = row[0]; e.end = row[1];
        int status = row[4];
        if (status != 2 && status != 3) return false;
        e.status = status;
        if (e.start >= e.end || e.end <= next.synced || e.start >= next.tomorrowEnd || next.zones[0].at > e.start ||
            (e.status != 2 && e.status != 3) || strlen(row[2]) > 32 || strlen(row[3]) > 20 ||
            (next.count && e.start < next.events[next.count - 1].start)) return false;
        strlcpy(e.subject, row[2], sizeof(e.subject));
        strlcpy(e.location, row[3], sizeof(e.location));
        next.events[next.count++] = e;
    }
    strlcpy(next.id, id, sizeof(next.id));
    // Clock correction only follows a complete authenticated, validated transaction.
    uint32_t target = next.synced + transferSeconds;
    if (target >= next.tomorrowEnd || transferSeconds > 60) return false;
    struct timeval timestamp = {time_t(target), 0};
    if (settimeofday(&timestamp, nullptr) != 0) return false;
    uint32_t verified = uint32_t(time(nullptr));
    if (verified < target || verified - target > 2) return false;
    clockMagic = CLOCK_MAGIC;
    next.magic = MAGIC;
    calendar = next;
    nextSyncWake = next.morning;
    nextPeriodicSync = PERIODIC_SYNC_SECONDS ? verified + PERIODIC_SYNC_SECONDS : 0;
    return true;
}


// GxEPD2 retains a full 48 kB monochrome framebuffer. Full refreshes are used
// deliberately: reliable cold controller startup after deep sleep comes first.
void line(int x, int y, int size, const String &text, uint16_t color = GxEPD_BLACK) {
    display.setFont(nullptr);
    display.setCursor(x, y);
    display.setTextSize(size);
    display.setTextColor(color);
    display.print(text);
}
void refreshPanel() {
    display.display(false);
    display.hibernate(); // Switch off panel high voltage before radio/sleep.
}
float batteryVoltage() {
    digitalWrite(BATTERY_ENABLE, HIGH);
    delay(10);
    uint32_t total = 0;
    for (int i = 0; i < 16; ++i) total += analogReadMilliVolts(BATTERY_ADC);
    digitalWrite(BATTERY_ENABLE, LOW);
    return (total / 16.0f) * 0.002f * BATTERY_CALIBRATION;
}
class SecurityCallbacks : public BLESecurityCallbacks {
    uint32_t onPassKeyRequest() override { return PAIR_PIN; }
    void onPassKeyNotify(uint32_t) override {} // Static PIN is already on screen.
    bool onSecurityRequest() override { return true; }
    bool onConfirmPIN(uint32_t) override { return false; } // No numeric-comparison UI.
    void onAuthenticationComplete(esp_ble_auth_cmpl_t) override {}
};
bool syncWindow(uint32_t duration, bool showPrompt) {
    if (showPrompt) {
        display.fillScreen(GxEPD_WHITE);
        line(24, 34, 5, "READY TO SYNC");
        line(24, 120, 2, "Run the calendar client on your laptop.");
        line(24, 170, 3, "First pairing PIN: " + String(PAIR_PIN));
        line(24, 235, 2, "KEY1 / D1 opens a two-minute sync window.");
        line(24, 285, 2, "Previous calendar kept until a new one is accepted.");
        line(24, 425, 1, "Local Bluetooth only. No Wi-Fi or cloud connection.");
        refreshPanel();
    }
    BLEDevice::init("TRMNL Calendar");
    BLEDevice::setSecurityCallbacks(new SecurityCallbacks());
    BLESecurity security;
    // Arduino ESP32 changed its BLE security API in 3.3.
#if ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 3, 0)
    security.setPassKey(true, PAIR_PIN);
    security.setEncryptionLevel(ESP_BLE_SEC_ENCRYPT_MITM);
#else
    security.setStaticPIN(PAIR_PIN);
    BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT_MITM);
#endif
    security.setAuthenticationMode(ESP_LE_AUTH_REQ_SC_MITM_BOND);
    security.setCapability(ESP_IO_CAP_OUT);
    security.setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
    BLEServer *server = BLEDevice::createServer();
    server->setCallbacks(new ServerCallbacks());
    BLEService *service = server->createService(SERVICE);
    statusCharacteristic = service->createCharacteristic(STATUS_UUID, BLECharacteristic::PROPERTY_READ);
    statusCharacteristic->setAccessPermissions(ESP_GATT_PERM_READ_ENC_MITM);
    statusCharacteristic->setValue("READY");
    BLECharacteristic *writer = service->createCharacteristic(WRITE, BLECharacteristic::PROPERTY_WRITE);
    writer->setAccessPermissions(ESP_GATT_PERM_WRITE_ENC_MITM);
    writer->setCallbacks(new WriteCallbacks());
    service->start();
    BLEAdvertising *advertising = BLEDevice::getAdvertising();
    advertising->addServiceUUID(SERVICE);
    advertising->setScanResponse(true);
    advertising->start();
    uint32_t opened = millis(), acceptedAt = 0;
    bool accepted = false;
    while (millis() - opened < duration || (accepted && millis() - acceptedAt < 15000)) {
        if (!accepted) {
            uint8_t *packet = commitBuffer; uint8_t challenge[32]; size_t length = 0; uint32_t transferSeconds = 0;
            xSemaphoreTake(rxMutex, portMAX_DELAY);
            if (committed) {
                length = received; memcpy(packet, receiveBuffer, length);
                memcpy(challenge, authNonce, sizeof(challenge));
                transferSeconds = (millis() - receiveStarted) / 1000;
            }
            xSemaphoreGive(rxMutex);
            if (length) {
                accepted = acceptPacket(packet, length, transferSeconds, challenge);
                statusCharacteristic->setValue(accepted ? ("OK:" + String(calendar.id)).c_str() : "ERR:payload");
                xSemaphoreTake(rxMutex, portMAX_DELAY);
                committed = false; received = expected = 0; haveChallenge = false;
                xSemaphoreGive(rxMutex);
                if (accepted) acceptedAt = millis();
            }
        }
        // Keep OK readable until the client disconnects, with a bounded fallback.
        if (accepted && ((!connected && millis() - acceptedAt > 500) || millis() - acceptedAt > 15000)) break;
        delay(25);
    }
    BLEDevice::deinit(true);
    connected = false;
    return accepted;
}
uint32_t nextTransition(uint32_t now) {
    uint32_t next = (nextSyncWake > now) ? nextSyncWake : now + 86400;
    if (currentDay(now)) {
        if (calendar.end > now) next = min(next, calendar.end); // Roll the page at midnight.
        next = min(next, calendar.tomorrowEnd);
        if (knowledgeUntil(now) > now) next = min(next, knowledgeUntil(now));
        for (int i = 0; i < calendar.count; ++i) {
            if (calendar.events[i].start > now) next = min(next, calendar.events[i].start);
            if (calendar.events[i].end > now) next = min(next, calendar.events[i].end);
        }
    }
    if (PERIODIC_SYNC_SECONDS && nextPeriodicSync > now) next = min(next, nextPeriodicSync);
    return next;
}

// Page models/renderers are independent of this hardware's refresh/power layer.
#include "ui/page_models.h"
#include "ui/page_renderers.h"
#include "ui/calendar_presenter.h"

void render(uint32_t now) {
    epaper_ui::CalendarPage page = epaper_ui::presentCalendar(now, batteryVoltage());
    epaper_ui::drawCalendarPage(display, page);
    refreshPanel();
}
// Ready for a future HA data adapter. No HA controls or telemetry are connected.
void renderDashboard(const epaper_ui::DashboardPage &page) {
    epaper_ui::drawDashboardPage(display, page);
    refreshPanel();
}

void setup() {
    // Never use UART0: GPIO44 belongs to this board's display CS.
    // USB CDC is enabled by platformio.ini; do not wait for a serial terminal.
    setenv("TZ", "UTC0", 1); tzset();
    const auto cause = esp_sleep_get_wakeup_cause();
    bool deepWake = cause == ESP_SLEEP_WAKEUP_TIMER || cause == ESP_SLEEP_WAKEUP_EXT0;
    if (!deepWake) { // No independent RTC: a reset/power cycle requires a new sync.
        calendar = {}; clockMagic = 0; nextSyncWake = 0; nextPeriodicSync = 0;
    }
    rtc_gpio_deinit(gpio_num_t(SYNC_BUTTON));
    pinMode(SYNC_BUTTON, INPUT_PULLUP);
    gpio_deep_sleep_hold_dis();
    gpio_hold_dis(gpio_num_t(BATTERY_ENABLE));
    pinMode(BATTERY_ENABLE, OUTPUT);
    digitalWrite(BATTERY_ENABLE, LOW);
    analogReadResolution(12);
    analogSetPinAttenuation(BATTERY_ADC, ADC_11db);
    SPI.begin(EPD_SCK, -1, EPD_MOSI, EPD_CS);
    // Full framebuffer is redrawn after each deep sleep; no retained controller RAM assumptions.
    display.init(0, true, 2, false);
    display.setRotation(0);
    display.setTextWrap(false);
    rxMutex = xSemaphoreCreateMutex();
    if (!rxMutex) esp_restart();
    uint32_t now = clockNow();
    bool morning = retained() && validClock(now) && nextSyncWake && now >= nextSyncWake;
    bool periodic = PERIODIC_SYNC_SECONDS && validClock(now) && nextPeriodicSync && now >= nextPeriodicSync;
    bool manual = cause == ESP_SLEEP_WAKEUP_EXT0 || !deepWake;
    if (manual || !retained() || !validClock(now) || morning || periodic) {
        if (morning) nextSyncWake = now + 86400;
        if (periodic) nextPeriodicSync = now + PERIODIC_SYNC_SECONDS;
        syncWindow(morning ? MORNING_WINDOW_MS : periodic && !manual ? PERIODIC_WINDOW_MS : MANUAL_WINDOW_MS,
                   manual || morning || !retained());
    }
    // Rendering may span a meeting boundary. Bound redraw retries, then schedule
    // a short retry if another boundary was crossed rather than sleeping on stale ink.
    bool crossed = false;
    uint32_t renderedUntil = 0;
    for (int attempt = 0; attempt < 3; ++attempt) {
        now = clockNow();
        uint32_t boundary = nextTransition(now);
        renderedUntil = boundary;
        render(now);
        crossed = validClock(now) && clockNow() >= boundary;
        if (!crossed) break;
    }
    display.hibernate();
    SPI.end();
    digitalWrite(BATTERY_ENABLE, LOW);
    gpio_hold_en(gpio_num_t(BATTERY_ENABLE));
    gpio_deep_sleep_hold_en();
    // ext0 supports KEY1/GPIO2 on S3; retain its RTC-domain pullup during sleep.
    uint32_t waited = millis();
    while (digitalRead(SYNC_BUTTON) == LOW && millis() - waited < 2000) delay(20);
    if (digitalRead(SYNC_BUTTON) != LOW) {
        rtc_gpio_pullup_en(gpio_num_t(SYNC_BUTTON));
        rtc_gpio_pulldown_dis(gpio_num_t(SYNC_BUTTON));
        esp_sleep_enable_ext0_wakeup(gpio_num_t(SYNC_BUTTON), 0);
    }
    // Subtract time spent releasing the button; calculate timer immediately before sleep.
    struct timeval clock;
    gettimeofday(&clock, nullptr);
    now = clockMagic == CLOCK_MAGIC ? uint32_t(clock.tv_sec) : 0;
    uint32_t next = nextTransition(now);
    uint64_t delayUs = validClock(now) && next > now ?
        uint64_t(next - now) * 1000000ULL - uint64_t(clock.tv_usec) : 3600000000ULL;
    if (crossed || (validClock(now) && now >= renderedUntil)) delayUs = 1000000ULL;
    esp_sleep_enable_timer_wakeup(delayUs);
    esp_deep_sleep_start();
}
void loop() {}
