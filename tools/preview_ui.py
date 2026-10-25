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
    # Date/status sidebar follows the supplied physical-calendar reference.
    d.rectangle((0, 0, 299, 91), fill='black')
    text(d, (17, -2), '26', 72, True, 'white')
    text(d, (112, 16), 'Monday', 23, True, 'white')
    text(d, (113, 50), 'October 2026', 16, fill='white')
    text(d, (22, 111), 'CURRENT AVAILABILITY', 12, True)
    if state == 'meeting':
        text(d, (20, 138), 'IN A', 36, True)
        text(d, (20, 177), 'MEETING', 36, True)
        text(d, (22, 232), 'Conference Room B', 21)
        text(d, (22, 263), 'Project review', 16)
        availability, detail = '11:30 AM', 'Free for 1 hr 30 min'
    elif state == 'available':
        text(d, (20, 144), 'AVAILABLE', 35, True)
        text(d, (22, 205), 'You can stop by', 21)
        text(d, (22, 246), 'Free until 1:00 PM', 18)
        availability, detail = 'Now', 'Next meeting at 1:00 PM'
    else:
        text(d, (20, 138), 'OUT OF', 36, True)
        text(d, (20, 177), 'OFFICE', 36, True)
        text(d, (22, 236), 'Away from the desk', 20)
        availability, detail = 'Tomorrow', 'Free at 10:00 AM'
    rule(d, 298)
    text(d, (22, 313), 'NEXT AVAILABLE', 12, True)
    text(d, (20, 331), availability, 34, True)
    text(d, (22, 380), detail, 15)
    rule(d, 414)
    text(d, (22, 427), 'NEXT UP', 11, True)
    text(d, (86, 424), 'Tue 9:00  Planning' if state == 'out-of-office' else '1:00  Design workshop', 13, width=200)
    d.line((300, 0, 300, 447), fill='black')
    # Two separate day columns. Event fill identifies the current meeting.
    for col, label, date in ((0, 'TODAY', 'Mon, Oct 26'), (1, 'TOMORROW', 'Tue, Oct 27')):
        x = 342 + col * 222
        text(d, (x + 8, 13), label, 12, True)
        text(d, (x + 8, 32), date, 18, True)
        if state == 'out-of-office' and col == 0:
            text(d, (x + 8, 59), 'All day: Out of office', 10, True)
    d.line((554, 0, 554, 447), fill='black')
    for hour in range(8, 19):
        y = 76 + (hour - 8) * 35
        text(d, (310, y - 7), str(hour if hour <= 12 else hour - 12), 11)
        d.line((337, y, 785, y), fill='black')
    events = ([(1, 480, 540, 'Out of office', True)] + [e for e in EVENTS if e[0] == 1]
              if state == 'out-of-office' else EVENTS)
    for day, start, end, title, active in events:
        x = 342 + day * 222
        y = 76 + (start - 480) * 35 // 60
        h = max(17, (end - start) * 35 // 60)
        fill = 'black' if active and state in ('meeting', 'out-of-office') else 'white'
        ink = 'white' if fill == 'black' else 'black'
        d.rectangle((x, y, x + 206, y + h - 2), fill=fill, outline='black')
        text(d, (x + 6, y + 1), title, 10 if h < 25 else 13, True, ink, width=194)
        if h >= 32:
            hr, minute = divmod(start, 60)
            ehr, em = divmod(end, 60)
            time_label = f'{hr % 12 or 12}:{minute:02} - {ehr % 12 or 12}:{em:02}'
            text(d, (x + 6, y + 19), time_label, 10, fill=ink)
    d.line((0, 448, 800, 448), fill='black')
    text(d, (18, 456), 'Synced 8:30 AM', 11)
    text(d, (300, 456), 'KEY1  Sync', 11)
    text(d, (594, 456), 'DEMO DATA  /  3.94 V', 11)
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
