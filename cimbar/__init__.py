"""cimbar: a pure-Python implementation of libcimbar-style color barcodes.

Encode a file into a series of high-density color-tile barcode images and
decode them back, with Reed-Solomon error correction. Clean-room and
self-consistent (this encoder <-> this decoder); the visual format mirrors
sz3's libcimbar mode B (https://github.com/sz3/libcimbar).
"""

from .protocol import encode, decode, Decoder
from .codec import render_frame, read_frame
from . import constants

__all__ = ["encode", "decode", "Decoder", "render_frame", "read_frame", "constants"]
__version__ = "0.1.0"
