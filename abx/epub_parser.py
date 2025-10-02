"""EPUB parsing and chaptering logic."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import ebooklib
from ebooklib import epub


@dataclass
class Chapter:
    """Represents a chapter from an EPUB."""

    idx: int
    title: str
    html_content: str
    href: str


@dataclass
class BookMetadata:
    """EPUB metadata."""

    title: str
    authors: list[str]
    publisher: str | None
    published_date: str | None
    language: str | None
    sha256: str
    source_path: str


def compute_book_sha(epub_path: Path) -> str:
    """Compute SHA256 of EPUB file."""
    sha256_hash = hashlib.sha256()
    with open(epub_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def extract_metadata(book: epub.EpubBook, epub_path: Path, sha256: str) -> BookMetadata:
    """Extract metadata from EPUB."""
    title = book.get_metadata("DC", "title")
    title_str = title[0][0] if title else "Untitled"

    authors = book.get_metadata("DC", "creator")
    authors_list = [a[0] for a in authors] if authors else []

    publisher = book.get_metadata("DC", "publisher")
    publisher_str = publisher[0][0] if publisher else None

    date = book.get_metadata("DC", "date")
    date_str = date[0][0] if date else None

    language = book.get_metadata("DC", "language")
    language_str = language[0][0] if language else None

    return BookMetadata(
        title=title_str,
        authors=authors_list,
        publisher=publisher_str,
        published_date=date_str,
        language=language_str,
        sha256=sha256,
        source_path=str(epub_path.absolute()),
    )


def should_skip_chapter(title: str) -> bool:
    """
    Check if chapter should be skipped based on title patterns.

    Skips common boilerplate sections like copyright, contents, etc.
    """
    skip_patterns = [
        r"^contents?$",
        r"^table of contents$",
        r"^copyright$",
        r"^legal notice$",
        r"^dedication$",
        r"^acknowledgments?$",
        r"^about the author$",
        r"^also by",
        r"^books by",
        r"^praise for",
        r"^title page$",
        r"^half title$",
        r"^frontmatter$",
        r"^backmatter$",
    ]

    title_lower = title.lower().strip()
    return any(re.match(pattern, title_lower) for pattern in skip_patterns)


def chapterize_epub(book: epub.EpubBook, chapter_limit: int = 999, skip_boilerplate: bool = True) -> list[Chapter]:
    """
    Extract chapters from EPUB.

    Chaptering strategy:
    1. Use spine for ordering
    2. Extract HTML documents
    3. Derive titles from nav/NCX or <h1>/<h2> tags
    4. Filter out very short sections (< 100 words)
    5. Optionally skip boilerplate chapters (copyright, contents, etc.)
    """
    chapters = []
    chapter_idx = 0

    # Build title map from TOC
    toc_titles = {}
    for toc_item in book.toc:
        if isinstance(toc_item, tuple):
            # Nested TOC
            for sub_item in toc_item[1]:
                if hasattr(sub_item, "href") and hasattr(sub_item, "title"):
                    href = sub_item.href.split("#")[0]
                    toc_titles[href] = sub_item.title
        elif hasattr(toc_item, "href") and hasattr(toc_item, "title"):
            href = toc_item.href.split("#")[0]
            toc_titles[href] = toc_item.title

    # Process spine
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        if chapter_idx >= chapter_limit:
            break

        content = item.get_content().decode("utf-8", errors="ignore")
        href = item.get_name()

        # Estimate word count
        text_preview = re.sub(r"<[^>]+>", " ", content)
        word_count = len(text_preview.split())

        # Skip very short sections
        if word_count < 100:
            continue

        # Determine title
        title = toc_titles.get(href)
        if not title:
            # Try to extract from h1/h2
            h_match = re.search(r"<h[12][^>]*>(.*?)</h[12]>", content, re.IGNORECASE | re.DOTALL)
            if h_match:
                title = re.sub(r"<[^>]+>", "", h_match.group(1)).strip()
            else:
                title = f"Chapter {chapter_idx + 1}"

        # Skip boilerplate chapters if enabled
        if skip_boilerplate and should_skip_chapter(title):
            continue

        chapters.append(
            Chapter(
                idx=chapter_idx,
                title=title[:200],  # Limit title length
                html_content=content,
                href=href,
            )
        )
        chapter_idx += 1

    return chapters


def parse_epub(epub_path: Path, chapter_limit: int = 999, skip_boilerplate: bool = True) -> tuple[BookMetadata, list[Chapter]]:
    """Parse EPUB and return metadata + chapters."""
    sha256 = compute_book_sha(epub_path)
    book = epub.read_epub(str(epub_path))
    metadata = extract_metadata(book, epub_path, sha256)
    chapters = chapterize_epub(book, chapter_limit, skip_boilerplate)
    return metadata, chapters
