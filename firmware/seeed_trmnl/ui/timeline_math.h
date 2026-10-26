#pragma once
#include <stdint.h>

namespace epaper_ui {
constexpr int wallMinute(uint32_t epoch, int32_t offset) {
    return int((int64_t(epoch) + offset) % 86400 / 60);
}
constexpr bool needsClockChangeMarker(int startMinute, int endMinute) {
    return endMinute <= startMinute;
}
// Regression: Chicago's repeated hour, Nov 1 2026, 06:50Z -> 07:10Z.
// The event lasts 20 real minutes but its local labels run 01:50 -> 01:10.
static_assert(wallMinute(1793515800UL, -18000) == 110, "DST start label");
static_assert(wallMinute(1793517000UL, -21600) == 70, "DST end label");
static_assert(needsClockChangeMarker(wallMinute(1793515800UL, -18000),
                                    wallMinute(1793517000UL, -21600)),
              "Repeated-hour meetings must remain visible as clock-change entries");
} // namespace epaper_ui
