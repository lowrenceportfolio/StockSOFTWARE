"""VintDesk visual system for Tkinter.

Direction (taste-skill, seed 429721506): one motif. The price tag hanging from a second-hand garment is the only
shape with character: the primary button, the large figure on the overview, the photo mask, the list marker.
Components follow the Linear DESIGN.md (awesome-design-md): dark canvas, a surface ladder instead of borders and
shadows, one accent. The dealt palette proportions are kept; its colours come from the subject (Vinted teal).
Reference renders: .taste-skill/mock/ref-*.png.
"""
import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

from PIL import Image, ImageDraw

BG = '#0b0f10'
SURFACE_1 = '#121819'
SURFACE_2 = '#192123'
SURFACE_3 = '#212b2e'
ROW_ALT = '#0f1415'
INK = '#eef3f3'
MUTED = '#9fadb0'
ACCENT = '#09b1ba'
ACCENT_HOVER = '#2cc6ce'
ACCENT_INK = '#04282a'
NEGATIVE = '#f0606b'
POSITIVE = '#5fd39b'
WARNING = '#f2b35b'
DANGER_HOVER = '#311b1f'
DISABLED_INK = '#5d6a6c'

# Five type steps, in CSS pixels: small, body, lead, head, display.
SMALL, BODY, LEAD, HEAD, DISPLAY = 13, 15, 20, 40, 92
FAMILY = 'Segoe UI'
SCALE = 1.0

FONT_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'assets' / 'fonts'
FONT_FILES = ('PilcrowRounded-Regular.otf', 'PilcrowRounded-Bold.otf')


def load_private_fonts():
    """Register the bundled typeface for this process only (Windows). Falls back to Segoe UI if it is missing."""
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        loaded = 0
        for name in FONT_FILES:
            path = FONT_DIR / name
            if path.exists():
                loaded += ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, 0) > 0
        return loaded == len(FONT_FILES)
    except Exception:
        return False


def init(root):
    """Pick the family and the pixel scale once the Tk root exists."""
    global FAMILY, SCALE
    SCALE = max(root.winfo_fpixels('1i') / 96, 1.0)
    if 'Pilcrow Rounded' in tkfont.families(root):
        FAMILY = 'Pilcrow Rounded'


def px(value):
    return int(round(value * SCALE))


def font(size, weight='normal'):
    """A Tk font tuple from a CSS pixel size (negative size = pixels in Tk)."""
    return (FAMILY, -px(size), weight)


def tag_points(x, y, w, h, notch):
    return (x + notch, y, x + w, y, x + w, y + h, x + notch, y + h, x, y + h / 2)


def draw_tag(canvas, x, y, w, h, notch, fill, hole, outline=''):
    canvas.create_polygon(tag_points(x, y, w, h, notch), fill=fill, outline=outline, width=px(2) if outline else 0)
    r = notch * .25
    cx, cy = x + notch * .85, y + h / 2
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=hole, outline='')


class TagButton(tk.Canvas):
    """The primary action, shaped as the price tag with its punched hole."""

    def __init__(self, parent, text, command, bg=BG, size=BODY):
        self.text, self.command, self.parent_bg = text, command, bg
        self.label_font = font(size, 'bold')
        measure = tkfont.Font(font=self.label_font).measure(text)
        self.notch = px(14)
        width, height = measure + self.notch + px(34), px(38)
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0,
                         takefocus=True, cursor='hand2')
        self.hover = self.focused = False
        self.enabled = True
        self.bind('<Configure>', lambda _: self.draw())
        self.bind('<Enter>', lambda _: self.set(hover=True))
        self.bind('<Leave>', lambda _: self.set(hover=False))
        self.bind('<FocusIn>', lambda _: self.set(focused=True))
        self.bind('<FocusOut>', lambda _: self.set(focused=False))
        self.bind('<ButtonRelease-1>', self.click)
        self.bind('<Return>', lambda _: self.invoke())
        self.bind('<space>', lambda _: self.invoke())
        self.draw()

    def set(self, **state):
        for key, value in state.items():
            setattr(self, key, value)
        if 'enabled' in state:
            self.configure(cursor='hand2' if self.enabled else 'arrow', takefocus=self.enabled)
        self.draw()

    def draw(self):
        self.delete('all')
        w, h = int(self['width']), int(self['height'])
        if not self.enabled:
            fill, ink = SURFACE_3, DISABLED_INK
        else:
            fill, ink = (ACCENT_HOVER if self.hover else ACCENT), ACCENT_INK
        draw_tag(self, 1, 1, w - 2, h - 2, self.notch, fill, self.parent_bg, outline=INK if self.focused and self.enabled else '')
        self.create_text(self.notch + (w - self.notch) / 2, h / 2, text=self.text, fill=ink, font=self.label_font)

    def click(self, event):
        if 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self.invoke()

    def invoke(self):
        if self.enabled:
            self.command()
        return 'break'


