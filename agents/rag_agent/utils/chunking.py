"""
Token-aware text chunker.

We use `tiktoken` (cl100k_base) as a stable, fast tokenizer for sizing.
Gemini does not expose its tokenizer via tiktoken, but cl100k is close
enough for chunk sizing — the 500-1000 token target is not a hard limit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import tiktoken

_ENCODER = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    content: str
    index: int
    token_count: int
    char_start: int
    char_end: int
    metadata: dict = field(default_factory=dict)


class TextChunker:
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 100) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str) -> list[Chunk]:
        """
        Token-aware chunking with overlap. Tries to avoid splitting mid-sentence
        by snapping chunk boundaries to the nearest sentence break when one
        exists within a short look-back window.
        """
        text = _normalize(text)
        if not text:
            return []

        tokens = _ENCODER.encode(text, disallowed_special=())
        if len(tokens) <= self.chunk_size:
            return [
                Chunk(
                    content=text,
                    index=0,
                    token_count=len(tokens),
                    char_start=0,
                    char_end=len(text),
                )
            ]

        chunks: list[Chunk] = []
        step = self.chunk_size - self.chunk_overlap
        start_tok = 0
        idx = 0
        while start_tok < len(tokens):
            end_tok = min(start_tok + self.chunk_size, len(tokens))
            chunk_tokens = tokens[start_tok:end_tok]
            chunk_text = _ENCODER.decode(chunk_tokens)
            chunk_text = _snap_to_sentence(chunk_text) if end_tok < len(tokens) else chunk_text
            char_start = text.find(chunk_text[:40]) if len(chunk_text) >= 40 else -1
            chunks.append(
                Chunk(
                    content=chunk_text,
                    index=idx,
                    token_count=len(chunk_tokens),
                    char_start=max(char_start, 0),
                    char_end=max(char_start, 0) + len(chunk_text),
                )
            )
            idx += 1
            if end_tok == len(tokens):
                break
            start_tok += step
        return chunks


def _normalize(text: str) -> str:
    # Collapse runs of whitespace; preserve paragraph breaks.
    out_lines: list[str] = []
    for line in text.splitlines():
        out_lines.append(" ".join(line.split()))
    # Keep at most one blank line between paragraphs.
    collapsed: list[str] = []
    blank = False
    for line in out_lines:
        if line:
            collapsed.append(line)
            blank = False
        elif not blank:
            collapsed.append("")
            blank = True
    return "\n".join(collapsed).strip()


def _snap_to_sentence(text: str, lookback: int = 200) -> str:
    """Trim trailing partial sentence if a sentence end is near the tail."""
    if len(text) <= lookback:
        return text
    tail = text[-lookback:]
    for mark in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
        idx = tail.rfind(mark)
        if idx != -1:
            cut = len(text) - lookback + idx + len(mark)
            return text[:cut].rstrip()
    return text


def batched(items: Iterable, size: int):
    """Yield fixed-size batches from an iterable."""
    batch: list = []
    for it in items:
        batch.append(it)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
