#include <cassert>
#include <random>
#include "firmware/seeed_trmnl/ui/timeline_layout.h"
using namespace epaper_ui;

static void verify(const TimeSlot *events, const TimelineLayout &m) {
    for (int i=0; i<m.count; ++i) {
        const auto &p=m.blocks[i];
        assert(p.y>=TimelineTop && p.y+p.height<=TimelineBottom);
        assert(p.height>=TimelineHeader && p.width>=347);
        assert(p.x>=TimelineLeft && p.x+p.width==TimelineRight);
        for (int j=i+1; j<m.count; ++j) {
            const auto &q=m.blocks[j];
            // Later layers never cover an earlier title/time row.
            assert(q.y>=p.y+TimelineHeader);
            if (!overlaps(events[p.index],events[q.index])) assert(q.y>=p.y+p.height+6);
            else assert(q.x>TimelineLeft && p.y+p.height>q.y);
        }
    }
}
int main() {
    TimelineLayout m;
    const TimeSlot approved[]={{600,690,false},{645,705,false},{720,750,false},
                               {780,840,false},{870,915,false},{960,1020,false}};
    placeTimeline(approved,6,600,1020,m);
    assert(m.count==6 && m.overflow==0);
    assert(m.blocks[1].x==TimelineLeft+36);
    assert(m.blocks[0].y+m.blocks[0].height>m.blocks[1].y);
    verify(approved,m);

    const TimeSlot adjacent[]={{600,601,false},{601,602,false},{602,603,false}};
    placeTimeline(adjacent,3,600,1080,m);
    assert(m.count==3);
    verify(adjacent,m); // Readable minimum heights must not create false overlaps.

    TimeSlot dense[48];
    for (auto &e:dense) e={600,660,false};
    placeTimeline(dense,48,600,1080,m);
    assert(m.count>1 && m.count<48 && m.count+m.overflow==48);
    verify(dense,m);

    const TimeSlot clipped[]={{400,500,true},{410,420,false},{470,510,false},{1080,1100,false}};
    placeTimeline(clipped,4,480,1080,m);
    assert(m.earlier==1 && m.outside==2 && m.count==1);
    verify(clipped,m);

    std::mt19937 rng(42);
    for (int trial=0; trial<1000; ++trial) {
        TimeSlot events[48]; int start=480;
        for (auto &e:events) { start+=rng()%30; e={start,start+1+int(rng()%180),false}; }
        placeTimeline(events,48,480,1080,m);
        assert(m.count+m.outside+m.overflow==48);
        verify(events,m);
    }
}
