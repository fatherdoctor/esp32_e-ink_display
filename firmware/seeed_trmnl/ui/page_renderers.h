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
    while (maxWidth > 0 && w > maxWidth && value.length()) {
        value.remove(value.length() - 1); shortened = true;
        c.getTextBounds(value + "...", 0, 0, &bx, &by, &w, &h);
    }
    if (shortened) {
        if (maxWidth < 16) return;
        value += "...";
    }
    c.getTextBounds(value, 0, 0, &bx, &by, &w, &h);
    c.setCursor(x - bx, top - by); c.print(value);
}
template<class Canvas>
void small(Canvas &c, int x, int top, const String &value, uint16_t ink = Black) {
    text(c, x, top, value, nullptr, ink);
}

// Fit whole words into a bounded number of lines. Long final lines use an
// explicit ellipsis; no glyphs are drawn across the containing card's border.
template<class Canvas>
void wrapped(Canvas &c, int x, int top, String value, const GFXfont *font,
             int width, int lines, int lineHeight, uint16_t ink = Black) {
    value.trim();
    for (int row = 0; row < lines && value.length(); ++row) {
        if (row == lines - 1) { text(c, x, top + row*lineHeight, value, font, ink, width); break; }
        c.setFont(font); c.setTextSize(1);
        int16_t bx, by; uint16_t w, h;
        int fit = 0, space = -1;
        for (unsigned end = 1; end <= value.length(); ++end) {
            c.getTextBounds(value.substring(0, end), 0, 0, &bx, &by, &w, &h);
            if (w > width) break;
            fit = end;
            if (value[end-1] == ' ') space = end-1;
        }
        if (fit == int(value.length())) { text(c, x, top + row*lineHeight, value, font, ink, width); break; }
        int cut = space > 0 ? space : max(1, fit);
        text(c, x, top + row*lineHeight, value.substring(0, cut), font, ink, width);
        value = value.substring(cut); value.trim();
    }
}
template<class Canvas>
void drawCalendarPage(Canvas &c, const CalendarPage &m) {
    c.fillScreen(White);
    text(c, 20, 22, m.day, &FreeSansBold24pt7b, Black, 116, 2);
    text(c, 144, 22, m.weekday, &FreeSansBold12pt7b, Black, 154);
    text(c, 144, 60, m.monthYear, &FreeSans9pt7b, Black, 154);
    String status;
    switch (m.status) {
        case Availability::Available: case Availability::Done: status = "Available"; break;
        case Availability::Meeting: status = "In a meeting"; break;
        case Availability::OutOfOffice: status = "Out of office"; break;
        default: status = "Sync needed"; break;
    }
    bool busy = m.status == Availability::Meeting || m.status == Availability::OutOfOffice;
    if (m.statusLabel.length()) status = m.statusLabel;
    c.fillRoundRect(18, 120, 280, 120, 16, busy ? Black : White);
    c.drawRoundRect(18, 120, 280, 120, 16, Black);
    c.setFont(&FreeSansBold24pt7b); c.setTextSize(1);
    int16_t sx, sy; uint16_t sw, sh;
    c.getTextBounds(status, 0, 0, &sx, &sy, &sw, &sh);
    int statusTop = sw <= 248 ? 120 + (120-sh)/2 : 135;
    wrapped(c, 34, statusTop, status, &FreeSansBold24pt7b, 248, 2, 52, busy ? White : Black);
    wrapped(c, 22, 258, m.location, &FreeSansBold12pt7b, 274, 2, 28);
    wrapped(c, 22, 324, m.subject, &FreeSans9pt7b, 274, 2, 22);
    String nextCaption = "Next available";
    if (m.nextAvailable == "Tomorrow") nextCaption += " / " + m.availabilityDetail;
    text(c, 22, 383, nextCaption, &FreeSans9pt7b, Black, 277);
    text(c, 21, 411, m.nextAvailable, &FreeSansBold24pt7b, Black, 277);
    for (int col = 0; col < 2; ++col) {
        const DayColumn &d = m.columns[col];
        int left = 316 + col * 238;
        c.drawRoundRect(left, 12, 230, 438, 12, Black);
        text(c, left+13, 27, d.label, &FreeSansBold12pt7b, Black, 204);
        text(c, left+13, 62, d.date, &FreeSans9pt7b, Black, 204);
        wrapped(c, left+13, 89, d.allDay, nullptr, 204, 2, 12);
        if (!d.covered) {
            wrapped(c, left+13, 156, "Sync needed", &FreeSansBold12pt7b, 204, 2, 28);
            continue;
        }
        if (d.coverageMinute < 1440) small(c, left+13, 116, "Partial schedule: sync for more");
        int shown = 0, more = 0, outside = 0, earlier = 0;
        for (int i = 0; i < d.count; ++i) {
            const TimelineEvent &e = d.events[i];
            if (e.past) { ++earlier; continue; }
            if (e.endMinute <= m.startHour*60 || e.startMinute >= m.endHour*60) { ++outside; continue; }
            if (shown >= 3) { ++more; continue; }
            int x = left+8, y = 132 + shown++ * 102;
            uint16_t ink = e.active ? White : Black;
            c.fillRoundRect(x, y, 214, 94, 9, e.active ? Black : White);
            c.drawRoundRect(x, y, 214, 94, 9, Black);
            text(c, x+10, y+10, e.time, &FreeSans9pt7b, ink, 194);
            wrapped(c, x+10, y+34, e.title, &FreeSansBold9pt7b, 194, 2, 21, ink);
            text(c, x+10, y+78, e.detail, nullptr, ink, 194);
        }
        if (!shown) wrapped(c, left+13, 156, d.coverageMinute < 1440 ? "Later schedule unknown" :
                             outside ? "No meetings in these hours" : "No upcoming meetings",
                             &FreeSans9pt7b, 204, 3, 24);
        String summary;
        if (more) summary += "+" + String(more) + " more  ";
        if (outside) summary += String(outside) + " outside hours";
        if (!more && !outside && earlier) summary = String(earlier) + " earlier";
        text(c, left+13, 438, summary, nullptr, Black, 204);
    }
    text(c, 22, 465, m.footer, nullptr, Black, 756);
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
