"""Document chunking for RAG with context-aware splitting.

This module provides intelligent document chunking that:
1. Respects context boundaries (sentences, paragraphs, code blocks)
2. Targets 400-600 tokens per chunk (soft limit)
3. Handles both natural language and code
4. Preserves semantic coherence
"""

import re
from dataclasses import dataclass
from typing import List

import tiktoken


@dataclass
class Chunk:
    """A chunk of text with metadata."""

    content: str
    start_char: int  # Character offset in original document
    end_char: int
    token_count: int
    chunk_index: int  # 0-based index within document


class DocumentChunker:
    """Chunks documents with context-aware splitting.

    Strategy:
    1. Split on major boundaries (functions, classes, paragraphs)
    2. If chunk too large, split on sentence boundaries
    3. If still too large, split on word boundaries
    4. Target 400-600 tokens, but allow flexibility for coherence
    """

    def __init__(
        self,
        target_min_tokens: int = 400,
        target_max_tokens: int = 600,
        hard_max_tokens: int = 1000,
        encoding_name: str = "cl100k_base",  # GPT-4 tokenizer
    ):
        """Initialize chunker.

        Args:
            target_min_tokens: Preferred minimum chunk size
            target_max_tokens: Preferred maximum chunk size
            hard_max_tokens: Absolute maximum (force split if exceeded)
            encoding_name: Tokenizer to use for counting
        """
        self.target_min_tokens = target_min_tokens
        self.target_max_tokens = target_max_tokens
        self.hard_max_tokens = hard_max_tokens
        self.encoding = tiktoken.get_encoding(encoding_name)

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.encoding.encode(text))

    def chunk_document(self, content: str, file_path: str = "") -> List[Chunk]:
        """Chunk a document into semantically coherent pieces.

        Args:
            content: Document text content
            file_path: Optional file path for better splitting heuristics

        Returns:
            List of Chunk objects
        """
        # Detect content type
        is_code = self._is_code_file(file_path)

        # Split into initial segments
        if is_code:
            segments = self._split_code(content)
        else:
            segments = self._split_text(content)

        # Build chunks from segments
        chunks = []
        current_chunk = ""
        current_start = 0
        chunk_index = 0

        for segment in segments:
            segment_tokens = self.count_tokens(segment)
            current_tokens = self.count_tokens(current_chunk)
            combined_tokens = self.count_tokens(current_chunk + segment)

            # If adding this segment exceeds hard max, finalize current chunk
            if current_chunk and combined_tokens > self.hard_max_tokens:
                chunk = self._finalize_chunk(
                    current_chunk, current_start, current_start + len(current_chunk), chunk_index
                )
                chunks.append(chunk)
                chunk_index += 1
                current_chunk = segment
                current_start += len(current_chunk)
            # If current chunk is in target range, finalize it
            elif current_tokens >= self.target_min_tokens and segment_tokens > 0:
                chunk = self._finalize_chunk(
                    current_chunk, current_start, current_start + len(current_chunk), chunk_index
                )
                chunks.append(chunk)
                chunk_index += 1
                current_chunk = segment
                current_start += len(chunk.content)
            # Otherwise, accumulate
            else:
                current_chunk += segment

        # Finalize remaining chunk
        if current_chunk.strip():
            chunk = self._finalize_chunk(
                current_chunk, current_start, current_start + len(current_chunk), chunk_index
            )
            chunks.append(chunk)

        return chunks

    def _finalize_chunk(
        self, content: str, start_char: int, end_char: int, chunk_index: int
    ) -> Chunk:
        """Create a Chunk object with metadata."""
        return Chunk(
            content=content.strip(),
            start_char=start_char,
            end_char=end_char,
            token_count=self.count_tokens(content),
            chunk_index=chunk_index,
        )

    def _is_code_file(self, file_path: str) -> bool:
        """Detect if file is code based on extension."""
        code_extensions = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".cs",
            ".php",
            ".rb",
            ".go",
            ".rs",
            ".swift",
            ".kt",
            ".sh",
            ".sql",
        }
        return any(file_path.endswith(ext) for ext in code_extensions)

    def _split_code(self, content: str) -> List[str]:
        """Split code on function/class boundaries.

        Strategy:
        1. Split on function/class definitions
        2. Keep docstrings with functions
        3. Preserve indentation context
        """
        segments = []

        # Regex patterns for common code structures
        # Python: def/class, JavaScript: function/class, etc.
        patterns = [
            r"\n(?=(?:async\s+)?(?:def|class)\s+\w+)",  # Python
            r"\n(?=(?:async\s+)?function\s+\w+)",  # JavaScript function
            r"\n(?=class\s+\w+)",  # JavaScript/Java class
            r"\n(?=(?:public|private|protected)\s+)",  # Java/C++ methods
        ]

        # Try each pattern
        for pattern in patterns:
            parts = re.split(pattern, content)
            if len(parts) > 1:
                # Found good splits, use them
                segments = [p for p in parts if p.strip()]
                break

        # Fallback: split on double newlines (paragraph-like)
        if not segments:
            segments = [s.strip() + "\n\n" for s in content.split("\n\n") if s.strip()]

        # If segments are still too large, split further
        refined_segments = []
        for segment in segments:
            if self.count_tokens(segment) > self.hard_max_tokens:
                # Split on single newlines
                subsegments = [s + "\n" for s in segment.split("\n") if s.strip()]
                refined_segments.extend(subsegments)
            else:
                refined_segments.append(segment)

        return refined_segments if refined_segments else [content]

    def _split_text(self, content: str) -> List[str]:
        """Split natural language text on sentence/paragraph boundaries.

        Strategy:
        1. Split on paragraphs (double newlines)
        2. If too large, split on sentences
        3. If still too large, split on words
        """
        # First, split on paragraphs
        paragraphs = [p.strip() + "\n\n" for p in content.split("\n\n") if p.strip()]

        segments = []
        for para in paragraphs:
            para_tokens = self.count_tokens(para)

            # If paragraph is in target range, keep it
            if para_tokens <= self.target_max_tokens:
                segments.append(para)
            # If too large, split on sentences
            elif para_tokens > self.hard_max_tokens:
                sentences = self._split_sentences(para)
                segments.extend(sentences)
            else:
                # Close to max but not over hard limit
                segments.append(para)

        return segments if segments else [content]

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences.

        Uses simple heuristics for sentence boundaries.
        """
        # Split on sentence terminators followed by space and capital letter
        # or newline
        pattern = r"(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])\n"
        sentences = re.split(pattern, text)

        # Clean up and add spacing
        result = []
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                result.append(sentence + " ")

        return result if result else [text]
