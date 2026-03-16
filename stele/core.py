"""
Backward-compatibility shim for Stele core.

All functionality has moved to:
- stele.engine: Stele class
- stele.chunkers.base: Chunk class

This module re-exports everything so existing imports continue working:
    from stele.core import Stele, Chunk
"""

from stele.engine import Stele
from stele.chunkers.base import Chunk

__all__ = [
    "Stele",
    "Chunk",
]
