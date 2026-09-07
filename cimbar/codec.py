"""Frame codec: map an RS-encoded byte buffer to a cimbar image and back.

A frame holds ``CAPACITY`` (9300) bytes across ``TOTAL_CELLS`` (12400) cells,
6 bits per cell (4 symbol bits + 2 color bits).
"""

import numpy as np
from PIL import Image

from .constants import (
    IMAGE_SIZE, CELL_SIZE, CAPACITY, TOTAL_CELLS, BITS_PER_CELL,
    NUM_SYMBOLS, ANCHOR_SIZE, SYMBOLS,
)
from .grid import cell_positions
from .tiles import TILES, _COLORS

_POS = cell_positions()
_WEIGHTS = np.array([32, 16, 8, 4, 2, 1], dtype=np.uint16)  # 6-bit MSB-first
# big-endian bytes, to match np.packbits output when Hamming-comparing hashes
_SYM_BYTES = np.array([np.frombuffer(s.to_bytes(8, "big"), np.uint8) for s in SYMBOLS])
_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint16)


def _draw_anchor(arr, x0, y0, secondary=False):
    """Draw a simple bullseye finder pattern (white on black)."""
    s = ANCHOR_SIZE
    white = np.array([255, 255, 255], dtype=np.uint8)
    arr[y0:y0 + s, x0:x0 + s] = white
    arr[y0 + 3:y0 + s - 3, x0 + 3:x0 + s - 3] = 0
    if secondary:
        # solid center dot marks the bottom-right (orientation) corner
        arr[y0 + 9:y0 + s - 9, x0 + 9:x0 + s - 9] = white
    else:
        arr[y0 + 6:y0 + s - 6, x0 + 6:x0 + s - 6] = white


def render_frame(buf):
    """Render a ``CAPACITY``-byte buffer to a 1024x1024 RGB :class:`PIL.Image`."""
    if len(buf) != CAPACITY:
        raise ValueError("buffer must be exactly %d bytes" % CAPACITY)

    bits = np.unpackbits(np.frombuffer(buf, dtype=np.uint8))  # (74400,)
    vals = (bits.reshape(TOTAL_CELLS, BITS_PER_CELL) * _WEIGHTS).sum(axis=1)
    symbols = (vals & 0x0F).astype(np.int64)
    colors = ((vals >> 4) & 0x03).astype(np.int64)

    arr = np.zeros((IMAGE_SIZE, IMAGE_SIZE, 3), dtype=np.uint8)
    a = ANCHOR_SIZE
    _draw_anchor(arr, 0, 0)
    _draw_anchor(arr, 0, IMAGE_SIZE - a)
    _draw_anchor(arr, IMAGE_SIZE - a, 0)
    _draw_anchor(arr, IMAGE_SIZE - a, IMAGE_SIZE - a, secondary=True)

    for k in range(TOTAL_CELLS):
        x, y = _POS[k]
        arr[y:y + CELL_SIZE, x:x + CELL_SIZE] = TILES[symbols[k], colors[k]]

    return Image.fromarray(arr, "RGB")


def read_frame(image):
    """Read a cimbar image back to a ``CAPACITY``-byte buffer (pre-ECC).

    ``image`` may be a path, a :class:`PIL.Image`, or a numpy array. Non-1024
    images are resized (best-effort for clean scans / screenshots).
    """
    if isinstance(image, str):
        image = Image.open(image)
    if isinstance(image, Image.Image):
        if image.mode != "RGB":
            image = image.convert("RGB")
        if image.size != (IMAGE_SIZE, IMAGE_SIZE):
            image = image.resize((IMAGE_SIZE, IMAGE_SIZE), Image.BILINEAR)
        arr = np.asarray(image, dtype=np.uint8)
    else:
        arr = np.asarray(image, dtype=np.uint8)

    # gather every cell into (N, 8, 8, 3)
    cells = np.empty((TOTAL_CELLS, CELL_SIZE, CELL_SIZE, 3), dtype=np.float32)
    for k in range(TOTAL_CELLS):
        x, y = _POS[k]
        cells[k] = arr[y:y + CELL_SIZE, x:x + CELL_SIZE]

    gray = cells[..., 0] * 0.299 + cells[..., 1] * 0.587 + cells[..., 2] * 0.114
    means = gray.reshape(TOTAL_CELLS, -1).mean(axis=1)[:, None, None]
    fgmask = gray > means  # (N, 8, 8)

    # --- symbol: average-hash -> nearest by Hamming ---
    hbits = fgmask.reshape(TOTAL_CELLS, 64).astype(np.uint8)
    hbytes = np.packbits(hbits, axis=1)  # (N, 8), MSB-first per byte
    # distance to each of 16 symbols
    xor = hbytes[:, None, :] ^ _SYM_BYTES[None, :, :]      # (N, 16, 8)
    dist = _POPCOUNT[xor].sum(axis=2)                       # (N, 16)
    symbols = dist.argmin(axis=1).astype(np.int64)

    # --- color: mean of foreground pixels -> nearest palette ---
    m = fgmask[..., None].astype(np.float32)
    counts = fgmask.reshape(TOTAL_CELLS, -1).sum(axis=1)
    counts = np.where(counts == 0, 1, counts)[:, None]
    fg_rgb = (cells * m).sum(axis=(1, 2)) / counts          # (N, 3)
    cdiff = ((fg_rgb[:, None, :] - _COLORS.astype(np.float32)[None, :, :]) ** 2).sum(axis=2)
    colors = cdiff.argmin(axis=1).astype(np.int64)

    # --- pack back to bytes ---
    vals = ((colors & 0x03) << 4) | (symbols & 0x0F)        # (N,) 6-bit values
    cellbits = np.zeros((TOTAL_CELLS, BITS_PER_CELL), dtype=np.uint8)
    for b in range(BITS_PER_CELL):
        cellbits[:, b] = (vals >> (BITS_PER_CELL - 1 - b)) & 1
    flat = cellbits.reshape(-1)
    return np.packbits(flat).tobytes()
