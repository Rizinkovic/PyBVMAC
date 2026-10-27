"""Exception hierarchy used throughout PyBVMAC."""


class PyBVMACError(Exception):
    """Base class for all PyBVMAC errors."""


class FetchError(PyBVMACError):
    """Raised when a bulletin cannot be downloaded or discovered."""


class ParseError(PyBVMACError):
    """Raised when a bulletin cannot be parsed into structured records."""


class OCRNotAvailableError(PyBVMACError):
    """Raised when OCR is required but the optional OCR dependencies
    (pytesseract, pdf2image) or the Tesseract binary are not installed.

    Install with: pip install pybvmac[ocr]
    """


class UnknownTickerError(PyBVMACError):
    """Raised when a ticker symbol cannot be resolved via the ticker map."""
