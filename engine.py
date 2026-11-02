from dataclasses import dataclass
from pathlib import Path
from math import ceil
from PIL import Image, ImageOps, ImageFilter

RAMP = ' .,:;irsXA253hMHGS#9B&@'
MIN_COLUMNS = 16
MAX_COLUMNS = 240
MAX_FRAMES = 600
MAX_PIXELS = 32_000_000
MAX_SAMPLED_PIXELS = 500_000
MAX_FRAME_CELLS = 32_000
MAX_ROWS = 400

@dataclass(frozen=True)
class Pixels:
    data: bytes

    def __iter__(self):
        return zip(self.data[0::4], self.data[1::4], self.data[2::4], self.data[3::4])

    def __getitem__(self, index):
        start = index * 4
        return tuple(self.data[start:start + 4])

    def __len__(self):
        return len(self.data) // 4

@dataclass(frozen=True)
class Frame:
    width: int
    height: int
    pixels: Pixels
    duration: int
    levels: bytes = b''  # Enhanced ASCII tones, independent of original RGB.

@dataclass(frozen=True)
class Profile:
    width: int
    height: int
    count: int
    limit: int

@dataclass(frozen=True)
class Clip:
    frames: tuple
    loop: int | None
    columns: int
    limit: int
    requested: int
    mode: str
    cell_size: int = 0
    minimum_cell: int = 2


def luminance(rgb):
    return (2126 * rgb[0] + 7152 * rgb[1] + 722 * rgb[2]) / 10000


def glyph(rgb, invert=False):
    level = luminance(rgb) / 255
    if invert:
        level = 1 - level
    return RAMP[min(len(RAMP) - 1, int(level * (len(RAMP) - 1)))]


def dot_radius(rgb, cell, invert=False):
    darkness = 1 - luminance(rgb) / 255
    if invert:
        darkness = 1 - darkness
    return cell * .48 * darkness ** .5


def rows_for(columns, width, height, mode):
    return max(1, round(columns * height / width * (.5 if mode == 'ASCII' else 1)))


def safe_limit(width, height, count, mode):
    # Exhaustive bounded search avoids rounding errors at the budget boundary.
    for columns in range(MAX_COLUMNS, MIN_COLUMNS - 1, -1):
        rows = rows_for(columns, width, height, mode)
        cells = columns * rows
        if rows <= MAX_ROWS and cells <= (12_000 if mode == 'Voxels' else MAX_FRAME_CELLS) and cells * count <= MAX_SAMPLED_PIXELS:
            return columns
    raise ValueError('This file is too tall or too long. Crop it or shorten the GIF first.')


def inspect_source(source, mode):
    count = getattr(source, 'n_frames', 1)
    if mode not in ('ASCII', 'Halftone', 'Diamonds', 'Voxels'):
        raise ValueError('Unknown conversion mode')
    if count > MAX_FRAMES:
        raise ValueError(f'GIF exceeds {MAX_FRAMES} frames. Use a shorter GIF.')
    if source.width * source.height > MAX_PIXELS:
        raise ValueError('Image exceeds 32 megapixels. Resize it first.')
    width, height = source.size
    if source.getexif().get(274) in (5, 6, 7, 8):
        width, height = height, width
    return Profile(width, height, count, safe_limit(width, height, count, mode))


def tone_table(rgba):
    # One LUT for the whole GIF prevents frame-by-frame auto-contrast flicker.
    visible = rgba.getchannel('A').point(lambda x: 255 if x > 16 else 0)
    histogram = rgba.convert('L').histogram(mask=visible)
    total = sum(histogram)
    if not total:
        return list(range(256))
    def percentile(fraction):
        running = 0
        for value, count in enumerate(histogram):
            running += count
            if running >= total * fraction:
                return value
        return 255
    low, high = percentile(.01), percentile(.99)
    if high - low < 20:
        return list(range(256))
    gain = min(1.8, 255 / (high - low))
    midpoint = (low + high) / 2
    return [max(0, min(255, round((x - midpoint) * gain + 127.5))) for x in range(256)]


def load_clip(path: str, columns=120, mode='ASCII', *, cell_size=None, viewport=(408, 268)) -> Clip:
    requested = max(MIN_COLUMNS, min(MAX_COLUMNS, int(columns)))
    frames = []
    with Image.open(Path(path)) as source:
        profile = inspect_source(source, mode)
        actual_cell = 0
        minimum_cell = 2
        if cell_size is not None:
            # Cell size is the displayed cell width in logical screen pixels.
            display_width = min(max(1, viewport[0]), max(1, viewport[1]) * profile.width / profile.height)
            minimum_cell = max(2, ceil(display_width / profile.limit))
            actual_cell = max(minimum_cell, int(cell_size))
            requested = max(1, min(MAX_COLUMNS, int(display_width / actual_cell)))
        columns = min(requested, profile.limit)
        loop = source.info.get('loop', None) if profile.count > 1 else None
        lut = None
        for index in range(profile.count):
            source.seek(index)
            if source.width * source.height > MAX_PIXELS:
                raise ValueError('An animation frame exceeds 32 megapixels.')
            rgba = ImageOps.exif_transpose(source).convert('RGBA')
            rows = rows_for(columns, rgba.width, rgba.height, mode)
            if rows > MAX_ROWS or columns * rows > MAX_FRAME_CELLS:
                raise ValueError('Frame dimensions changed beyond the safety limit.')
            rgba = rgba.resize((columns, rows), Image.Resampling.LANCZOS)
            levels = b''
            if mode == 'ASCII':
                if lut is None:
                    lut = tone_table(rgba)
                levels = rgba.convert('L').point(lut).filter(
                    ImageFilter.UnsharpMask(radius=.65, percent=125, threshold=2)).tobytes()
            frames.append(Frame(columns, rows, Pixels(rgba.tobytes()),
                                max(20, int(source.info.get('duration', 100) or 100)), levels))
            if sum(f.width * f.height for f in frames) > MAX_SAMPLED_PIXELS:
                raise ValueError('Animation exceeds the safe sample budget.')
    return Clip(tuple(frames), loop, columns, profile.limit, requested, mode, actual_cell, minimum_cell)