def flat_button(parent, text, command, bg=None, danger=False):
    """Secondary action: square, one tone step above its ground, no border; focus shows an accent ring.
    danger=True marks destructive actions: red label, red-tinted hover."""
    rest = bg or SURFACE_2
    hover = DANGER_HOVER if danger else SURFACE_3 if rest != SURFACE_3 else '#2a3639'
    ink = NEGATIVE if danger else INK
    button = tk.Button(parent, text=text, command=command, font=font(BODY), bg=rest, fg=ink,
                       activebackground=hover, activeforeground=ink, disabledforeground=DISABLED_INK, relief='flat', bd=0,
                       padx=px(16), pady=px(8), cursor='hand2', highlightthickness=px(2), highlightbackground=BG,
                       highlightcolor=ACCENT, takefocus=True)
    button.rest = rest
    button.bind('<Enter>', lambda _: str(button['state']) != 'disabled' and button.configure(bg=hover))
    button.bind('<Leave>', lambda _: button.configure(bg=rest))
    button.bind('<Return>', lambda _: button.invoke())
    return button


def set_enabled(button, enabled):
    """Disabled actions keep their place but read as unavailable: dim label, plain cursor, skipped by Tab."""
    if isinstance(button, TagButton):
        if button.enabled != enabled:
            button.set(enabled=enabled)
        return
    button.configure(state='normal' if enabled else 'disabled', cursor='hand2' if enabled else 'arrow', takefocus=enabled)
    if not enabled:
        button.configure(bg=button.rest)


class BigTag(tk.Canvas):
    """The motif at its largest: a flat tag cropped by the right edge of the window, holding one figure."""

    def __init__(self, parent, figure, label, note='', notch=64, figure_size=DISPLAY, bg=BG, height=236, label_first=True):
        super().__init__(parent, bg=bg, height=px(height), highlightthickness=0, bd=0)
        self.values = figure, label, note
        self.notch, self.figure_size, self.parent_bg, self.label_first = px(notch), figure_size, bg, label_first
        self.bind('<Configure>', lambda _: self.draw())

    def draw(self):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        figure, label, note = self.values
        draw_tag(self, 0, 0, w + px(4), h, self.notch, ACCENT, self.parent_bg)
        x = self.notch + px(40)
        if self.label_first:
            self.create_text(x, h * .5 - px(self.figure_size * .62), text=label, anchor='w', fill=ACCENT_INK, font=font(LEAD, 'bold'))
            self.create_text(x - px(4), h * .5 + px(4), text=figure, anchor='w', fill=ACCENT_INK, font=font(self.figure_size, 'bold'))
            if note:
                self.create_text(x, h * .5 + px(self.figure_size * .62), text=note, anchor='w', fill=ACCENT_INK, font=font(SMALL))
        else:
            self.create_text(x - px(4), h * .5 - px(10), text=figure, anchor='w', fill=ACCENT_INK, font=font(self.figure_size, 'bold'))
            self.create_text(x, h * .5 + px(self.figure_size * .5), text=label, anchor='w', fill=ACCENT_INK, font=font(BODY))


