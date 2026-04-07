"""
Custom exceptions for md2office.
"""


class MD2OfficeError(Exception):
    """Base exception for all md2office errors."""


class TemplateNotFoundError(MD2OfficeError):
    """Raised when a template file does not exist or cannot be opened."""


class InputFormatError(MD2OfficeError):
    """Raised when the input file format is unsupported or malformed."""


class RenderError(MD2OfficeError):
    """Raised when rendering fails; no partial output is saved."""


class PlannerError(MD2OfficeError):
    """Raised when the content planner cannot build a valid plan."""


class LLMUnavailableError(MD2OfficeError):
    """Raised when the LLM provider cannot be reached; triggers fallback."""


class ValidationError(MD2OfficeError):
    """Raised when the validation pipeline finds blocking errors."""
