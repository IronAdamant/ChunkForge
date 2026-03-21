"""
Backward-compatibility shim for Stele core.

All functionality has moved to:
- stele_context.engine: Stele class
- stele_context.chunkers.base: Chunk class

This module re-exports everything so existing imports continue working:
    from stele_context.core import Stele, Chunk
"""

from stele_context.engine import Stele
from stele_context.chunkers.base import Chunk

__all__ = [
    "Stele",
    "Chunk",
]
