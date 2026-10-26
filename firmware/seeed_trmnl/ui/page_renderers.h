#pragma once
#include "page_models.h"
#include "timeline_layout.h"
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

template<class Canvas>
void stipple(Canvas &c, int x, int y, int width, int height, int level, int radius = 0) {
    static const uint8_t bayer[4][4] = {{0,8,2,10},{12,4,14,6},{3,11,1,9},{15,7,13,5}};
    for (int yy = 0; yy < height; ++yy) for (int xx = 0; xx < width; ++xx) {
        int dx = xx < radius ? radius-xx : xx >= width-radius ? xx-(width-radius-1) : 0;
        int dy = yy < radius ? radius-yy : yy >= height-radius ? yy-(height-radius-1) : 0;
        if (dx && dy && dx*dx+dy*dy > radius*radius) continue;
        c.drawPixel(x+xx,y+yy,bayer[(y+yy)&3][(x+xx)&3] < level ? Black : White);
    }
}

template<class Canvas>
void centered(Canvas &c, int left, int top, int width, const String &value,
              const GFXfont *font, uint16_t ink = Black) {
    c.setFont(font); c.setTextSize(1);
    int16_t bx, by; uint16_t w, h;
    c.getTextBounds(value,0,0,&bx,&by,&w,&h);
    text(c,left+(width-min(int(w),width))/2,top,value,font,ink,width);
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
    const DayColumn &d = m.today;
    stipple(c,316,12,468,52,2,10);
    c.drawRoundRect(316,12,468,52,10,Black);
    c.fillRoundRect(324,20,452,36,5,White);
    text(c,340,29,"Today",&FreeSansBold9pt7b,Black,130);
    text(c,584,30,d.date,&FreeSans9pt7b,Black,176);
    String notice = d.coverageMinute < 1440 ? "Partial schedule: sync for more" : d.allDay;
    text(c,365,78,notice,nullptr,Black,418);
    if (!d.covered) {
        wrapped(c,365,160,"Sync needed",&FreeSansBold12pt7b,400,2,28);
    } else {
        int first = m.startHour*60, last = m.endHour*60;
        int unknownY = constrain(timelineY(d.coverageMinute,first,last),TimelineTop,TimelineBottom);
        if (unknownY < TimelineBottom) stipple(c,365,unknownY,419,TimelineBottom-unknownY,2);
        int step = m.endHour-m.startHour > 8 ? 2 : 1;
        for (int hour = m.startHour; hour <= m.endHour; hour += step) {
            int y = timelineY(hour*60,first,last);
            String hourText = m.clock24 ? String(hour) : hour == 12 ? "Noon" :
                String(hour%12 ? hour%12 : 12) + (hour < 12 ? " AM" : " PM");
            text(c,310,y-3,hourText,nullptr,Black,49);
            for (int x=365; x<784; x+=5) c.drawPixel(x,y,Black);
        }
        TimeSlot slots[48];
        for (int i=0; i<d.count; ++i) slots[i] = {d.events[i].startMinute,d.events[i].endMinute,d.events[i].past};
        TimelineLayout layout;
        placeTimeline(slots,d.count,first,last,layout);
        for (int i=0; i<layout.count; ++i) {
            const EventPlacement &p = layout.blocks[i];
            const TimelineEvent &e = d.events[p.index];
            int headerRoom = p.height;
            for (int j=i+1; j<layout.count; ++j) {
                const EventPlacement &later = layout.blocks[j];
                if (later.y < p.y+p.height) headerRoom = min(headerRoom,later.y-p.y-2);
            }
            bool solid = e.active && !e.tentative;
            uint16_t ink = solid ? White : Black;
            // A white separation edge keeps concurrent black cards distinct.
            c.fillRoundRect(p.x-2,p.y-2,p.width+4,p.height+4,9,White);
            c.fillRoundRect(p.x,p.y,p.width,p.height,8,solid ? Black : White);
            c.drawRoundRect(p.x,p.y,p.width,p.height,8,Black);
            if (e.tentative) {
                if (headerRoom < 48) stipple(c,p.x+1,p.y+5,4,p.height-10,4,2);
                else {
                    stipple(c,p.x+1,p.y+1,p.width-2,p.height-2,4,7);
                    c.fillRoundRect(p.x+3,p.y+3,p.width-6,p.height-6,5,White);
                }
            }
            // Keep title/time inside the first protected 34px even when another
            // meeting covers the lower part. Detail rows are deliberately omitted.
            int rowY = p.y+min(16,(headerRoom-17)/2);
            text(c,p.x+18,rowY,e.title,&FreeSansBold9pt7b,ink,p.width-180);
            text(c,TimelineRight-146,rowY+4,e.time,nullptr,ink,130);
        }
        if (!layout.count) wrapped(c,365,160,d.coverageMinute < 1440 ? "Later schedule unknown" :
                                  layout.outside ? "No meetings in these hours" : "No upcoming meetings",
                                  &FreeSans9pt7b,400,2,24);
        String counts;
        if (layout.overflow) counts += "+" + String(layout.overflow) + " more  ";
        if (layout.earlier) counts += String(layout.earlier) + " earlier  ";
        if (layout.outside) counts += String(layout.outside) + " outside hours";
        text(c,365,451,counts,nullptr,Black,419);
    }
    text(c,22,465,m.footer + "    Stippled cards: tentative",nullptr,Black,756);
    c.setFont(nullptr);
}

template<class Canvas>
void drawDashboardPage(Canvas &c, const DashboardPage &m) {
    c.fillScreen(White);
    centered(c, 260, 14, 280, m.title, &FreeSansBold12pt7b);
    text(c, 18, 21, m.date, nullptr, Black, 220);
    c.drawFastHLine(0, 48, 800, Black);
    for (int i = 0; i < min(m.count, 6); ++i) {
        int x = 16 + (i % 3) * 260, y = 66 + (i / 3) * 190;
        c.drawRoundRect(x, y, 248, 173, 9, Black);
        stipple(c,x+1,y+1,246,42,2,8);
        c.fillRoundRect(x+12,y+7,224,29,5,White);
        centered(c,x+20,y+14,208,m.cards[i].title,&FreeSansBold9pt7b);
        text(c, x + 15, y + 55, m.cards[i].value, &FreeSansBold24pt7b, Black, 218);
        text(c, x + 15, y + 130, m.cards[i].detail, &FreeSans9pt7b, Black, 218);
    }
    c.drawFastHLine(0, 448, 800, Black); small(c, 18, 460, m.footer.substring(0, 125));
    c.setFont(nullptr);
}
} // namespace epaper_ui
