"""Reed-Solomon error correction.

Thin wrapper over the pure-Python ``reedsolo`` package, using the same block
framing as libcimbar's default mode: 155-byte blocks with 30 parity bytes,
i.e. 125 data bytes protected per block, correcting up to 15 byte-errors.
"""

from reedsolo import RSCodec, ReedSolomonError

from .constants import ECC_BYTES, ECC_BLOCK_SIZE, DATA_PER_BLOCK

_rsc = RSCodec(ECC_BYTES, nsize=ECC_BLOCK_SIZE)


class RSError(Exception):
    """Raised when a block cannot be corrected."""


def rs_encode_block(data):
    """Encode up to ``DATA_PER_BLOCK`` bytes into an ``ECC_BLOCK_SIZE`` block."""
    if len(data) > DATA_PER_BLOCK:
        raise ValueError("block data too long")
    # pad short final blocks so every codeword is full-size and self-describing
    if len(data) < DATA_PER_BLOCK:
        data = bytes(data) + b"\x00" * (DATA_PER_BLOCK - len(data))
    return bytes(_rsc.encode(bytes(data)))


def rs_decode_block(block):
    """Decode one ``ECC_BLOCK_SIZE`` codeword back to ``DATA_PER_BLOCK`` bytes."""
    try:
        decoded, _, _ = _rsc.decode(bytes(block))
    except ReedSolomonError as exc:  # pragma: no cover - error path
        raise RSError(str(exc)) from exc
    return bytes(decoded)


def encode_payload(payload):
    """RS-encode a full frame payload (multiple blocks) -> cell-capacity bytes."""
    out = bytearray()
    for i in range(0, len(payload), DATA_PER_BLOCK):
        out += rs_encode_block(payload[i:i + DATA_PER_BLOCK])
    return bytes(out)


def decode_payload(buf):
    """RS-decode cell-capacity bytes -> frame payload.

    Blocks that cannot be corrected are replaced with zeros and their indices
    returned, so the caller can decide whether the frame is usable.
    """
    out = bytearray()
    bad_blocks = []
    for bi, i in enumerate(range(0, len(buf), ECC_BLOCK_SIZE)):
        block = buf[i:i + ECC_BLOCK_SIZE]
        try:
            out += rs_decode_block(block)
        except RSError:
            out += b"\x00" * DATA_PER_BLOCK
            bad_blocks.append(bi)
    return bytes(out), bad_blocks
