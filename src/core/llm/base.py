"""
LLM abstraction layer for md2office.

Scope (STRICT — per specification):
- Markdown normalization
- Content structuring / semantic tagging
- Slide/type mapping hints
- Rule-based validation suggestions

Forbidden:
- Generating final PPTX/DOCX/XLSX content directly
- Making layout or formatting decisions
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for all LLM provider implementations."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """
        Send a prompt to the LLM and return the text response.

        Args:
            prompt: The full prompt string.

        Returns:
            Raw text response from the model.
        """

    def is_available(self) -> bool:
        """
        Check whether the provider endpoint is reachable.

        Returns:
            True if available, False otherwise.
        """
        try:
            self.generate("ping")
            return True
        except Exception:
            return False
