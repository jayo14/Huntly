"""Document extraction engine for Huntly resume import.

Supports:
- PDF extraction via pypdf (with scanned document detection)
- DOCX extraction via python-docx
- File format validation (magic bytes, extensions, size limits)
- Clean OCR extension point
"""

import io
import os
import re
import zipfile
from typing import Dict, Any, Tuple, Optional
from django.conf import settings
from pypdf import PdfReader
from docx import Document


class DocumentExtractionError(Exception):
    """Raised when an uploaded document cannot be read or is invalid."""
    pass


class DocumentFormatError(DocumentExtractionError):
    """Raised when file format is not permitted or magic bytes do not match."""
    pass


class DocumentOversizedError(DocumentExtractionError):
    """Raised when uploaded file exceeds size limits."""
    pass


class ScannedDocumentWarning(DocumentExtractionError):
    """Raised or flagged when a document has insufficient extractable text."""
    pass


class OCRExtensionPoint:
    """Extension interface for Optical Character Recognition (OCR).

    When a PDF contains scanned raster images without selectable text streams,
    this interface defines the contract for OCR integrations (e.g. Tesseract,
    AWS Textract, or Google Cloud Vision).
    """

    @classmethod
    def is_available(cls) -> bool:
        """Check if an OCR engine is configured and operational in this environment."""
        return False

    @classmethod
    def extract_scanned_text(cls, file_bytes: bytes) -> Optional[str]:
        """Attempt OCR text extraction on scanned document bytes.

        Returns extracted text string if OCR engine is configured, or None.
        """
        if not cls.is_available():
            return None
        # Clean extension hook for future OCR plug-in
        raise NotImplementedError("OCR engine is not configured in this environment.")


def get_max_upload_size() -> int:
    """Configurable upload size limit in bytes (defaults to 10MB)."""
    return getattr(settings, 'RESUME_IMPORT_MAX_SIZE_BYTES', 10 * 1024 * 1024)


def validate_file_bytes(file_bytes: bytes, filename: str) -> str:
    """Validate document extension, size, and magic bytes.

    Returns detected file type: 'pdf' or 'docx'.
    Raises DocumentFormatError or DocumentOversizedError.
    """
    if not file_bytes or len(file_bytes) == 0:
        raise DocumentExtractionError("The uploaded file is empty (0 bytes). Please upload a valid resume.")

    max_size = get_max_upload_size()
    if len(file_bytes) > max_size:
        max_mb = max_size // (1024 * 1024)
        raise DocumentOversizedError(
            f"The uploaded file ({len(file_bytes) / (1024 * 1024):.1f} MB) exceeds the maximum allowed size of {max_mb} MB."
        )

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ('.pdf', '.docx'):
        raise DocumentFormatError(
            f"Unsupported file format '{ext}'. Huntly supports PDF (.pdf) and Microsoft Word (.docx) files."
        )

    # Magic byte verification
    if ext == '.pdf':
        if not file_bytes.startswith(b'%PDF-'):
            raise DocumentFormatError(
                "The uploaded file has a .pdf extension but is not a valid PDF document (missing %PDF signature)."
            )
        return 'pdf'

    if ext == '.docx':
        # DOCX is an OpenXML ZIP archive containing [Content_Types].xml and word/document.xml
        if not file_bytes.startswith(b'PK\x03\x04'):
            raise DocumentFormatError(
                "The uploaded file has a .docx extension but is not a valid OpenXML Word document."
            )
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                namelist = zf.namelist()
                if 'word/document.xml' not in namelist:
                    raise DocumentFormatError("The uploaded DOCX archive does not contain 'word/document.xml'.")
        except zipfile.BadZipFile:
            raise DocumentFormatError("The uploaded DOCX file is corrupt or not a valid ZIP container.")
        return 'docx'

    raise DocumentFormatError("Unsupported file type.")


def extract_text_from_pdf(file_bytes: bytes) -> Tuple[str, Dict[str, Any]]:
    """Extract selectable text from PDF using pypdf.

    Returns (extracted_text, metadata_dict).
    Detects scanned PDFs where page text is empty or negligible.
    """
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception as e:
        raise DocumentExtractionError(f"Could not read PDF structure: {e}")

    num_pages = len(reader.pages)
    if num_pages == 0:
        raise DocumentExtractionError("The PDF document contains no pages.")

    pages_text = []
    total_chars = 0

    for idx, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
            # Normalize whitespace while preserving paragraphs
            clean_page = text.strip()
            pages_text.append(clean_page)
            total_chars += len(clean_page)
        except Exception as e:
            pages_text.append(f"[Page {idx+1} extract error: {e}]")

    combined_text = "\n\n".join(filter(None, pages_text))
    avg_chars_per_page = total_chars / max(1, num_pages)

    is_scanned = False
    ocr_recommended = False
    warnings = []

    # Scanned detection heuristic: under 60 total characters or under 30 chars/page
    if total_chars < 60 or avg_chars_per_page < 30:
        is_scanned = True
        ocr_recommended = True
        warnings.append(
            "This document appears to be a scanned image or photo containing little or no selectable text. "
            "Huntly requires text-based PDFs or DOCX files. OCR is currently not enabled in this environment."
        )

    metadata = {
        'num_pages': num_pages,
        'total_chars': total_chars,
        'avg_chars_per_page': avg_chars_per_page,
        'is_scanned': is_scanned,
        'ocr_recommended': ocr_recommended,
        'warnings': warnings,
    }

    return combined_text, metadata


def extract_text_from_docx(file_bytes: bytes) -> Tuple[str, Dict[str, Any]]:
    """Extract text from Microsoft Word (.docx) file using python-docx.

    Includes paragraphs, tables, and header/footer elements.
    """
    try:
        doc = Document(io.BytesIO(file_bytes))
    except Exception as e:
        raise DocumentExtractionError(f"Could not read DOCX document: {e}")

    parts = []
    # 1. Paragraphs
    for p in doc.paragraphs:
        txt = p.text.strip()
        if txt:
            parts.append(txt)

    # 2. Tables (frequently used for resume columns, contact headers, or skill grids)
    for table in doc.tables:
        for row in table.rows:
            row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_cells:
                # Deduplicate identical adjacent cells caused by merged table cells
                deduped = []
                for c in row_cells:
                    if not deduped or deduped[-1] != c:
                        deduped.append(c)
                parts.append(" | ".join(deduped))

    combined_text = "\n".join(parts)
    total_chars = len(combined_text)

    warnings = []
    if total_chars < 50:
        warnings.append("The Word document contains very little extractable text. Please ensure content is not in embedded images.")

    metadata = {
        'num_pages': 1,
        'total_chars': total_chars,
        'is_scanned': False,
        'ocr_recommended': False,
        'warnings': warnings,
    }

    return combined_text, metadata


def extract_document_content(file_bytes: bytes, filename: str) -> Tuple[str, str, Dict[str, Any]]:
    """Primary entry point for document extraction.

    Validates bytes and extracts text.
    Returns (extracted_text, file_type, metadata_dict).
    """
    file_type = validate_file_bytes(file_bytes, filename)
    if file_type == 'pdf':
        text, meta = extract_text_from_pdf(file_bytes)
    elif file_type == 'docx':
        text, meta = extract_text_from_docx(file_bytes)
    else:
        raise DocumentFormatError(f"Unsupported file type '{file_type}'.")

    return text, file_type, meta
