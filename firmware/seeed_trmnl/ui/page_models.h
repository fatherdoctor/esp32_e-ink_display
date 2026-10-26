#pragma once
#include <Arduino.h>

// Page models contain display-ready data only: no BLE, Outlook, HA or driver calls.
namespace epaper_ui {
enum class Availability { Unknown, Available, Meeting, OutOfOffice, Done };
struct TimelineEvent {
    int startMinute = 0, endMinute = 0;
    String title;
    String detail, time;
    bool tentative = false;
    bool active = false;
    bool past = false;
};
struct DayColumn {
    String label, date, allDay;
    bool covered = false;
    int coverageMinute = 1440;
    int count = 0;
    TimelineEvent events[48];
};
struct CalendarPage {
    Availability status = Availability::Unknown;
    String day, weekday, monthYear, subject, location, statusLabel;
    String nextAvailable, availabilityDetail, nextUp, footer;
    DayColumn today;
    int startHour = 8, endHour = 18;
    bool clock24 = false;
};
struct DashboardCard { String title, value, detail; };
struct DashboardPage {
    String title, date, footer;
    int count = 0;
    DashboardCard cards[6];
};
} // namespace epaper_ui
