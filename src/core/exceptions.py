"""
Custom exceptions for text2officeprocessor.
"""


class Text2OfficeProcessorError(Exception):
    """Base exception for all text2officeprocessor errors."""


class TemplateNotFoundError(Text2OfficeProcessorError):
    """Raised when a template file does not exist or cannot be opened."""


class InputFormatError(Text2OfficeProcessorError):
    """Raised when the input file format is unsupported or malformed."""


class RenderError(Text2OfficeProcessorError):
    """Raised when rendering fails; no partial output is saved."""


class PlannerError(Text2OfficeProcessorError):
    """Raised when the content planner cannot build a valid plan."""


class LLMUnavailableError(Text2OfficeProcessorError):
    """Raised when the LLM provider cannot be reached; triggers fallback."""


class ValidationError(Text2OfficeProcessorError):
    """Raised when the validation pipeline finds blocking errors."""
