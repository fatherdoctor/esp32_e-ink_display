"""Render synthetic 800x480 e-paper design previews; never access Outlook or HA."""
from pathlib import Path
import argparse
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 800, 480
ROOT = Path(__file__).resolve().parents[1]


def font(size, bold=False):
    candidates = ([Path('C:/Windows/Fonts') / ('segoeuib.ttf' if bold else 'segoeui.ttf'),
                   Path('/usr/share/fonts/truetype/dejavu') /
                   ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')])
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def canvas():
    img = Image.new('RGB', (WIDTH, HEIGHT), 'white')
    return img, ImageDraw.Draw(img)


def text(draw, xy, value, size=16, bold=False, fill='black', width=None):
    f = font(size, bold)
    if width:
        while value and draw.textbbox((0, 0), value, font=f)[2] > width:
            value = value[:-2].rstrip() + '~' if len(value) > 2 else ''
    draw.text(xy, value, font=f, fill=fill, stroke_width=0)


def rule(draw, y, left=20, right=280):
    draw.line((left, y, right, y), fill='black', width=1)


EVENTS = [
    (0, 9 * 60, 9 * 60 + 30, 'Team stand-up', False),
    (0, 10 * 60 + 30, 11 * 60 + 30, 'Project review', True),
    (0, 13 * 60, 14 * 60, 'Design workshop', False),
    (0, 15 * 60, 16 * 60, 'Focus time', False),
    (1, 9 * 60, 10 * 60, 'Planning session', False),
    (1, 11 * 60, 12 * 60, 'Customer review', False),
    (1, 13 * 60 + 30, 15 * 60, 'Out of office', False),
]


def calendar_page(state):
    img, d = canvas()
    text(d, (22, 15), 'Monday', 23, True)
    text(d, (18, 40), '26', 80, True)
    text(d, (137, 83), 'October 2026', 17)
    busy = state != 'available'
    status = {'meeting': 'In a meeting', 'available': 'Available', 'out-of-office': 'Out of office'}[state]
    d.rounded_rectangle((20, 151, 285, 189), radius=19, fill='black' if busy else 'white', outline='black')
    text(d, (35, 157), status, 19, True, 'white' if busy else 'black')
    location = {'meeting': 'Conference Room B', 'available': 'You can stop by', 'out-of-office': 'Away from the desk'}[state]
    text(d, (22, 209), location, 22, True, width=265)
    text(d, (22, 251), 'Project review · Hybrid / Teams' if state == 'meeting' else
         'Free until 1:00 PM' if state == 'available' else 'Annual leave · All day', 15, width=265)
    text(d, (22, 306), 'Next available', 13)
    availability = '11:30 AM' if state == 'meeting' else 'Now' if state == 'available' else 'Tomorrow'
    text(d, (20, 326), availability, 36, True)
    text(d, (22, 378), 'After this meeting block' if state == 'meeting' else
         'Next meeting at 1:00 PM' if state == 'available' else 'At 10:00 AM', 15)
    text(d, (22, 415), 'Next up', 12)
    text(d, (22, 432), '1:00  Design workshop' if state != 'out-of-office' else 'Tue 10:00  Planning', 13)
    for col, label, date in ((0, 'Today', 'Mon, Oct 26'), (1, 'Tomorrow', 'Tue, Oct 27')):
        x = 344 + col * 224
        d.rounded_rectangle((x-6, 12, x+212, 447), radius=12, outline='black')
        text(d, (x+8, 24), label, 23, True)
        text(d, (x+8, 56), date, 12)
        text(d, (x+8, 77), 'All day: Annual leave' if col == 0 and state == 'out-of-office'
             else 'Reminder: Submit expenses' if col == 0 else '', 10, width=195)
        for hour in range(8, 19, 2):
            y = 99 + (hour-8)*327//10
            for xx in range(x, x+206, 5): d.point((xx,y), fill='black')
            if col == 0: text(d, (310,y-6), str(hour%12 or 12), 11)
    events = ([e for e in EVENTS if e[0] == 1] if state == 'out-of-office' else EVENTS)
    for day, start, end, title, active in events:
        x=344+day*224; y=99+(start-480)*327//600
        h=max(12,(end-start)*327//600-2)
        active = active and state == 'meeting'
        ink='white' if active else 'black'
        d.rounded_rectangle((x,y,x+204,y+h),radius=min(6,h//2), fill='black' if active else 'white',outline='black')
        text(d,(x+6,y+2),title,10 if h<22 else 13,True,ink,width=192)
        if h>=28:
            detail = 'Hybrid / Teams · Accepted' if active else 'Teams · Tentative' if title == 'Planning session' else 'In person · Accepted'
            text(d,(x+6,y+19),detail,10,fill=ink,width=192)
    text(d, (22, 461), 'Synced 8:30 AM     KEY1 / NFC: Sync                         DEMO DATA  /  3.94 V', 11)
    return img.convert('1', dither=Image.Dither.NONE)


def dashboard_page():
    img, d = canvas()
    text(d, (18, 12), 'HOME', 22, True)
    text(d, (120, 18), 'MONDAY, OCTOBER 26', 12)
    text(d, (576, 18), 'HOME   CALENDAR   WEATHER', 11)
    d.line((0, 48, 800, 48), fill='black')
    def card(x, y, w, h, title):
        d.rounded_rectangle((x, y, x + w, y + h), radius=9, outline='black', width=2)
        text(d, (x + 15, y + 12), title, 12, True)
    card(16, 66, 248, 152, 'MONDAY')
    text(d, (30, 96), '10:37', 48, True)
    text(d, (34, 166), 'Clear   /   72 F', 22)
    card(16, 232, 248, 197, 'WEATHER')
    for y, hour, value in ((272, '11 AM', '74 F  Clear'), (319, '12 PM', '77 F  Clear'), (366, '1 PM', '79 F  Partly cloudy')):
        text(d, (32, y), hour, 14, True)
        text(d, (110, y), value, 13)
        if y < 366: d.line((32, y + 35, 246, y + 35), fill='black')
    card(276, 66, 248, 173, 'CLIMATE')
    text(d, (292, 103), 'DOWNSTAIRS', 11, True)
    text(d, (292, 122), '72.4 F', 30, True)
    text(d, (292, 178), 'Upstairs     72.3 F', 18)
    card(276, 253, 248, 176, 'HOUSE')
    for y, name, value in ((294, 'Scene', 'Home'), (335, 'Lights', '4 on'), (376, 'Doors', 'Closed')):
        text(d, (292, y), name, 16)
        text(d, (410, y), value, 16, True)
    card(536, 66, 248, 152, 'SECURITY')
    d.polygon(((660, 105), (685, 118), (682, 149), (660, 166), (638, 149), (635, 118)), outline='black', width=3)
    text(d, (582, 174), 'Armed stay', 23, True)
    card(536, 232, 248, 197, 'HOUSEHOLD')
    for y, name, value in ((274, 'Adult 1', 'Home'), (320, 'Adult 2', 'Home'), (366, 'Guest mode', 'Off')):
        text(d, (552, y), name, 16)
        text(d, (699, y), value, 16, True)
    d.line((0, 448, 800, 448), fill='black')
    text(d, (18, 456), 'Updated 10:37 AM', 11)
    text(d, (560, 456), 'READ-ONLY DESIGN  /  DEMO DATA', 11)
    return img.convert('1', dither=Image.Dither.NONE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'previews')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for state in ('meeting', 'available', 'out-of-office'):
        calendar_page(state).save(args.output / f'calendar-{state}.png')
    dashboard_page().save(args.output / 'dashboard.png')
    print(f'Rendered monochrome design previews into {args.output}')


if __name__ == '__main__':
    main()
