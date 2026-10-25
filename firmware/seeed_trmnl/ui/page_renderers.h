#pragma once
#include "page_models.h"
#include <Fonts/FreeSans9pt7b.h>
#include <Fonts/FreeSansBold9pt7b.h>
#include <Fonts/FreeSansBold12pt7b.h>
#include <Fonts/FreeSansBold24pt7b.h>

// Render against an Adafruit-GFX-compatible canvas. Panel refresh, sleep and
// transport belong to the caller; adding a new page does not change the driver.
namespace epaper_ui {
constexpr uint16_t Black = 0, White = 0xFFFF;
template<class Canvas>
void text(Canvas &c, int x, int top, String value, const GFXfont *font,
          uint16_t ink = Black, int maxWidth = 0, int scale = 1) {
    c.setFont(font); c.setTextSize(scale); c.setTextColor(ink); c.setTextWrap(false);
    int16_t bx, by; uint16_t w, h;
    c.getTextBounds(value, 0, 0, &bx, &by, &w, &h);
    bool shortened = false;
    while (maxWidth && w > maxWidth && value.length()) {
        value.remove(value.length() - 1); shortened = true;
        c.getTextBounds(value + "~", 0, 0, &bx, &by, &w, &h);
    }
    if (shortened) {
        if (maxWidth < 16) return;
        value += "~";
    }
    c.getTextBounds(value, 0, 0, &bx, &by, &w, &h);
    c.setCursor(x - bx, top - by); c.print(value);
}
template<class Canvas>
void small(Canvas &c, int x, int top, const String &value, uint16_t ink = Black) {
    text(c, x, top, value, nullptr, ink);
}
template<class Canvas>
void drawCalendarPage(Canvas &c, const CalendarPage &m) {
    c.fillScreen(White);
    c.fillRect(0, 0, 300, 92, Black);
    text(c, 16, 12, m.day, &FreeSansBold24pt7b, White, 120, 2);
    text(c, 143, 18, m.weekday, &FreeSansBold12pt7b, White, 148);
    text(c, 143, 56, m.monthYear, &FreeSans9pt7b, White, 148);
    c.drawFastVLine(300, 0, 448, Black);
    small(c, 22, 115, "CURRENT AVAILABILITY");
    String first, second;
    switch (m.status) {
        case Availability::Available: first = "AVAILABLE"; break;
        case Availability::Meeting: first = "IN A"; second = "MEETING"; break;
        case Availability::OutOfOffice: first = "OUT OF"; second = "OFFICE"; break;
        case Availability::Done: first = "DONE FOR"; second = "TODAY"; break;
        default: first = "SYNC"; second = "NEEDED"; break;
    }
    text(c, 21, 146, first, &FreeSansBold24pt7b, Black, 268);
    if (second.length()) text(c, 21, 190, second, &FreeSansBold24pt7b, Black, 268);
    text(c, 22, 241, m.location, &FreeSans9pt7b, Black, 264);
    text(c, 22, 272, m.subject, &FreeSans9pt7b, Black, 264);
    c.drawFastHLine(20, 300, 260, Black);
    small(c, 22, 316, "NEXT AVAILABLE");
    text(c, 21, 339, m.nextAvailable, &FreeSansBold24pt7b, Black, 268);
    text(c, 22, 386, m.availabilityDetail, &FreeSans9pt7b, Black, 265);
    c.drawFastHLine(20, 414, 260, Black);
    small(c, 22, 430, "NEXT UP");
    // Built-in font gives a guaranteed 31-character line at this width.
    small(c, 84, 430, m.nextUp.substring(0, 34));
    c.drawFastVLine(554, 0, 448, Black);
    constexpr int top = 80, bottom = 430, firstMinute = 480, lastMinute = 1080;
    for (int hour = 8; hour <= 18; ++hour) {
        int y = top + (hour - 8) * 35;
        small(c, 311, y - 3, String(hour > 12 ? hour - 12 : hour));
        c.drawFastHLine(337, y, 449, Black);
    }
    for (int col = 0; col < 2; ++col) {
        const DayColumn &d = m.columns[col];
        int left = 342 + col * 222;
        small(c, left + 6, 18, d.label);
        text(c, left + 6, 37, d.date, &FreeSansBold9pt7b, Black, 202);
        if (d.allDay.length()) small(c, left + 6, 61, d.allDay.substring(0, 31));
        // Hatch unknown time, so blank space cannot imply a known free schedule.
        int knownMinute = d.covered ? d.coverageMinute : firstMinute;
        int unknownY = constrain(top + (knownMinute - firstMinute) * 350 / 600, top, bottom);
        for (int y = unknownY; y < bottom; y += 8)
            for (int x = left; x < left + 206; x += 8) c.drawPixel(x, y, Black);
        if (!d.covered) {
            c.fillRect(left + 12, 222, 180, 24, White);
            text(c, left + 22, 226, "Sync needed", &FreeSans9pt7b);
            continue;
        }
        // Partition each connected overlap group into lanes. Never paint one
        // event over another, including chains of partially overlapping events.
        int i = 0, outside = 0;
        while (i < d.count) {
            int groupEnd = d.events[i].endMinute, end = i + 1;
            while (end < d.count && d.events[end].startMinute < groupEnd) {
                groupEnd = max(groupEnd, d.events[end].endMinute); ++end;
            }
            int laneEnds[12] = {}, lanes[12] = {}, laneCount = 0;
            for (int j = i; j < end; ++j) {
                int lane = 0;
                while (lane < laneCount && laneEnds[lane] > d.events[j].startMinute) ++lane;
                if (lane == laneCount) ++laneCount;
                lanes[j - i] = lane; laneEnds[lane] = d.events[j].endMinute;
            }
            for (int j = i; j < end; ++j) {
                const TimelineEvent &e = d.events[j];
                if (e.startMinute < firstMinute || e.endMinute > lastMinute) ++outside;
                int a = max(firstMinute, e.startMinute), b = min(lastMinute, e.endMinute);
                if (a >= b) continue;
                int width = 206 / laneCount, x = left + lanes[j - i] * width;
                int y = top + (a - firstMinute) * 350 / 600;
                int h = max(3, (b - a) * 350 / 600 - 1);
                uint16_t ink = e.active ? White : Black;
                c.fillRect(x, y, width - 2, h, e.active ? Black : White);
                c.drawRect(x, y, width - 2, h, Black);
                if (h >= 20) text(c, x + 5, y + 3, e.title, &FreeSansBold9pt7b, ink, width - 13);
                else if (h >= 11) small(c, x + 3, y + 2, e.title.substring(0, max(1, (width - 9) / 6)), ink);
                if (h >= 35) {
                    char time[20];
                    snprintf(time, sizeof(time), "%d:%02d - %d:%02d", e.startMinute / 60 % 12 ? e.startMinute / 60 % 12 : 12,
                        e.startMinute % 60, e.endMinute / 60 % 12 ? e.endMinute / 60 % 12 : 12, e.endMinute % 60);
                    small(c, x + 5, y + 24, String(time).substring(0, max(1, (width - 12) / 6)), ink);
                }
            }
            i = end;
        }
        if (outside) small(c, left + 3, 437, String(outside) + " outside 8 AM - 6 PM");
    }
    c.drawFastHLine(0, 448, 800, Black);
    small(c, 18, 460, m.footer.substring(0, 125));
    c.setFont(nullptr);
}
template<class Canvas>
void drawDashboardPage(Canvas &c, const DashboardPage &m) {
    c.fillScreen(White);
    text(c, 18, 14, m.title, &FreeSansBold12pt7b, Black, 300);
    small(c, 420, 21, m.date.substring(0, 58));
    c.drawFastHLine(0, 48, 800, Black);
    for (int i = 0; i < min(m.count, 6); ++i) {
        int x = 16 + (i % 3) * 260, y = 66 + (i / 3) * 190;
        c.drawRoundRect(x, y, 248, 173, 9, Black);
        small(c, x + 15, y + 16, m.cards[i].title.substring(0, 35));
        text(c, x + 15, y + 55, m.cards[i].value, &FreeSansBold24pt7b, Black, 218);
        text(c, x + 15, y + 130, m.cards[i].detail, &FreeSans9pt7b, Black, 218);
    }
    c.drawFastHLine(0, 448, 800, Black); small(c, 18, 460, m.footer.substring(0, 125));
    c.setFont(nullptr);
}
} // namespace epaper_ui
