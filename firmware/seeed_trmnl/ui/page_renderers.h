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
    text(c, 22, 16, m.weekday, &FreeSansBold12pt7b, Black, 260);
    text(c, 20, 48, m.day, &FreeSansBold24pt7b, Black, 115, 2);
    text(c, 133, 78, m.monthYear, &FreeSans9pt7b, Black, 155);
    String status;
    switch (m.status) {
        case Availability::Available: status = "Available"; break;
        case Availability::Meeting: status = "In a meeting"; break;
        case Availability::OutOfOffice: status = "Out of office"; break;
        case Availability::Done: status = "Available / done today"; break;
        default: status = "Sync needed"; break;
    }
    bool busy = m.status == Availability::Meeting || m.status == Availability::OutOfOffice;
    if (m.statusLabel.length()) status = m.statusLabel;
    c.fillRoundRect(20, 151, 265, 38, 18, busy ? Black : White);
    c.drawRoundRect(20, 151, 265, 38, 18, Black);
    text(c, 34, 162, status, &FreeSansBold9pt7b, busy ? White : Black, 236);
    text(c, 22, 214, m.location, &FreeSansBold12pt7b, Black, 264);
    text(c, 22, 251, m.subject, &FreeSans9pt7b, Black, 264);
    small(c, 23, 309, "Next available");
    text(c, 21, 331, m.nextAvailable, &FreeSansBold24pt7b, Black, 265);
    text(c, 22, 378, m.availabilityDetail, &FreeSans9pt7b, Black, 265);
    small(c, 22, 419, "Next up");
    small(c, 22, 436, m.nextUp.substring(0, 44));
    const int top = 99, bottom = 426, span = bottom - top;
    const int firstMinute = m.startHour * 60, lastMinute = m.endHour * 60;
    const int minutes = lastMinute - firstMinute;
    for (int col = 0; col < 2; ++col) {
        const DayColumn &d = m.columns[col];
        int left = 344 + col * 224;
        c.drawRoundRect(left - 6, 12, 218, 435, 12, Black);
        text(c, left + 7, 28, d.label, &FreeSansBold12pt7b, Black, 192);
        small(c, left + 8, 58, d.date);
        small(c, left + 8, 78, d.allDay.substring(0, 31));
        for (int hour = m.startHour; hour <= m.endHour; hour += 2) {
            int y = top + (hour * 60 - firstMinute) * span / minutes;
            for (int x = left + 1; x < left + 205; x += 5) c.drawPixel(x, y, Black);
            if (col == 0) small(c, 311, y - 3, String(m.clock24 ? hour : (hour % 12 ? hour % 12 : 12)));
        }
        int knownMinute = d.covered ? d.coverageMinute : firstMinute;
        int unknownY = constrain(top + (knownMinute - firstMinute) * span / minutes, top, bottom);
        for (int y = unknownY; y < bottom; y += 8)
            for (int x = left; x < left + 206; x += 8) c.drawPixel(x, y, Black);
        if (!d.covered) {
            c.fillRoundRect(left + 10, 230, 185, 28, 8, White);
            text(c, left + 23, 236, "Sync needed", &FreeSans9pt7b);
            continue;
        }
        int i = 0, outside = 0;
        while (i < d.count) {
            int groupEnd = d.events[i].endMinute, end = i + 1;
            while (end < d.count && d.events[end].startMinute < groupEnd) {
                groupEnd = max(groupEnd, d.events[end].endMinute); ++end;
            }
            int laneEnds[48] = {}, lanes[48] = {}, laneCount = 0;
            for (int j = i; j < end; ++j) {
                int lane = 0;
                while (lane < laneCount && laneEnds[lane] > d.events[j].startMinute) ++lane;
                if (lane == laneCount) ++laneCount;
                lanes[j-i] = lane; laneEnds[lane] = d.events[j].endMinute;
            }
            for (int j = i; j < end; ++j) {
                const TimelineEvent &e = d.events[j];
                if (e.startMinute < firstMinute || e.endMinute > lastMinute) ++outside;
                int a = max(firstMinute, e.startMinute), b = min(lastMinute, e.endMinute);
                if (a >= b) continue;
                int width = 206 / laneCount, x = left + lanes[j-i] * width;
                int y = top + (a-firstMinute) * span / minutes;
                int h = max(3, (b-a) * span / minutes - 2);
                uint16_t ink = e.active ? White : Black;
                int radius = min(6, min(h/2, (width-2)/2));
                c.fillRoundRect(x, y, width-2, h, radius, e.active ? Black : White);
                c.drawRoundRect(x, y, width-2, h, radius, Black);
                if (e.tentative) for (int yy=y+3; yy<y+h-2; yy+=4) c.drawFastVLine(x+2, yy, 2, ink);
                if (h >= 21) text(c, x+6, y+4, e.title, &FreeSansBold9pt7b, ink, width-15);
                else if (h >= 11) small(c, x+3, y+2, e.title.substring(0, max(1,(width-9)/6)), ink);
                if (h >= 32) small(c, x+6, y+22, e.detail.substring(0, max(1,(width-15)/6)), ink);
            }
            i = end;
        }
        if (outside) small(c, left+6, 434, String(outside) + " outside visible hours");
    }
    small(c, 22, 465, m.footer.substring(0, 125));
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
