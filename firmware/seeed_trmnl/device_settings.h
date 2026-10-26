#pragma once
#include <Preferences.h>
#include <ArduinoJson.h>
#include "settings_schema.h"

static DeviceSettings settings;
struct SettingsRecord { uint32_t version; DeviceSettings values; };
constexpr uint32_t SETTINGS_VERSION = 1;

inline bool validateSettings(const DeviceSettings &v) {
    for (const auto &spec : SETTING_SPECS) {
        int32_t value = v.*(spec.member);
        if (value < spec.low || value > spec.high) return false;
    }
    if (v.timeline_start_hour >= v.timeline_end_hour) return false;
    if (v.periodic_interval_seconds > 0 && v.periodic_interval_seconds < 15) return false;
    if (v.nfc_enabled) {
        const int safe[] = {3, 5, 8, 11, 12, 13, 14, 15, 16, 17, 18, 21};
        bool found = false;
        for (int pin : safe) if (pin == v.nfc_gpio) found = true;
        if (!found || ((v.nfc_gpio == 3 || v.nfc_gpio == 5) && v.nfc_active_level)) return false;
    }
    return true;
}
inline bool decodeSettings(JsonVariantConst cfg, DeviceSettings &value) {
    value = settings;
    if (cfg.isNull()) return true; // Older secure calendar messages keep current options.
    if (!cfg.is<JsonObjectConst>() || cfg.size() != sizeof(SETTING_SPECS) / sizeof(SETTING_SPECS[0])) return false;
    for (const auto &spec : SETTING_SPECS) {
        if (!cfg[spec.key].is<int32_t>()) return false;
        value.*(spec.member) = cfg[spec.key].as<int32_t>();
    }
    return validateSettings(value);
}
inline void loadSettings() {
    Preferences store;
    if (!store.begin("eink-config", true)) return;
    SettingsRecord record = {};
    if (store.getBytesLength("options") == sizeof(record) &&
        store.getBytes("options", &record, sizeof(record)) == sizeof(record) &&
        record.version == SETTINGS_VERSION && validateSettings(record.values)) settings = record.values;
    store.end();
}
inline bool saveSettings(const DeviceSettings &value) {
    if (!validateSettings(value)) return false;
    if (!memcmp(&settings, &value, sizeof(value))) return true; // No repeated flash writes.
    Preferences store;
    if (!store.begin("eink-config", false)) return false;
    SettingsRecord record = {SETTINGS_VERSION, value};
    bool ok = store.putBytes("options", &record, sizeof(record)) == sizeof(record);
    store.end();
    if (ok) settings = value;
    return ok;
}
