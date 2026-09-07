"""File <-> frame protocol.

Minimal, robust scheme: the file is zlib-compressed, wrapped in a small
self-describing container, split into fixed-size chunks, and each chunk is
placed in one cimbar frame (with a per-frame header and Reed-Solomon ECC).

Frames may be decoded in any order; every frame must be received to
reconstruct the file. Bit/tile errors within a frame are corrected by ECC.
"""

import struct
import zlib

from .constants import PAYLOAD_SIZE, CAPACITY
from .galois import encode_payload, decode_payload
from .codec import render_frame, read_frame

# container header: magic, version, flags, name_len, name, orig_size, orig_crc32
_CONTAINER_MAGIC = b"CMBR"
_CONTAINER_FMT = ">4sBBH"          # magic, version, flags, name_len
_CONTAINER_TAIL_FMT = ">QI"        # orig_size, orig_crc32
_FLAG_ZLIB = 0x01

# per-frame header: magic, version, index, total, chunk_len, reserved
_FRAME_MAGIC = b"CB"
_FRAME_FMT = ">2sBHHHB"
FRAME_HEADER = struct.calcsize(_FRAME_FMT)     # 10
CHUNK_MAX = PAYLOAD_SIZE - FRAME_HEADER        # 7490


def _build_container(data, name):
    name_b = name.encode("utf-8")
    if len(name_b) > 0xFFFF:
        name_b = name_b[:0xFFFF]
    comp = zlib.compress(data, 9)
    if len(comp) < len(data):
        flags, body = _FLAG_ZLIB, comp
    else:
        flags, body = 0, data
    head = struct.pack(_CONTAINER_FMT, _CONTAINER_MAGIC, 1, flags, len(name_b))
    head += name_b + struct.pack(_CONTAINER_TAIL_FMT, len(data), zlib.crc32(data) & 0xFFFFFFFF)
    return head + body


def _parse_container(container):
    magic, version, flags, name_len = struct.unpack_from(_CONTAINER_FMT, container, 0)
    if magic != _CONTAINER_MAGIC:
        raise ValueError("bad container magic")
    off = struct.calcsize(_CONTAINER_FMT)
    name = container[off:off + name_len].decode("utf-8", "replace")
    off += name_len
    orig_size, orig_crc = struct.unpack_from(_CONTAINER_TAIL_FMT, container, off)
    off += struct.calcsize(_CONTAINER_TAIL_FMT)
    body = container[off:]
    data = zlib.decompress(body) if (flags & _FLAG_ZLIB) else body
    data = data[:orig_size]
    if len(data) != orig_size:
        raise ValueError("size mismatch after decompress")
    if (zlib.crc32(data) & 0xFFFFFFFF) != orig_crc:
        raise ValueError("CRC mismatch: data corrupted")
    return name, data


def encode(data, name="data.bin"):
    """Encode bytes -> list of frame :class:`PIL.Image` objects."""
    container = _build_container(data, name)
    total = max(1, -(-len(container) // CHUNK_MAX))  # ceil
    frames = []
    for i in range(total):
        chunk = container[i * CHUNK_MAX:(i + 1) * CHUNK_MAX]
        header = struct.pack(_FRAME_FMT, _FRAME_MAGIC, 1, i, total, len(chunk), 0)
        payload = header + chunk
        payload += b"\x00" * (PAYLOAD_SIZE - len(payload))
        buf = encode_payload(payload)
        assert len(buf) == CAPACITY
        frames.append(render_frame(buf))
    return frames


class Decoder:
    """Accumulates frames (any order) and reconstructs the file."""

    def __init__(self):
        self.chunks = {}
        self.total = None
        self.errors_corrected = 0
        self.frames_read = 0
        self.frames_failed = 0

    def add(self, image):
        """Feed one frame image/path. Returns True if the file is complete."""
        self.frames_read += 1
        buf = read_frame(image)
        payload, bad = decode_payload(buf)
        if 0 in bad:  # header block unreadable
            self.frames_failed += 1
            return self.complete()
        try:
            magic, ver, idx, total, clen, _ = struct.unpack_from(_FRAME_FMT, payload, 0)
        except struct.error:
            self.frames_failed += 1
            return self.complete()
        if magic != _FRAME_MAGIC or clen > CHUNK_MAX:
            self.frames_failed += 1
            return self.complete()
        self.total = total
        self.chunks[idx] = payload[FRAME_HEADER:FRAME_HEADER + clen]
        return self.complete()

    def complete(self):
        return self.total is not None and len(self.chunks) >= self.total

    def missing(self):
        if self.total is None:
            return None
        return [i for i in range(self.total) if i not in self.chunks]

    def result(self):
        """Return (name, data). Raises if frames are missing or data is bad."""
        if not self.complete():
            raise ValueError("incomplete: missing frames %r" % (self.missing(),))
        container = b"".join(self.chunks[i] for i in range(self.total))
        return _parse_container(container)


def decode(images):
    """Decode an iterable of frame images/paths -> (name, data)."""
    dec = Decoder()
    for im in images:
        if dec.add(im):
            break
    return dec.result()
