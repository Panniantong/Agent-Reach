# -*- coding: utf-8 -*-
"""PDF Reader — download and extract text from academic papers.

Supports:
  - Downloading PDFs from arXiv, Semantic Scholar, and direct URLs
  - Text extraction using PyMuPDF (fitz) with fallback to pdfplumber
  - Caching: downloaded PDFs are saved to a local directory

Usage:
    from agent_reach.research.pdf_reader import download_and_read

    text = download_and_read("https://arxiv.org/pdf/2301.12345.pdf")
    print(text[:500])
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional


# ------------------------------------------------------------------ #
# Configuration
# ------------------------------------------------------------------ #

def _cache_dir() -> Path:
    """Get or create the PDF cache directory."""
    base = Path(os.environ.get("AGENT_REACH_CACHE", Path.home() / ".agent_reach"))
    pdf_dir = base / "papers"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    return pdf_dir


# ------------------------------------------------------------------ #
# Download
# ------------------------------------------------------------------ #

def download_pdf(url: str, cache: bool = True, timeout: int = 60) -> Optional[Path]:
    """Download a PDF from a URL and save to cache.

    Args:
        url: PDF URL (e.g. https://arxiv.org/pdf/2301.12345.pdf).
        cache: Whether to use/save to cache (default True).
        timeout: Download timeout in seconds.

    Returns:
        Path to the downloaded PDF file, or None if download failed.
    """
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    dest_dir = _cache_dir()
    dest = dest_dir / f"{url_hash}.pdf"

    # Return cached copy if it exists
    if cache and dest.exists() and dest.stat().st_size > 0:
        return dest

    # Add User-Agent — some servers reject requests without one
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; AgentReach/1.0; "
            "mailto:research@example.com)"
        )
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = resp.read()

            # Validate it's a PDF (starts with %PDF)
            if not data.startswith(b"%PDF"):
                return None

            # Save to cache
            if cache:
                dest.write_bytes(data)
            else:
                # Write to temp file if not caching
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp.write(data)
                tmp.close()
                return Path(tmp.name)

            return dest

    except Exception:
        return None


# ------------------------------------------------------------------ #
# Text extraction
# ------------------------------------------------------------------ #

def extract_text(pdf_path: Path, max_pages: int = 50) -> str:
    """Extract text from a PDF file.

    Tries PyMuPDF (fitz) first, then pdfplumber.

    Args:
        pdf_path: Path to the PDF file.
        max_pages: Maximum pages to extract (prevents memory issues).

    Returns:
        Extracted text, or error message if extraction failed.
    """
    if not pdf_path.exists():
        return f"PDF 文件不存在: {pdf_path}"

    # --- Try PyMuPDF (fast, good quality) ---
    text = _extract_with_pymupdf(pdf_path, max_pages)
    if text:
        return text

    # --- Try pdfplumber (slower, better table handling) ---
    text = _extract_with_pdfplumber(pdf_path, max_pages)
    if text:
        return text

    # --- Last resort: try PyPDF2 or pypdf ---
    text = _extract_with_pypdf(pdf_path, max_pages)
    if text:
        return text

    return (
        "无法提取 PDF 文本。请安装以下任一库：\n"
        "  pip install pymupdf       (推荐，速度快)\n"
        "  pip install pdfplumber    (备选)\n"
        "  pip install pypdf         (最简)\n"
    )


def _extract_with_pymupdf(pdf_path: Path, max_pages: int) -> str:
    """Extract text using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ""

    try:
        doc = fitz.open(str(pdf_path))
        pages = []
        limit = min(len(doc), max_pages)
        for i in range(limit):
            page = doc[i]
            pages.append(page.get_text("text"))
        doc.close()
        return "\n\n".join(pages)
    except Exception:
        return ""


def _extract_with_pdfplumber(pdf_path: Path, max_pages: int) -> str:
    """Extract text using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        return ""

    try:
        pages = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            limit = min(len(pdf.pages), max_pages)
            for i in range(limit):
                page = pdf.pages[i]
                text = page.extract_text()
                if text:
                    pages.append(text)
        return "\n\n".join(pages)
    except Exception:
        return ""


def _extract_with_pypdf(pdf_path: Path, max_pages: int) -> str:
    """Extract text using pypdf (formerly PyPDF2)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            return ""

    try:
        reader = PdfReader(str(pdf_path))
        pages = []
        limit = min(len(reader.pages), max_pages)
        for i in range(limit):
            text = reader.pages[i].extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages)
    except Exception:
        return ""


# ------------------------------------------------------------------ #
# Main convenience function
# ------------------------------------------------------------------ #

def download_and_read(
    url: str,
    cache: bool = True,
    max_pages: int = 50,
    timeout: int = 60,
    on_progress=None,
) -> str:
    """Download a PDF and extract its text in one call.

    Args:
        url: PDF URL.
        cache: Whether to cache the PDF locally.
        max_pages: Max pages to extract.
        timeout: Download timeout in seconds.
        on_progress: Optional progress callback.

    Returns:
        Extracted text, or error message.
    """
    if on_progress:
        on_progress(f"⬇ 下载 PDF: {url}")

    pdf_path = download_pdf(url, cache=cache, timeout=timeout)
    if pdf_path is None:
        return f"下载失败: {url}\n请检查 URL 是否正确，或网络是否连通。"

    if on_progress:
        on_progress(f"📄 提取文本 ({pdf_path.stat().st_size // 1024} KB)")

    text = extract_text(pdf_path, max_pages=max_pages)

    if on_progress:
        words = len(text)
        on_progress(f"✅ 提取完成 ({words} 字符)")

    return text


def find_pdf_url(paper: dict) -> Optional[str]:
    """Extract the best available PDF URL from a paper metadata dict.

    Checks: pdf_url → open_access_pdf → constructs arXiv PDF URL from arxiv_id.

    Args:
        paper: Paper dict from search results.

    Returns:
        PDF URL string, or None.
    """
    # Direct PDF URL
    pdf = paper.get("pdf_url", "")
    if pdf and pdf.endswith(".pdf"):
        return pdf

    # Semantic Scholar open access
    open_pdf = paper.get("open_access_pdf", "")
    if open_pdf and open_pdf.endswith(".pdf"):
        return open_pdf

    # Construct from arXiv ID
    arxiv_id = paper.get("arxiv_id", "")
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    # Check if URL itself is a PDF
    url = paper.get("url", "")
    if url and ".pdf" in url:
        return url

    return None
