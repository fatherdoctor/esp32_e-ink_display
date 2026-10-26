#pragma once

namespace epaper_ui {
constexpr int TimelineTop = 104, TimelineBottom = 444;
constexpr int TimelineLeft = 365, TimelineRight = 784;
constexpr int TimelineHeader = 34;
struct TimeSlot { int start, end; bool past; };
struct EventPlacement { int index, x, y, width, height; };
struct TimelineLayout {
    int count = 0, earlier = 0, outside = 0, overflow = 0;
    EventPlacement blocks[48];
};
inline int timelineY(int minute, int first, int last) {
    return TimelineTop + (minute-first)*(TimelineBottom-TimelineTop)/(last-first);
}
inline int larger(int a, int b) { return a > b ? a : b; }
inline int smaller(int a, int b) { return a < b ? a : b; }
inline bool overlaps(const TimeSlot &a, const TimeSlot &b) {
    return a.start < b.end && b.start < a.end;
}
// Inputs are chronological. Event times remain authoritative: minimum readable
// heights and protected headings can expand the visual duration of short events.
// Only genuinely concurrent meetings share horizontal area. Additional entries
// that cannot retain a complete heading are counted instead of clipped.
inline void placeTimeline(const TimeSlot *events, int count, int first, int last,
                          TimelineLayout &out) {
    out.count = out.earlier = out.outside = out.overflow = 0;
    if (last <= first) return;
    for (int i = 0; i < count && i < 48; ++i) {
        const TimeSlot &e = events[i];
        if (e.past) { ++out.earlier; continue; }
        if (e.end <= first || e.start >= last || e.end <= e.start) { ++out.outside; continue; }
        int y = timelineY(larger(first,e.start),first,last), offset = 0;
        int height = larger(TimelineHeader,timelineY(smaller(last,e.end),first,last)-y);
        for (int j = 0; j < out.count; ++j) {
            const EventPlacement &p = out.blocks[j];
            if (overlaps(e,events[p.index])) {
                y = larger(y,p.y+TimelineHeader);
                offset = larger(offset,smaller(72,p.x-TimelineLeft+36));
            } else {
                y = larger(y,p.y+p.height+6);
            }
        }
        if (y+TimelineHeader > TimelineBottom) { ++out.overflow; continue; }
        for (int j = 0; j < out.count; ++j) {
            EventPlacement &p = out.blocks[j];
            if (overlaps(e,events[p.index])) p.height = larger(p.height,y+12-p.y);
        }
        height = smaller(height,TimelineBottom-y);
        out.blocks[out.count++] = {i,TimelineLeft+offset,y,TimelineRight-TimelineLeft-offset,height};
    }
}
} // namespace epaper_ui
