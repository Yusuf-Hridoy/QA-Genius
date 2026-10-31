"""Write public/favicon.svg and public/favicon.ico: the ✦ mark on its tile.

The tab icon is the same mark the rail shows, in the same two colours, so
a pinned tab and the page agree about what this is.

Run it when the mark or the colours change:

    python scripts/make_favicon.py

Nothing here runs at request time and nothing is installed: the .ico is
written by hand (header, BITMAPINFOHEADER, BGRA pixels, AND mask), so the
app has no image library to depend on.
"""

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"

# --cta and the ink the rail puts on it, from public/style.css.
TILE = (0xFF, 0xD1, 0x66)
MARK = (0x20, 0x2F, 0x77)

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="8" fill="#FFD166"/>
  <path d="M16 3.5c.9 5.6 2.8 8.9 6.5 10.3l3.9 1.4c.8.3.8 1.3 0 1.6l-3.9 1.4
           c-3.7 1.4-5.6 4.7-6.5 10.3-.1.8-1.2.8-1.3 0-.9-5.6-2.8-8.9-6.5-10.3
           l-3.9-1.4c-.8-.3-.8-1.3 0-1.6l3.9-1.4C12 12.4 13.8 9.1 14.7 3.5
           c.1-.8 1.2-.8 1.3 0z" fill="#202F77"/>
</svg>
"""

SIZE = 32
# Where the tile's rounded corners start, in pixels.
RADIUS = 8
# The mark is an astroid: |x|^P + |y|^P <= r^P with P under 1 gives the four
# points and the pinched waist of ✦.
POWER = 0.55
REACH = 13.5


def _in_tile(x: float, y: float) -> bool:
    """Inside the rounded square."""
    near_x = min(x, SIZE - 1 - x)
    near_y = min(y, SIZE - 1 - y)
    if near_x >= RADIUS or near_y >= RADIUS:
        return True
    away_x = RADIUS - near_x
    away_y = RADIUS - near_y
    return away_x * away_x + away_y * away_y <= RADIUS * RADIUS


def _in_mark(x: float, y: float) -> bool:
    middle = (SIZE - 1) / 2
    across = abs(x - middle)
    down = abs(y - middle)
    if across == 0 and down == 0:
        return True
    return across**POWER + down**POWER <= REACH**POWER


def _pixels() -> bytes:
    """32-bit BGRA, bottom row first, the way an icon stores them."""
    rows = []
    for y in range(SIZE - 1, -1, -1):
        row = bytearray()
        for x in range(SIZE):
            if not _in_tile(x, y):
                row += bytes((0, 0, 0, 0))
                continue
            red, green, blue = MARK if _in_mark(x, y) else TILE
            row += bytes((blue, green, red, 255))
        rows.append(bytes(row))
    return b"".join(rows)


def _mask() -> bytes:
    """The AND mask: one bit per pixel, rows padded to 4 bytes. All zero."""
    row_bytes = ((SIZE + 31) // 32) * 4
    return bytes(row_bytes * SIZE)


def ico() -> bytes:
    pixels = _pixels()
    mask = _mask()
    header = struct.pack("<HHH", 0, 1, 1)
    info = struct.pack(
        "<IiiHHIIiiII",
        40,  # header size
        SIZE,
        SIZE * 2,  # height counts the mask too
        1,  # planes
        32,  # bits per pixel
        0,  # no compression
        len(pixels) + len(mask),
        0,
        0,
        0,
        0,
    )
    image = info + pixels + mask
    entry = struct.pack(
        "<BBBBHHII", SIZE, SIZE, 0, 0, 1, 32, len(image), len(header) + 16
    )
    return header + entry + image


def main() -> None:
    (PUBLIC / "favicon.svg").write_text(SVG, encoding="utf-8")
    (PUBLIC / "favicon.ico").write_bytes(ico())
    print("wrote", PUBLIC / "favicon.svg", "and", PUBLIC / "favicon.ico")


if __name__ == "__main__":
    main()
