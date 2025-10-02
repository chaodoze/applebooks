"""HTML cleaning utilities."""

import html
import re

from bs4 import BeautifulSoup


def clean_html(html_content: str, mode: str = "loose") -> str:
    """
    Clean HTML to plain text.

    Args:
        html_content: Raw HTML from EPUB chapter
        mode: 'loose' or 'strict'
            - loose: Remove scripts/styles, keep structure, gentle cleanup
            - strict: Aggressive stripping, minimal formatting
    """
    soup = BeautifulSoup(html_content, "lxml")

    # Remove scripts, styles, and other non-content elements
    for tag in soup(["script", "style", "noscript", "meta", "link"]):
        tag.decompose()

    if mode == "strict":
        # Remove footnote anchors and references
        for tag in soup.find_all("a", class_=re.compile(r"footnote|endnote|noteref", re.I)):
            tag.decompose()

        # Remove sup/sub tags often used for footnotes
        for tag in soup(["sup", "sub"]):
            if tag.find("a"):
                tag.decompose()

    # Get text
    text = soup.get_text(separator=" ", strip=False)

    # Decode HTML entities
    text = html.unescape(text)

    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)  # Collapse spaces/tabs
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)  # Max 2 consecutive newlines
    text = text.strip()

    if mode == "strict":
        # More aggressive cleanup
        text = re.sub(r"\n[ \t]+", "\n", text)  # Remove leading spaces on lines
        text = re.sub(r"[ \t]+\n", "\n", text)  # Remove trailing spaces on lines

    return text
