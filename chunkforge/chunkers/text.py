"""
Text chunker for ChunkForge.

Splits plain text files into semantically coherent chunks using
paragraph boundaries and token-based splitting. Supports adaptive
chunk sizing and sliding window for overlapping chunks. Zero dependencies.
"""

import re
from collections import Counter
from typing import Any, Dict, List, Optional

from chunkforge.chunkers.base import BaseChunker, Chunk


class TextChunker(BaseChunker):
    """
    Chunker for plain text files.
    
    Uses paragraph boundaries and token-based splitting to create
    semantically coherent chunks. Supports adaptive chunk sizing based
    on content density and sliding window for overlapping chunks.
    Zero external dependencies.
    """
    
    def __init__(
        self,
        chunk_size: int = 256,
        max_chunk_size: int = 4096,
        overlap: int = 0,
        adaptive: bool = True,
    ):
        """
        Initialize text chunker.
        
        Args:
            chunk_size: Target tokens per chunk
            max_chunk_size: Maximum tokens per chunk
            overlap: Number of tokens to overlap between chunks (0 = no overlap)
            adaptive: Whether to adapt chunk size based on content density
        """
        self.chunk_size = chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
        self.adaptive = adaptive
    
    def supported_extensions(self) -> List[str]:
        """Return supported text file extensions."""
        return [
            ".txt",
            ".md",
            ".markdown",
            ".rst",
            ".adoc",
            ".log",
            ".csv",
            ".tsv",
        ]
    
    def chunk(
        self,
        content: Any,
        document_path: str,
        **kwargs: Any,
    ) -> List[Chunk]:
        """
        Split text content into chunks.
        
        Args:
            content: Text content to chunk
            document_path: Path to source document
            **kwargs: Additional options (ignored)
            
        Returns:
            List of Chunk objects
        """
        if not isinstance(content, str):
            content = str(content)
        
        # Use sliding window if overlap > 0
        if self.overlap > 0:
            return self._chunk_sliding_window(content, document_path)
        
        # Use adaptive chunking if enabled
        if self.adaptive:
            return self._chunk_adaptive(content, document_path)
        
        # Standard paragraph-based chunking
        return self._chunk_paragraphs(content, document_path)
    
    def _chunk_paragraphs(self, content: str, document_path: str) -> List[Chunk]:
        """Standard paragraph-based chunking."""
        # Split into paragraphs
        paragraphs = re.split(r'\n\s*\n', content)
        
        chunks: List[Chunk] = []
        current_text = ""
        current_start = 0
        chunk_index = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # Estimate tokens
            combined_tokens = (len(current_text) + len(para)) // 4
            
            if combined_tokens > self.chunk_size and current_text:
                # Create chunk
                chunk = Chunk(
                    content=current_text.strip(),
                    modality="text",
                    start_pos=current_start,
                    end_pos=current_start + len(current_text),
                    document_path=document_path,
                    chunk_index=chunk_index,
                )
                chunks.append(chunk)
                chunk_index += 1
                
                # Start new chunk
                current_start = current_start + len(current_text)
                current_text = para + "\n\n"
            else:
                # Add to current chunk
                if current_text:
                    current_text += para + "\n\n"
                else:
                    current_text = para + "\n\n"
        
        # Add final chunk
        if current_text.strip():
            chunk = Chunk(
                content=current_text.strip(),
                modality="text",
                start_pos=current_start,
                end_pos=current_start + len(current_text),
                document_path=document_path,
                chunk_index=chunk_index,
            )
            chunks.append(chunk)
        
        # Handle empty content
        if not chunks:
            chunks.append(Chunk(
                content="",
                modality="text",
                start_pos=0,
                end_pos=0,
                document_path=document_path,
                chunk_index=0,
            ))
        
        return chunks
    
    def _chunk_adaptive(self, content: str, document_path: str) -> List[Chunk]:
        """
        Adaptive chunking that adjusts size based on content density.
        
        Dense content (code, lists) gets smaller chunks.
        Sparse content (prose) gets larger chunks.
        """
        # Split into paragraphs
        paragraphs = re.split(r'\n\s*\n', content)
        
        chunks: List[Chunk] = []
        current_text = ""
        current_start = 0
        chunk_index = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # Calculate content density
            density = self._content_density(para)
            
            # Adjust chunk size based on density
            # High density (code, lists) → smaller chunks
            # Low density (prose) → larger chunks
            adjusted_size = int(self.chunk_size * (1.0 - density * 0.5))
            adjusted_size = max(self.chunk_size // 2, min(adjusted_size, self.max_chunk_size))
            
            # Estimate tokens
            combined_tokens = (len(current_text) + len(para)) // 4
            
            if combined_tokens > adjusted_size and current_text:
                # Create chunk
                chunk = Chunk(
                    content=current_text.strip(),
                    modality="text",
                    start_pos=current_start,
                    end_pos=current_start + len(current_text),
                    document_path=document_path,
                    chunk_index=chunk_index,
                    metadata={"density": density, "adjusted_size": adjusted_size},
                )
                chunks.append(chunk)
                chunk_index += 1
                
                # Start new chunk
                current_start = current_start + len(current_text)
                current_text = para + "\n\n"
            else:
                # Add to current chunk
                if current_text:
                    current_text += para + "\n\n"
                else:
                    current_text = para + "\n\n"
        
        # Add final chunk
        if current_text.strip():
            chunk = Chunk(
                content=current_text.strip(),
                modality="text",
                start_pos=current_start,
                end_pos=current_start + len(current_text),
                document_path=document_path,
                chunk_index=chunk_index,
            )
            chunks.append(chunk)
        
        # Handle empty content
        if not chunks:
            chunks.append(Chunk(
                content="",
                modality="text",
                start_pos=0,
                end_pos=0,
                document_path=document_path,
                chunk_index=0,
            ))
        
        return chunks
    
    def _chunk_sliding_window(self, content: str, document_path: str) -> List[Chunk]:
        """
        Sliding window chunking with overlap.
        
        Creates overlapping chunks to ensure context continuity.
        """
        # Split into sentences for better boundaries
        sentences = re.split(r'(?<=[.!?])\s+', content)
        
        chunks: List[Chunk] = []
        chunk_index = 0
        
        # Build chunks with sliding window
        i = 0
        while i < len(sentences):
            # Collect sentences for this chunk
            chunk_sentences = []
            token_count = 0
            
            while i < len(sentences) and token_count < self.chunk_size:
                sentence = sentences[i]
                sentence_tokens = len(sentence) // 4
                
                if token_count + sentence_tokens > self.max_chunk_size:
                    break
                
                chunk_sentences.append(sentence)
                token_count += sentence_tokens
                i += 1
            
            if not chunk_sentences:
                break
            
            # Create chunk
            chunk_content = " ".join(chunk_sentences)
            start_pos = content.find(chunk_sentences[0])
            end_pos = start_pos + len(chunk_content)
            
            chunk = Chunk(
                content=chunk_content,
                modality="text",
                start_pos=start_pos,
                end_pos=end_pos,
                document_path=document_path,
                chunk_index=chunk_index,
                metadata={"overlap": self.overlap, "sentence_count": len(chunk_sentences)},
            )
            chunks.append(chunk)
            chunk_index += 1
            
            # Move back for overlap
            if self.overlap > 0 and i < len(sentences):
                overlap_tokens = 0
                overlap_count = 0
                
                for j in range(len(chunk_sentences) - 1, -1, -1):
                    sentence_tokens = len(chunk_sentences[j]) // 4
                    if overlap_tokens + sentence_tokens > self.overlap:
                        break
                    overlap_tokens += sentence_tokens
                    overlap_count += 1
                
                i -= overlap_count
        
        # Handle empty content
        if not chunks:
            chunks.append(Chunk(
                content="",
                modality="text",
                start_pos=0,
                end_pos=0,
                document_path=document_path,
                chunk_index=0,
            ))
        
        return chunks
    
    def _content_density(self, text: str) -> float:
        """
        Calculate content density (0.0 = sparse prose, 1.0 = dense code/lists).
        
        High density indicators:
        - Short lines
        - Many special characters
        - Indentation
        - Bullet points or numbers
        """
        if not text:
            return 0.0
        
        lines = text.split("\n")
        if not lines:
            return 0.0
        
        # Average line length (shorter = denser)
        avg_line_length = sum(len(line) for line in lines) / len(lines)
        line_score = max(0, 1.0 - avg_line_length / 80.0)
        
        # Special character ratio
        special_chars = sum(1 for c in text if c in "{}[]()<>:=|&%$#@!~`")
        special_score = min(1.0, special_chars / max(len(text), 1) * 10)
        
        # Indentation ratio
        indented_lines = sum(1 for line in lines if line.startswith((" ", "\t")))
        indent_score = indented_lines / max(len(lines), 1)
        
        # Bullet/number ratio
        bullet_lines = sum(1 for line in lines if re.match(r'^\s*[-*•]\s', line))
        number_lines = sum(1 for line in lines if re.match(r'^\s*\d+[.)]\s', line))
        list_score = (bullet_lines + number_lines) / max(len(lines), 1)
        
        # Combine scores
        density = (line_score * 0.3 + special_score * 0.3 + indent_score * 0.2 + list_score * 0.2)
        
        return min(1.0, max(0.0, density))


class TextChunk(Chunk):
    """Text-specific chunk with enhanced semantic signature."""
    
    def _compute_semantic_signature(self, signature_dim: int = 128) -> List[float]:
        """
        Compute semantic signature for text.
        
        Uses character trigrams, word frequencies, and structural features.
        """
        signature = [0.0] * signature_dim
        
        if not isinstance(self.content, str):
            return signature
        
        text = self.content.lower()
        
        # Feature 1: Character trigram frequencies (first 64 dimensions)
        trigrams: Counter = Counter()
        for i in range(len(text) - 2):
            trigrams[text[i:i+3]] += 1
        
        for i, (trigram, count) in enumerate(trigrams.most_common(64)):
            if i >= 64:
                break
            signature[i] = count / max(len(text), 1)
        
        # Feature 2: Word frequency distribution (next 32 dimensions)
        words: Counter = Counter()
        word_list = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', text)
        for word in word_list:
            if len(word) > 2:
                words[word] += 1
        
        for i, (word, count) in enumerate(words.most_common(32)):
            if i >= 32:
                break
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
        norm = sum(x * x for x in signature) ** 0.5
        if norm > 0:
            signature = [x / norm for x in signature]
        
        return signature
    
    def _estimate_token_count(self) -> int:
        """Estimate token count for text."""
        if isinstance(self.content, str):
            return max(1, len(self.content) // 4)
        return 1
