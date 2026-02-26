"""Peer ID generation utilities."""

from __future__ import annotations

import os
import struct


def generate_peer_id() -> int:
    """Generate a random 64-bit unsigned peer ID."""
    return struct.unpack("!Q", os.urandom(8))[0]
