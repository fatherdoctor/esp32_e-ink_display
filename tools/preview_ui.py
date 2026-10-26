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


def boxed_text(draw, box, value, size=16, bold=False, fill='black', lines=1, leading=None):
    """Draw measured, word-wrapped text and assert every ink box fits its bounds."""
    left, top, right, bottom = box
    f = font(size, bold)
    leading = leading or size + 4
    remaining = str(value).strip()
    for row in range(lines):
        if not remaining:
            break
        fit = 0
        for end in range(1, len(remaining) + 1):
            if draw.textbbox((0, 0), remaining[:end], font=f, anchor='lt')[2] > right-left:
                break
            fit = end
        if fit == len(remaining):
            line, remaining = remaining, ''
        elif row == lines-1:
            line = remaining[:fit].rstrip()
            while line and draw.textbbox((0, 0), line+'...', font=f, anchor='lt')[2] > right-left:
                line = line[:-1].rstrip()
            line, remaining = line+'...', ''
        else:
            cut = remaining.rfind(' ', 0, fit+1)
            if cut <= 0: cut = max(1, fit)
            line, remaining = remaining[:cut].rstrip(), remaining[cut:].lstrip()
        xy = (left, top+row*leading)
        bounds = draw.textbbox(xy, line, font=f, anchor='lt')
        assert bounds[0] >= left and bounds[1] >= top and bounds[2] <= right and bounds[3] <= bottom, (value, bounds, box)
        draw.text(xy, line, font=f, anchor='lt', fill=fill)


def calendar_page(state):
    img, d = canvas()
    boxed_text(d, (20,22,136,102), '26', 80, True)
    boxed_text(d, (144,22,298,51), 'Monday', 23, True)
    boxed_text(d, (144,60,298,86), 'October 2026', 17)
    busy = state != 'available'
    status = {'meeting': 'In a meeting', 'available': 'Available', 'out-of-office': 'Out of office'}[state]
    d.rounded_rectangle((18,120,298,240), radius=16, fill='black' if busy else 'white', outline='black')
    sb = d.textbbox((0,0), status, font=font(43, True), anchor='lt')
    status_top = 120+(120-sb[3])//2 if sb[2] <= 248 else 135
    boxed_text(d, (34,status_top,282,230), status, 43, True, 'white' if busy else 'black', lines=2, leading=52)
    location = {'meeting': 'Conference Room B', 'available': 'You can stop by', 'out-of-office': 'Away from the desk'}[state]
    boxed_text(d, (22,258,296,312), location, 24, True, lines=2, leading=28)
    boxed_text(d, (22,324,296,368), 'Project review / Hybrid with Teams' if state == 'meeting' else
               'Free until 1:00 PM' if state == 'available' else 'Annual leave / All day', 18, lines=2, leading=22)
    boxed_text(d, (22,383,296,405), 'Next available / At 10:00 AM' if state == 'out-of-office' else 'Next available', 18)
    availability = '11:30 AM' if state == 'meeting' else 'Now' if state == 'available' else 'Tomorrow'
    boxed_text(d, (21,411,298,451), availability, 38, True)
    now = 10*60+45 if state == 'meeting' else 12*60 if state == 'available' else 8*60
    for col, label, date in ((0, 'Today', 'Mon, Oct 26'), (1, 'Tomorrow', 'Tue, Oct 27')):
        left = 316+col*238
        d.rounded_rectangle((left,12,left+230,450), radius=12, outline='black')
        boxed_text(d, (left+13,27,left+217,54), label, 23, True)
        boxed_text(d, (left+13,62,left+217,84), date, 18)
        boxed_text(d, (left+13,89,left+217,115), 'All day: Annual leave' if col == 0 and state == 'out-of-office'
                   else 'Reminder: Submit expenses' if col == 0 else '', 12, lines=2, leading=12)
        entries = [e for e in EVENTS if e[0] == col]
        if state == 'out-of-office' and col == 0: entries = []
        earlier = sum(1 for e in entries if col == 0 and e[2] <= now)
        entries = [e for e in entries if col != 0 or e[2] > now]
        for index, (_, start, end, title, active) in enumerate(entries[:3]):
            x=left+8; y=132+index*102
            active = active and state == 'meeting'
            ink='white' if active else 'black'
            d.rounded_rectangle((x,y,x+214,y+94),radius=9, fill='black' if active else 'white',outline='black')
            def clock(minutes):
                hour, minute=divmod(minutes,60)
                return f'{hour%12 or 12}:{minute:02} {"AM" if hour<12 else "PM"}'
            boxed_text(d, (x+10,y+10,x+204,y+30), clock(start)+' - '+clock(end), 15, fill=ink)
            boxed_text(d, (x+10,y+34,x+204,y+74), title, 18, True, ink, lines=2, leading=21)
            detail = 'Accepted / Hybrid' if active else 'Tentative / Teams' if title == 'Planning session' else 'Accepted / In person'
            boxed_text(d, (x+10,y+78,x+204,y+90), detail, 12, fill=ink)
        if not entries:
            boxed_text(d, (left+13,156,left+217,228), 'No upcoming meetings', 18, lines=3, leading=24)
        summary = (f'+{len(entries)-3} more  ' if len(entries)>3 else '') + (f'{earlier} earlier' if earlier else '')
        boxed_text(d, (left+13,438,left+217,448), summary, 10)
    boxed_text(d, (22,465,778,478), 'Synced 8:30 AM     KEY1 / NFC: Sync                         DEMO DATA / 3.94 V', 11)
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
