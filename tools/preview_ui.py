"""Render synthetic 800x480 e-paper design previews; never access Outlook or HA."""
from pathlib import Path
import argparse
import math
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


BAYER = ((0,8,2,10),(12,4,14,6),(3,11,1,9),(15,7,13,5))

def stipple(img, box, level=2, radius=0):
    """level / 16 black coverage. Pattern phase stays fixed to panel pixels."""
    x0, y0, x1, y1 = box
    mask = Image.new('1', img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=1)
    pixels, inside = img.load(), mask.load()
    for y in range(y0, y1+1):
        for x in range(x0, x1+1):
            if inside[x, y]: pixels[x, y] = (0, 0, 0) if BAYER[y%4][x%4] < level else (255, 255, 255)

def label(d, box, value, size=16, bold=False, ink='black', lines=1, leading=None):
    boxed_text(d, box, value, size, bold, ink, lines=lines, leading=leading)

def calendar_page(state='meeting'):
    img, d = canvas()
    label(d,(20,22,136,102),'26',80,True)
    label(d,(144,22,298,51),'Monday',23,True)
    label(d,(144,60,298,86),'October 2026',17)
    busy = state != 'available'
    status = {'meeting':'In a meeting','available':'Available','out-of-office':'Out of office'}[state]
    d.rounded_rectangle((18,120,298,240),radius=16,fill='black' if busy else 'white',outline='black')
    sb=d.textbbox((0,0),status,font=font(43,True),anchor='lt')
    status_top=120+(120-sb[3])//2 if sb[2]<=248 else 135
    label(d,(34,status_top,282,230),status,43,True,'white' if busy else 'black',lines=2,leading=52)
    location={'meeting':'Room B + Teams','available':'You can stop by','out-of-office':'Away from the desk'}[state]
    label(d,(22,258,296,312),location,24,True,lines=2,leading=28)
    detail={'meeting':'2 overlapping meetings','available':'Free until 1:00 PM','out-of-office':'Annual leave / All day'}[state]
    label(d,(22,324,296,368),detail,18,lines=2,leading=22)
    label(d,(22,383,296,405),'Next available / At 10:00 AM' if state=='out-of-office' else 'Next available',18)
    label(d,(21,411,298,451),{'meeting':'11:45 AM','available':'Now','out-of-office':'Tomorrow'}[state],38,True)

    # One compact, 52px day header frees the schedule area for the whole day.
    d.rounded_rectangle((316,12,784,64),radius=10,outline='black')
    stipple(img,(317,13,783,63),2,9)
    d.rounded_rectangle((324,20,776,56),radius=5,fill='white')
    label(d,(340,28,470,53),'Today',20,True)
    label(d,(584,30,760,51),'Monday, October 26',15)
    label(d,(366,78,780,96),'All day: Annual leave' if state=='out-of-office' else 'All day: Submit expenses / Free',12)

    top,bottom=104,444
    def at(hour): return round(top+(hour-10)*(bottom-top)/7)
    for hour in range(10,18):
        y=at(hour)
        text='Noon' if hour==12 else f'{hour%12 or 12} {"AM" if hour<12 else "PM"}'
        label(d,(310,y-5,359,y+12),text,11)
        for x in range(365,782,5): d.point((x,y),fill='black')

    # Concurrent events share horizontal space and really occlude one another,
    # as in the user's reference. Both essential headings stay above the overlap.
    events=[
        (10,11.5,'Project review','10:00 AM - 11:30 AM',0,'black'),
        (10.75,11.75,'Quick check-in','10:45 AM - 11:45 AM',36,'tentative'),
        (12,12.5,'Lunch','12:00 PM - 12:30 PM',0,'white'),
        (13,14,'Design workshop','1:00 PM - 2:00 PM',0,'white'),
        (14.5,15.25,'Vendor call','2:30 PM - 3:15 PM',0,'tentative'),
        (16,17,'Focus time','4:00 PM - 5:00 PM',0,'white'),
    ]
    if state == 'out-of-office': events=[]
    if state == 'available': events=[e for e in events if e[1]>12]
    for start,end,title,time,offset,tone in events:
        x=365+offset; y=at(start); r=783
        h=max(34,at(end)-y)
        d.rounded_rectangle((x,y,r,y+h),radius=8,fill='black' if tone=='black' else 'white',outline='black')
        if tone=='tentative':
            if h < 48:
                # Short appointments use a side accent so dots never crowd text.
                stipple(img,(x+1,y+5,x+5,y+h-5),4,2)
            else:
                stipple(img,(x+1,y+1,r-1,y+h-1),4,7)
                d.rounded_rectangle((x+3,y+3,r-3,y+h-3),radius=5,fill='white')
        ink='white' if tone=='black' else 'black'
        # Essential details occupy one row. Padding is preserved even for the
        # inset overlapping card; lower-priority venue/RSVP rows are omitted.
        pad=18
        ty=y+(h-17)//2 if title not in ('Project review',) else y+12
        label(d,(x+pad,ty,r-162,ty+21),title,16,True,ink)
        label(d,(r-146,ty+2,r-16,ty+19),time,12,ink=ink)
    label(d,(22,465,780,479),'Synced 10:50 AM / Stippled cards: tentative / Synthetic preview data',11)
    return img.convert('1',dither=Image.Dither.NONE)

