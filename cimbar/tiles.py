"""Tile rendering and symbol/color matching.

Foreground pixels of each 8x8 symbol are drawn in the chosen color on a black
background. Decoding recovers the symbol via an 8x8 average-hash (mean-threshold
+ Hamming distance) and the color via nearest-palette on the foreground pixels.
"""

import numpy as np

from .constants import (
    CELL_SIZE, NUM_SYMBOLS, NUM_COLORS, SYMBOLS, COLORS,
)

# Foreground bit masks: FG[sym][r, c] is True where the symbol is drawn.
FG = np.zeros((NUM_SYMBOLS, CELL_SIZE, CELL_SIZE), dtype=bool)
for _s, _bits in enumerate(SYMBOLS):
    for _r in range(CELL_SIZE):
        for _c in range(CELL_SIZE):
            _bit = (_bits >> (63 - (_r * CELL_SIZE + _c))) & 1
            FG[_s, _r, _c] = bool(_bit)

# Prerendered tiles: TILES[sym, color] -> (8, 8, 3) uint8
_COLORS = np.array(COLORS, dtype=np.uint8)
TILES = np.zeros((NUM_SYMBOLS, NUM_COLORS, CELL_SIZE, CELL_SIZE, 3), dtype=np.uint8)
for _s in range(NUM_SYMBOLS):
    for _k in range(NUM_COLORS):
        TILES[_s, _k][FG[_s]] = _COLORS[_k]

# Reference symbol hashes. Because a rendered foreground pixel is always brighter
# than the black background, the mean-threshold average-hash of a rendered tile
# equals its foreground bit pattern -- i.e. the SYMBOLS constants themselves.
_SYM_HASHES = np.array(SYMBOLS, dtype=np.uint64)


def _ahash(gray_cell):
    """8x8 grayscale cell -> 64-bit average hash (mean threshold, MSB=top-left)."""
    thresh = gray_cell.mean()
    bits = 0
    flat = (gray_cell > thresh).reshape(-1)
    for b in flat:
        bits = (bits << 1) | int(b)
    return bits


_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def _hamming64(a, b):
    x = int(a) ^ int(b)
    return _POPCOUNT[[(x >> s) & 0xFF for s in (0, 8, 16, 24, 32, 40, 48, 56)]].sum()


def decode_cell(cell_rgb):
    """Decode one 8x8 RGB cell -> (symbol, color).

    ``cell_rgb`` is an (8, 8, 3) uint8/float array.
    """
    cell = cell_rgb.astype(np.float32)
    gray = cell[:, :, 0] * 0.299 + cell[:, :, 1] * 0.587 + cell[:, :, 2] * 0.114

    # symbol: nearest average-hash by Hamming distance
    h = _ahash(gray)
    best_sym = 0
    best_dist = 65
    for s in range(NUM_SYMBOLS):
        d = _hamming64(h, int(_SYM_HASHES[s]))
        if d < best_dist:
            best_dist = d
            best_sym = s

    # color: average the foreground pixels, then nearest palette color
    mask = gray > gray.mean()
    if mask.any():
        fg_rgb = cell[mask].mean(axis=0)
    else:
        fg_rgb = cell.reshape(-1, 3).mean(axis=0)
    diffs = ((_COLORS.astype(np.float32) - fg_rgb) ** 2).sum(axis=1)
    best_color = int(diffs.argmin())

    return best_sym, best_color
