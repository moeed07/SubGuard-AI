"""Extract canonical capability tags from sanitized billing email subjects and bodies."""

from __future__ import annotations

import re

CAPABILITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "music",
        re.compile(
            r"\b(?:ad[- ]free music|youtube music|spotify|offline downloads|higher audio quality|music streaming)\b",
            re.I,
        ),
    ),
    (
        "ai",
        re.compile(
            r"\b(?:gemini|chatgpt|ai assistant|higher usage limits|file uploads and analysis|image generation)\b",
            re.I,
        ),
    ),
    (
        "storage",
        re.compile(
            r"\b(?:cloud storage|\d+\s*(?:gb|tb)\s+(?:of\s+)?storage|onedrive|google drive)\b",
            re.I,
        ),
    ),
    (
        "movies",
        re.compile(
            r"\b(?:movies|tv shows|netflix|films|cinema|hd streaming|4k streaming)\b",
            re.I,
        ),
    ),
    (
        "office",
        re.compile(
            r"\b(?:microsoft 365|office apps|word|excel|powerpoint|outlook)\b",
            re.I,
        ),
    ),
    (
        "sports",
        re.compile(
            r"\b(?:live cricket|sports|tamasha|live tv|football|match streaming)\b",
            re.I,
        ),
    ),
    (
        "coding",
        re.compile(
            r"\b(?:coding|code completion|ide|github copilot|developer)\b",
            re.I,
        ),
    ),
    (
        "writing",
        re.compile(
            r"\b(?:writing|grammarly|grammar|proofreading)\b",
            re.I,
        ),
    ),
    (
        "design",
        re.compile(
            r"\b(?:design pro|figma|sketch|canva|illustrator|graphic design)\b",
            re.I,
        ),
    ),
)


def extract_capability_tags(subject: str, body_text: str) -> list[str]:
    """Return sorted canonical feature tags detected from an email's subject and body."""
    combined = f"{subject}\n{body_text}".strip()
    if not combined:
        return []
    return sorted({tag for tag, pattern in CAPABILITY_PATTERNS if pattern.search(combined)})
