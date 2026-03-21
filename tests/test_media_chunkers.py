"""Tests for media chunkers: ImageChunker, PDFChunker, AudioChunker, VideoChunker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from stele_context.chunkers.base import BaseChunker, Chunk
from stele_context.chunkers import (
    HAS_IMAGE_CHUNKER,
    HAS_PDF_CHUNKER,
    HAS_AUDIO_CHUNKER,
    HAS_VIDEO_CHUNKER,
)
from stele_context.chunkers.image import ImageChunker, HAS_PIL
from stele_context.chunkers.pdf import PDFChunker, HAS_PYMUPDF
from stele_context.chunkers.audio import AudioChunker, HAS_LIBROSA
from stele_context.chunkers.video import VideoChunker, HAS_OPENCV


class TestHasFlags:
    def test_image_flag_matches_module(self):
        assert HAS_IMAGE_CHUNKER == HAS_PIL

    def test_pdf_flag_matches_module(self):
        assert HAS_PDF_CHUNKER == HAS_PYMUPDF

    def test_audio_flag_matches_module(self):
        assert HAS_AUDIO_CHUNKER == HAS_LIBROSA

    def test_video_flag_matches_module(self):
        assert HAS_VIDEO_CHUNKER == HAS_OPENCV

    def test_flags_are_bool(self):
        for flag in (
            HAS_IMAGE_CHUNKER,
            HAS_PDF_CHUNKER,
            HAS_AUDIO_CHUNKER,
            HAS_VIDEO_CHUNKER,
        ):
            assert isinstance(flag, bool)


def _bypass(cls, **attrs):
    """Instantiate a chunker subclass without calling __init__."""
    obj = cls.__new__(cls)
    obj.__dict__.update(attrs)
    return obj


class TestImageChunker:
    EXPECTED = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".tiff",
        ".tif",
        ".ico",
    }

    def _make(self):
        return _bypass(ImageChunker, tile_size=None, max_dimension=2048)

    def test_supported_extensions(self):
        assert set(self._make().supported_extensions()) == self.EXPECTED

    def test_can_handle_positive(self):
        c = self._make()
        for ext in self.EXPECTED:
            assert c.can_handle(f"file{ext}") is True

    def test_can_handle_negative(self):
        c = self._make()
        assert c.can_handle("file.mp4") is False
        assert c.can_handle("file.pdf") is False

    def test_constructor_raises_without_pil(self):
        with patch("stele_context.chunkers.image.HAS_PIL", False):
            with pytest.raises(ImportError, match="Pillow"):
                ImageChunker()


class TestPDFChunker:
    def _make(self):
        return _bypass(
            PDFChunker, chunk_size=256, max_chunk_size=4096, pages_per_chunk=1
        )

    def test_supported_extensions(self):
        assert self._make().supported_extensions() == [".pdf"]

    def test_can_handle_positive(self):
        assert self._make().can_handle("report.pdf") is True

    def test_can_handle_negative(self):
        c = self._make()
        assert c.can_handle("report.docx") is False
        assert c.can_handle("image.png") is False

    def test_constructor_raises_without_pymupdf(self):
        with patch("stele_context.chunkers.pdf.HAS_PYMUPDF", False):
            with pytest.raises(ImportError, match="pymupdf"):
                PDFChunker()

    def test_chunk_by_pages_produces_valid_chunks(self):
        mock_doc = MagicMock()
        mock_doc.page_count = 2
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Page text.\n"
        mock_doc.__getitem__ = lambda self, i: mock_page
        meta = {"title": "T", "author": "A", "page_count": 2}

        chunker = self._make()
        chunks = chunker._chunk_by_pages(mock_doc, "report.pdf", meta)

        assert len(chunks) >= 1
        for c in chunks:
            assert isinstance(c, Chunk)
            assert c.modality == "pdf"
            assert c.document_path == "report.pdf"


class TestAudioChunker:
    EXPECTED = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma"}

    def _make(self):
        return _bypass(
            AudioChunker, segment_duration=30.0, sample_rate=22050, n_mfcc=13
        )

    def test_supported_extensions(self):
        assert set(self._make().supported_extensions()) == self.EXPECTED

    def test_can_handle_positive(self):
        c = self._make()
        for ext in self.EXPECTED:
            assert c.can_handle(f"track{ext}") is True

    def test_can_handle_negative(self):
        c = self._make()
        assert c.can_handle("track.mp4") is False
        assert c.can_handle("track.txt") is False

    def test_constructor_raises_without_librosa(self):
        with patch("stele_context.chunkers.audio.HAS_LIBROSA", False):
            with pytest.raises(ImportError, match="librosa"):
                AudioChunker()


class TestVideoChunker:
    EXPECTED = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}

    def _make(self):
        return _bypass(
            VideoChunker,
            segment_duration=10.0,
            keyframe_interval=1.0,
            max_dimension=640,
        )

    def test_supported_extensions(self):
        assert set(self._make().supported_extensions()) == self.EXPECTED

    def test_can_handle_positive(self):
        c = self._make()
        for ext in self.EXPECTED:
            assert c.can_handle(f"clip{ext}") is True

    def test_can_handle_negative(self):
        c = self._make()
        assert c.can_handle("clip.mp3") is False
        assert c.can_handle("clip.png") is False

    def test_constructor_raises_without_opencv(self):
        with patch("stele_context.chunkers.video.HAS_OPENCV", False):
            with pytest.raises(ImportError, match="opencv"):
                VideoChunker()

    def test_empty_video_chunk_is_valid(self):
        chunks = VideoChunker._empty_video_chunk(
            "clip.mp4", width=640, height=480, duration=5.0
        )
        assert len(chunks) == 1
        c = chunks[0]
        assert isinstance(c, Chunk)
        assert c.modality == "video"
        assert c.content == b""
        assert c.document_path == "clip.mp4"
        assert c.metadata["width"] == 640


class TestDetectModality:
    def _make_chunkers(self):
        from stele_context.chunkers.text import TextChunker
        from stele_context.chunkers.code import CodeChunker

        def mock_chunker(exts):
            m = MagicMock(spec=BaseChunker)
            m.supported_extensions.return_value = exts
            return m

        return {
            "text": TextChunker(),
            "code": CodeChunker(),
            "image": mock_chunker(
                [
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".webp",
                    ".bmp",
                    ".tiff",
                    ".tif",
                    ".ico",
                ]
            ),
            "pdf": mock_chunker([".pdf"]),
            "audio": mock_chunker(
                [".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma"]
            ),
            "video": mock_chunker(
                [".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"]
            ),
        }

    def _detect(self, path):
        from stele_context.indexing import detect_modality

        return detect_modality(path, self._make_chunkers())

    def test_routes_image(self):
        assert self._detect("photo.png") == "image"
        assert self._detect("photo.jpg") == "image"

    def test_routes_pdf(self):
        assert self._detect("report.pdf") == "pdf"

    def test_routes_audio(self):
        assert self._detect("track.mp3") == "audio"
        assert self._detect("track.wav") == "audio"

    def test_routes_video(self):
        assert self._detect("clip.mp4") == "video"
        assert self._detect("clip.mkv") == "video"

    def test_routes_code(self):
        assert self._detect("main.py") == "code"
        assert self._detect("app.js") == "code"

    def test_routes_text(self):
        assert self._detect("README.md") == "text"
        assert self._detect("notes.txt") == "text"

    def test_routes_unknown(self):
        assert self._detect("archive.xyz") == "unknown"
