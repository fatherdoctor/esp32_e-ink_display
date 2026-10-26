#pragma once
#include "page_models.h"
#include "timeline_math.h"

// This presenter translates the semantic calendar into a page model. It does
// not draw, refresh, sleep, connect to BLE, or know where the data came from.
namespace epaper_ui {
inline String dateText(uint32_t epoch, const char *format) {
    time_t value = time_t(epoch) + utcOffset(epoch);
    struct tm local;
    gmtime_r(&value, &local);
    char buffer[40]; strftime(buffer, sizeof(buffer), format, &local);
    return String(buffer);
}
inline int minuteOfDay(uint32_t epoch) {
    return wallMinute(epoch, utcOffset(epoch));
}
inline CalendarPage presentCalendar(uint32_t now, float voltage) {
    CalendarPage m;
    m.startHour = settings.timeline_start_hour; m.endHour = settings.timeline_end_hour;
    m.clock24 = settings.use_24_hour_time;
    bool valid = currentDay(now), known = valid && now < knowledgeUntil(now);
    if (validClock(now)) {
        m.day = dateText(now, "%d"); m.weekday = dateText(now, "%A");
        m.monthYear = dateText(now, "%B %Y");
    } else { m.day = "--"; m.weekday = "Calendar"; m.monthYear = "Sync to set date"; }
    uint32_t todayEnd = calendarDayEnd(now), nextStart = todayEnd;
    uint32_t busyEnd = now;
    int active = -1, next = -1, activeCount = 0;
    for (int i = 0; i < calendar.count; ++i) {
        const Event &e = calendar.events[i];
        if (blocksAvailability(e) && e.start <= now && e.end > now) {
            ++activeCount;
            if (active < 0 || e.status == 3) active = i;
            busyEnd = max(busyEnd, e.end);
        }
        if (blocksAvailability(e) && e.start > now && e.start < todayEnd) nextStart = min(nextStart, e.start);
        if (e.start > now && (next < 0 || e.start < calendar.events[next].start)) next = i;
    }
    if (active >= 0) for (int pass = 0; pass < 48; ++pass)
        for (int i = 0; i < calendar.count; ++i)
            if (blocksAvailability(calendar.events[i]) && calendar.events[i].start <= busyEnd && calendar.events[i].end > busyEnd)
                busyEnd = calendar.events[i].end;
    if (!known) {
        m.status = Availability::Unknown;
        m.location = settings.button_enabled ? "Press KEY1 to sync" :
            settings.nfc_enabled ? "Tap NFC to sync" : "Reset panel to sync";
        m.subject = "Incomplete or stale schedule"; m.nextAvailable = "Unknown";
    } else if (active >= 0) {
        const Event &e = calendar.events[active];
        m.status = e.status == 3 ? Availability::OutOfOffice : Availability::Meeting;
        if (e.status == 4) m.statusLabel = "Working elsewhere";
        else if (e.response == 5) m.statusLabel = "Awaiting response";
        else if (e.response == 2 || e.status == 1) m.statusLabel = "Tentative meeting";
        m.location = strlen(e.location) ? String(e.location) : "Location not provided";
        if (e.status == 3 && !strlen(e.location)) m.location = "Away from the desk";
        if (e.venue == 1) m.location = "Microsoft Teams";
        if (e.venue == 3) m.location += " / Teams";
        m.subject = e.subject;
        if (activeCount > 1) {
            m.subject = String(activeCount) + " overlapping meetings";
            bool online = false, physical = false;
            String room;
            for (int i = 0; i < calendar.count; ++i) {
                const Event &other = calendar.events[i];
                if (!blocksAvailability(other) || other.start > now || other.end <= now) continue;
                online |= other.venue == 1 || other.venue == 3;
                physical |= other.venue == 2 || other.venue == 3;
                if ((other.venue == 2 || other.venue == 3) && strlen(other.location)) room = other.location;
            }
            if (online && physical) m.location = room.length() ? room : "In person";
            if (online && physical && m.location.indexOf("Teams") < 0) m.location += " + Teams";
        }
        uint32_t horizon = knowledgeUntil(now);
        if (now < calendar.end && calendar.until == calendar.end) horizon = calendar.tomorrowUntil;
        m.nextAvailable = busyEnd < horizon ? (busyEnd >= todayEnd ? "Tomorrow" : hhmm(busyEnd)) : "Unknown";
        m.availabilityDetail = m.nextAvailable == "Unknown" ? "Sync for later availability" :
            busyEnd >= todayEnd ? "At " + hhmm(busyEnd) : "After this meeting block";
    } else {
        bool done = nextStart == todayEnd && knowledgeUntil(now) == todayEnd;
        m.status = done ? Availability::Done : Availability::Available;
        m.location = done ? "No more meetings today" : "You can stop by";
        m.subject = done ? "" : "Free until " + hhmm(min(nextStart, knowledgeUntil(now)));
        m.nextAvailable = "Now"; m.availabilityDetail = "";
    }
    if (known && next >= 0) {
        const Event &e = calendar.events[next];
        m.nextUp = (e.start >= todayEnd ? dateText(e.start, "%a ") : "") + hhmm(e.start) + " " + e.subject;
    } else m.nextUp = known ? "No later meetings" : "Sync needed";
    {
        DayColumn &d = m.today;
        uint32_t from = now < calendar.end ? calendar.day : calendar.end;
        uint32_t to = todayEnd;
        d.label = "Today";
        d.covered = valid && to > from;
        d.date = d.covered || valid ? dateText(from, "%a, %b %d") : "Awaiting sync";
        uint32_t horizon = knowledgeUntil(now);
        d.coverageMinute = horizon >= to ? 1440 : minuteOfDay(horizon);
        for (int i = 0; d.covered && i < calendar.count; ++i) {
            const Event &e = calendar.events[i];
            if (e.end <= from || e.start >= to) continue;
            if (e.allDay || (e.start <= from && e.end >= to)) {
                if (d.allDay.length()) d.allDay += " / ";
                d.allDay += String(e.status == 0 ? "Reminder: " : "All day: ") + e.subject;
                continue;
            }
            if (d.count >= 48) break;
            TimelineEvent &block = d.events[d.count++];
            block.startMinute = e.start <= from ? 0 : minuteOfDay(e.start);
            block.endMinute = e.end >= to ? 1440 : minuteOfDay(e.end);
            if (needsClockChangeMarker(block.startMinute, block.endMinute)) {
                d.allDay = String("Clock change: ") + e.subject +
                    (d.allDay.length() ? " / " + d.allDay : "");
                --d.count;
                continue;
            }
            block.title = e.subject;
            block.time = hhmm(e.start) + " - " + hhmm(e.end);
            block.past = e.end <= now;
            block.tentative = e.response == 2 || e.status == 1 || e.response == 5;
            block.detail = e.response == 5 ? "Awaiting RSVP" : block.tentative ? "Tentative" :
                e.response == 3 ? "Accepted" : e.response == 1 ? "Organizer" : "Appointment";
            block.detail += e.venue == 1 ? " / Teams" : e.venue == 3 ? " / Hybrid" :
                e.venue == 2 ? " / In person" : "";
            block.active = blocksAvailability(e) && e.start <= now && e.end > now;
        }
    }
    m.footer = retained() ? "Synced " + dateText(calendar.synced, "%a ") + hhmm(calendar.synced) : "Not synchronized";
    if (settings.button_enabled) m.footer += "    KEY1: Sync";
    if (settings.nfc_enabled) m.footer += "    NFC: Sync";
    if (voltage > 2.5f && voltage < 4.6f) m.footer += "    Battery " + String(voltage, 2) + "V";
    return m;
}
} // namespace epaper_ui
