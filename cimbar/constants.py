"""Format constants for the pure-Python cimbar codec.

These mirror libcimbar's default *mode B* configuration (``Conf8x8``):
a 1024x1024 image, 8x8 pixel tiles, a 112x112 cell grid with the four
corners reserved for finder/anchor patterns, 16 symbol tiles (4 bits) and
4 colors (2 bits) for 6 bits per cell, and Reed-Solomon error correction
of 30 parity bytes over 155-byte blocks (125 data bytes each).

Reference: https://github.com/sz3/libcimbar (see DETAILS.md / GridConf.h).
"""

# ---------------------------------------------------------------------------
# Image geometry (libcimbar Conf8x8)
# ---------------------------------------------------------------------------
IMAGE_SIZE = 1024          # square image, pixels
CELL_SIZE = 8              # tile is CELL_SIZE x CELL_SIZE pixels
CELL_SPACING = 9           # cell_size + 1 px gap
CELL_OFFSET = 8            # margin before the first cell
CELLS_PER_COL = 112        # cells across / down
MARKER_CELLS = 6           # corner_padding == round(54 / cell_spacing) == 6
ANCHOR_SIZE = 30           # finder-pattern size in pixels

# ---------------------------------------------------------------------------
# Symbol / color capacity
# ---------------------------------------------------------------------------
SYMBOL_BITS = 4            # 16 tiles
COLOR_BITS = 2             # 4 colors
BITS_PER_CELL = SYMBOL_BITS + COLOR_BITS  # 6

NUM_SYMBOLS = 1 << SYMBOL_BITS   # 16
NUM_COLORS = 1 << COLOR_BITS     # 4

# 112*112 - (6*6) per corner * 4 corners = 12544 - 144 = 12400
TOTAL_CELLS = CELLS_PER_COL * CELLS_PER_COL - (MARKER_CELLS * MARKER_CELLS * 4)

# ---------------------------------------------------------------------------
# Reed-Solomon error correction
# ---------------------------------------------------------------------------
ECC_BYTES = 30             # parity bytes per block
ECC_BLOCK_SIZE = 155       # total block size (data + parity)
DATA_PER_BLOCK = ECC_BLOCK_SIZE - ECC_BYTES  # 125

# Cell capacity in bytes (with parity) == 12400 * 6 / 8 == 9300
CAPACITY = TOTAL_CELLS * BITS_PER_CELL // 8
NUM_BLOCKS = CAPACITY // ECC_BLOCK_SIZE          # 60
# Usable data bytes per frame (after ECC) == 60 * 125 == 7500
PAYLOAD_SIZE = NUM_BLOCKS * DATA_PER_BLOCK

# ---------------------------------------------------------------------------
# Interleave (spread ECC blocks across the image against burst errors)
# ---------------------------------------------------------------------------
INTERLEAVE_BLOCKS = ECC_BLOCK_SIZE  # 155
INTERLEAVE_PARTITIONS = 2

# ---------------------------------------------------------------------------
# Colors (libcimbar getColor4, color_mode 1). Foreground colors on black bg.
# RGB tuples.
# ---------------------------------------------------------------------------
COLORS = (
    (0x00, 0xFF, 0x00),   # 0 green
    (0x00, 0xFF, 0xFF),   # 1 cyan
    (0xFF, 0xFF, 0x00),   # 2 yellow
    (0xFF, 0x00, 0xFF),   # 3 magenta
)
BACKGROUND = (0, 0, 0)    # dark mode background

# ---------------------------------------------------------------------------
# The 16 symbol tiles, extracted verbatim from libcimbar bitmap/4/*.png.
# Each value is a 64-bit integer: 8 rows of 8 bits, row-major, MSB = leftmost
# pixel of the top row. A set bit is a foreground pixel.
# ---------------------------------------------------------------------------
SYMBOLS = (
    0xfffefcf8f0e0c080, 0x80c0e0f0f8fcfeff, 0xff7f3f1f0f070301, 0x0103070f1f3f7fff,
    0x181818ffff181818, 0x66e7e70000e7e766, 0x3c7ee7c3c3e77e3c, 0x18183c3c7e7effff,
    0xc0f0fcfffffcf0c0, 0xfffcf00000f0fcff, 0xff3f0f00000f3fff, 0xe7e7e7e7c3c38181,
    0x8181c3c3e7e7e7e7, 0x0000c3e77e3c1800, 0x0c1c387070381c0c, 0x1e1e38381c1c7878,
)

assert len(SYMBOLS) == NUM_SYMBOLS
assert len(COLORS) == NUM_COLORS
assert TOTAL_CELLS == 12400
assert CAPACITY == 9300
assert PAYLOAD_SIZE == 7500
