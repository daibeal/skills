"""Cell positions and interleaving (mirrors libcimbar CellPositions/Interleave).

The 12400 data cells are laid out in three horizontal bands, skipping the four
corner regions reserved for finder anchors, then interleaved so that
consecutive bytes of an error-correction block are spread across the image.
"""

from functools import lru_cache

from .constants import (
    CELL_SPACING, CELLS_PER_COL, CELL_OFFSET, MARKER_CELLS,
    INTERLEAVE_BLOCKS, INTERLEAVE_PARTITIONS, TOTAL_CELLS,
)


def _compute_linear():
    """Top-left pixel (x, y) of every data cell, in raster (linear) order."""
    spacing = CELL_SPACING
    dim = CELLS_PER_COL
    marker = MARKER_CELLS
    offset = CELL_OFFSET
    positions = []

    marker_offset_x = spacing * marker
    top_width = dim - marker - marker

    # top band: `marker` rows, skipping left/right corner columns
    for i in range(top_width * marker):
        x = (i % top_width) * spacing + marker_offset_x + offset
        y = (i // top_width) * spacing + offset
        positions.append((x, y))

    # middle band: full width, `dim - 2*marker` rows
    mid_y = marker * spacing
    mid_height = dim - marker - marker
    for i in range(dim * mid_height):
        x = (i % dim) * spacing + offset
        y = (i // dim) * spacing + mid_y + offset
        positions.append((x, y))

    # bottom band: `marker` rows, skipping corner columns
    bottom_y = (dim - marker) * spacing
    for i in range(top_width * marker):
        x = (i % top_width) * spacing + marker_offset_x + offset
        y = (i // top_width) * spacing + bottom_y + offset
        positions.append((x, y))

    return positions


def interleave_indices(size, num_chunks, partitions):
    """Permutation used to spread adjacent cells across the image."""
    if num_chunks == 0:
        return list(range(size))
    indices = []
    partition_size = size // partitions
    for part in range(0, size, partition_size):
        for chunk in range(num_chunks):
            for i in range(chunk, partition_size, num_chunks):
                indices.append(i + part)
    return indices


@lru_cache(maxsize=1)
def cell_positions():
    """Interleaved (x, y) pixel positions; encode and decode iterate this order."""
    linear = _compute_linear()
    idx = interleave_indices(len(linear), INTERLEAVE_BLOCKS, INTERLEAVE_PARTITIONS)
    return [linear[i] for i in idx]


# sanity checks at import
_pos = cell_positions()
assert len(_pos) == TOTAL_CELLS, (len(_pos), TOTAL_CELLS)
assert len(set(_pos)) == TOTAL_CELLS, "cell positions must be unique"
