"""Msgpack serialization helpers."""

from __future__ import annotations

from typing import Any

import msgpack


def pack(obj: Any) -> bytes:
    """Serialize an object to msgpack bytes."""
    return msgpack.packb(obj, use_bin_type=True)


def unpack(data: bytes) -> Any:
    """Deserialize msgpack bytes to an object."""
    return msgpack.unpackb(data, raw=False)
