"""
Backward-compatibility shim for ChunkForge core.

All functionality has moved to:
- chunkforge.engine: ChunkForge class
- chunkforge.chunkers.base: Chunk class
- chunkforge.chunkers.numpy_compat: numpy helpers

This module re-exports everything so existing imports continue working:
    from chunkforge.core import ChunkForge, Chunk
"""

from chunkforge.engine import ChunkForge
from chunkforge.chunkers.base import Chunk
from chunkforge.chunkers.numpy_compat import (
    np,
    HAS_NUMPY,
    cosine_similarity as _cosine_similarity,
)

__all__ = [
    "ChunkForge",
    "Chunk",
    "_cosine_similarity",
    "np",
    "HAS_NUMPY",
]
