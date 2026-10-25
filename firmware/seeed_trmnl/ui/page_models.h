#pragma once
#include <Arduino.h>

// Page models contain display-ready data only: no BLE, Outlook, HA or driver calls.
namespace epaper_ui {
enum class Availability { Unknown, Available, Meeting, OutOfOffice, Done };
struct TimelineEvent {
    int startMinute = 0, endMinute = 0;
    String title;
    bool active = false;
};
struct DayColumn {
    String label, date, allDay;
    bool covered = false;
    int coverageMinute = 1440;
    int count = 0;
    TimelineEvent events[12];
};
struct CalendarPage {
    Availability status = Availability::Unknown;
    String day, weekday, monthYear, subject, location;
    String nextAvailable, availabilityDetail, nextUp, footer;
    DayColumn columns[2];
};
struct DashboardCard { String title, value, detail; };
struct DashboardPage {
    String title, date, footer;
    int count = 0;
    DashboardCard cards[6];
};
} // namespace epaper_ui