def dashboard_page():
    img, d = canvas()
    home_width=d.textbbox((0,0),'Home',font=font(30,True),anchor='lt')[2]
    home_x=(800-home_width)//2
    label(d, (home_x,16,home_x+home_width+1,53), 'Home', 30, True)
    label(d, (20,25,270,46), 'Monday, October 26', 16)
    label(d, (685,25,780,46), '10:45 AM', 16)
    d.line((20,58,780,58), fill='black')

    def card(box, title, tone=2, dark=False):
        x, y, r, b = box
        d.rounded_rectangle(box, radius=14, fill='black' if dark else 'white', outline='black')
        bounds=d.textbbox((0,0),title,font=font(16,True),anchor='lt')
        text_width=bounds[2]-bounds[0]
        text_x=(x+r-text_width)//2
        if not dark:
            stipple(img, (x+1,y+1,r-1,y+42), tone, 13)
            d.rounded_rectangle((text_x-12,y+7,text_x+text_width+12,y+36),radius=5,fill='white')
        label(d, (text_x,y+14,text_x+text_width+1,y+37), title, 16, True, 'white' if dark else 'black')

    card((16,74,264,240), 'Weather')
    label(d, (30,127,225,178), '72 F', 46, True)
    label(d, (32,188,245,214), 'Clear skies', 20)
    label(d, (32,218,245,234), 'High 76 / Low 58', 13)
    # Simple sun icon; all strokes are panel pixels.
    cx, cy = 225, 157
    d.ellipse((cx-12,cy-12,cx+12,cy+12), outline='black', width=2)
    for index in range(8):
        a=math.pi*index/4
        d.line((cx+17*math.cos(a),cy+17*math.sin(a),cx+23*math.cos(a),cy+23*math.sin(a)),fill='black',width=2)

    card((276,74,524,240), 'Indoor climate')
    label(d, (291,130,508,178), '72.4 F', 42, True)
    label(d, (292,185,508,211), 'Downstairs', 20)
    label(d, (292,219,508,234), 'Upstairs 72.3 F / Humidity 44%', 12)

    card((536,74,784,240), 'Security', dark=True)
    # Shield marks status, not a touch control.
    d.polygon(((745,125),(761,132),(759,155),(745,169),(731,155),(729,132)),outline='white',width=2)
    d.line((737,145,743,151,753,139),fill='white',width=2)
    label(d, (551,137,725,178), 'Armed stay', 28, True, 'white')
    label(d, (551,194,769,220), 'All entry points closed', 17, ink='white')

    card((16,254,264,444), 'Lights')
    label(d, (31,309,249,355), '4 on', 38, True)
    label(d, (32,369,249,392), 'Living room', 17)
    label(d, (195,369,250,392), '2 on', 17, True)
    label(d, (32,409,249,432), 'Kitchen', 17)
    label(d, (195,409,250,432), '2 on', 17, True)

    card((276,254,524,444), 'Energy')
    label(d, (291,309,509,350), '1.2 kW', 34, True)
    label(d, (292,354,509,376), 'Solar producing 2.8 kW', 16)
    # Dithered history bars distinguish earlier values from the current solid bar.
    heights=(14,22,31,25,38,33,20,27,36)
    for index, h in enumerate(heights):
        x=294+index*23
        if index == len(heights)-1: d.rectangle((x,426-h,x+14,426),fill='black')
        else: stipple(img,(x,426-h,x+14,426),4 if index%2 else 8)

    card((536,254,784,444), 'Household')
    for y, who, status in ((313,'Adult 1','Home'),(354,'Adult 2','Away'),(402,'Garage','Closed')):
        label(d, (551,y,665,y+25), who, 18)
        if status == 'Away':
            stipple(img,(675,y-4,769,y+28),4,9)
            d.rounded_rectangle((682,y,762,y+24),radius=5,fill='white')
        else: d.rounded_rectangle((675,y-4,769,y+28),radius=9,outline='black')
        label(d, (687,y+2,759,y+25), status, 16, True)

    label(d, (20,461,780,478), 'Updated 10:45 AM / Read-only Home Assistant concept / Synthetic data', 12)
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
