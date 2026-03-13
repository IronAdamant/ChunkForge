"""
Base chunker interface for ChunkForge.

All modality-specific chunkers inherit from BaseChunker and implement
the chunk() method to split content into semantically coherent units.
"""

import hashlib
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from chunkforge.chunkers.numpy_compat import (
    np,
    HAS_NUMPY,
    cosine_similarity,
)


@dataclass
class Chunk:
    """
    Represents a chunk of content with metadata.

    A chunk is a semantically coherent unit that can be independently
    indexed, cached, and restored. Works for any modality (text, image, etc.)
    """

    # Content
    content: Any  # str for text, bytes for binary
    modality: str  # "text", "image", "audio", "video", "pdf"

    # Position in source
    start_pos: int = 0
    end_pos: int = 0

    # Source info
    document_path: str = ""
    chunk_index: int = 0

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Computed properties (lazy)
    _content_hash: Optional[str] = field(default=None, repr=False)
    _semantic_signature: Optional[Any] = field(default=None, repr=False)
    _token_count: Optional[int] = field(default=None, repr=False)
    _chunk_id: Optional[str] = field(default=None, repr=False)

    @property
    def content_hash(self) -> str:
        """SHA-256 hash of chunk content."""
        if self._content_hash is None:
            if isinstance(self.content, str):
                self._content_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
            elif isinstance(self.content, bytes):
                self._content_hash = hashlib.sha256(self.content).hexdigest()
            else:
                self._content_hash = hashlib.sha256(str(self.content).encode("utf-8")).hexdigest()
        return self._content_hash

    @property
    def semantic_signature(self) -> Any:
        """
        Semantic signature for similarity comparison.

        Returns a 128-dim vector using character trigrams, word frequencies,
        and structural features.
        """
        if self._semantic_signature is None:
            self._semantic_signature = self._compute_semantic_signature()
        return self._semantic_signature

    @property
    def token_count(self) -> int:
        """Estimated token count."""
        if self._token_count is None:
            self._token_count = self._estimate_token_count()
        return self._token_count

    @property
    def chunk_id(self) -> str:
        """Unique identifier for this chunk."""
        if self._chunk_id is None:
            id_string = f"{self.document_path}:{self.start_pos}:{self.end_pos}:{self.content_hash[:16]}"
            self._chunk_id = hashlib.sha256(id_string.encode("utf-8")).hexdigest()[:32]
        return self._chunk_id

    def _compute_semantic_signature(self, signature_dim: int = 128) -> Any:
        """
        Compute a rich 128-dim semantic signature using TF-style features.

        Uses character trigrams (64 dims), word frequencies (32 dims),
        and structural features (32 dims).
        """
        if not isinstance(self.content, str):
            # For binary content, pad hash-based signature to full dimension
            hash_vals = [float(ord(c)) / 255.0 for c in self.content_hash[:64]]
            return hash_vals + [0.0] * (signature_dim - len(hash_vals))

        signature = np.zeros(signature_dim, dtype=np.float32)

        # Feature 1: Character trigram frequencies (first 64 dimensions)
        trigrams = self._extract_trigrams()
        for i, (_, count) in enumerate(trigrams.most_common(64)):
            signature[i] = count / max(len(self.content), 1)

        # Feature 2: Word frequency distribution (next 32 dimensions)
        words = self._extract_words()
        for i, (_, count) in enumerate(words.most_common(32)):
            signature[64 + i] = count / max(len(words), 1)

        # Feature 3: Structural features (next 32 dimensions)
        lines = self.content.split("\n")
        signature[96] = len(lines) / 100.0
        signature[97] = sum(len(line) for line in lines) / max(len(self.content), 1)
        signature[98] = sum(1 for line in lines if line.strip().startswith("#")) / max(len(lines), 1)
        signature[99] = sum(1 for line in lines if line.strip().startswith("def ")) / max(len(lines), 1)
        signature[100] = sum(1 for line in lines if line.strip().startswith("class ")) / max(len(lines), 1)
        signature[101] = self.content.count("(") / max(len(self.content), 1)
        signature[102] = self.content.count("{") / max(len(self.content), 1)
        signature[103] = self.content.count("[") / max(len(self.content), 1)

        # Normalize to unit vector
        norm = np.linalg.norm(signature)
        if norm > 0:
            if HAS_NUMPY:
                signature = signature / norm
            else:
                signature = [x / norm for x in signature]

        return signature

    def _extract_trigrams(self) -> Counter:
        """Extract character trigrams from content."""
        text = self.content.lower()
        trigrams: Counter = Counter()
        for i in range(len(text) - 2):
            trigrams[text[i:i + 3]] += 1
        return trigrams

    def _extract_words(self) -> Counter:
        """Extract word frequencies from content."""
        word_list = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', self.content.lower())
        return Counter(w for w in word_list if len(w) > 2)

    def _estimate_token_count(self) -> int:
        """Estimate token count."""
        if isinstance(self.content, (str, bytes)):
            return max(1, len(self.content) // 4)
        return 1

    def similarity(self, other: "Chunk") -> float:
        """Compute cosine similarity with another chunk."""
        return cosine_similarity(self.semantic_signature, other.semantic_signature)


class BaseChunker(ABC):
    """
    Abstract base class for modality-specific chunkers.

    All chunkers must implement:
    - chunk(): Split content into chunks
    - supported_extensions(): Return list of supported file extensions
    """

    @abstractmethod
    def chunk(
        self,
        content: Any,
        document_path: str,
        **kwargs: Any,
    ) -> List[Chunk]:
        """Split content into chunks."""
        pass

    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """Return list of supported file extensions."""
        pass

    def can_handle(self, file_path: str) -> bool:
        """Check if this chunker can handle a file."""
        ext = Path(file_path).suffix.lower()
        return ext in self.supported_extensions()