class Slider(tk.Canvas):
    """Flat slider: accent fill on a surface track, a square thumb; arrows, PageUp/PageDown, Home/End move it."""

    def __init__(self, parent, variable, maximum, step, bg):
        super().__init__(parent, height=px(30), bg=bg, highlightthickness=px(2), highlightbackground=bg,
                         highlightcolor=ACCENT, bd=0, takefocus=True, cursor='hand2')
        self.variable, self.maximum, self.step = variable, maximum, step
        self.bind('<Configure>', lambda _: self.draw())
        self.bind('<Button-1>', self.drag)
        self.bind('<B1-Motion>', self.drag)
        for key, delta in (('<Left>', -step), ('<Right>', step), ('<Down>', -step), ('<Up>', step),
                           ('<Prior>', step * 10), ('<Next>', -step * 10)):
            self.bind(key, lambda _, d=delta: self.move(self.variable.get() + d))
        self.bind('<Home>', lambda _: self.move(0))
        self.bind('<End>', lambda _: self.move(self.maximum))
        self.trace = variable.trace_add('write', lambda *_: self.draw())
        self.bind('<Destroy>', lambda _: variable.trace_remove('write', self.trace))

    def move(self, value):
        value = min(max(round(value / self.step) * self.step, 0), self.maximum)
        self.variable.set(int(value))
        return 'break'

    def drag(self, event):
        self.focus_set()
        pad = px(9)
        self.move((event.x - pad) / max(self.winfo_width() - pad * 2, 1) * self.maximum)

    def draw(self):
        self.delete('all')
        w, h, pad = self.winfo_width(), self.winfo_height(), px(9)
        x = pad + (w - pad * 2) * self.variable.get() / self.maximum
        y = h / 2
        self.create_rectangle(pad, y - px(3), w - pad, y + px(3), fill=SURFACE_3, outline='')
        self.create_rectangle(pad, y - px(3), x, y + px(3), fill=ACCENT, outline='')
        self.create_rectangle(x - px(7), y - px(9), x + px(7), y + px(9), fill=INK, outline='')


def placeholder(entry, variable, text):
    """Example text shown inside an empty field; it never becomes the field's value."""
    label = tk.Label(entry, text=text, font=font(BODY), fg=MUTED, bg=SURFACE_2, bd=0, cursor='xterm')
    label.bind('<Button-1>', lambda _: entry.focus_set())
    def update(*_):
        if variable.get():
            label.place_forget()
        else:
            label.place(x=px(9), rely=.5, anchor='w')
    trace = variable.trace_add('write', update)
    entry.bind('<Destroy>', lambda _: variable.trace_remove('write', trace), add='+')
    update()
    return label


def tag_marker(parent, color, bg, width=18, height=10):
    """The motif at text size: list bullet and active-page marker."""
    canvas = tk.Canvas(parent, width=px(width), height=px(height), bg=bg, highlightthickness=0, bd=0)
    draw_tag(canvas, 0, 0, px(width), px(height), px(height * .5), color, bg)
    return canvas


def mask_tag(image, notch_ratio=.15, ground=BG):
    """Crop a photo into the tag silhouette (chamfered left side and hole), painted over the ground colour."""
    image = image.convert('RGB')
    w, h = image.size
    notch = int(w * notch_ratio)
    mask = Image.new('L', (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon(tag_points(0, 0, w, h, notch), fill=255)
    r, cx, cy = notch * .2, notch * .85, h / 2
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=0)
    out = Image.new('RGB', (w, h), ground)
    out.paste(image, (0, 0), mask)
    return out


STATUS_COLORS = {'In vendita': ACCENT, 'Riservato': WARNING, 'Da pubblicare': SURFACE_3,
                 'Venduto': MUTED, 'Archiviato': MUTED}


def list_thumb(photo_bytes, status, size=38):
    """Row thumbnail: the garment photo (or an empty tile) carrying a small tag in the colour of its stock state.
    The tag sits inside the tile, so the thumbnail reads the same on striped, plain and selected rows."""
    import io
    side = px(size)
    tile = Image.new('RGB', (side, side), SURFACE_3)
    if photo_bytes:
        with Image.open(io.BytesIO(photo_bytes)) as image:
            image.draft('RGB', (side * 2, side * 2))
            image = image.convert('RGB')
            scale = side / min(image.size)
            image = image.resize((max(side, round(image.width * scale)), max(side, round(image.height * scale))), Image.Resampling.LANCZOS)
            left, top = (image.width - side) // 2, (image.height - side) // 2
            tile = image.crop((left, top, left + side, top + side))
    draw = ImageDraw.Draw(tile)
    tw, th = px(17), px(10)
    y = side - th
    draw.rectangle((0, y - 1, tw + 1, side), fill=BG)
    draw.polygon(tag_points(1, y, tw, th - 1, th * .5), fill=STATUS_COLORS.get(status, MUTED))
    return tile
