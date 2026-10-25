from .document_generator import generate_docx as python_generate_docx, DocumentGenerationError

class DocxGenerationError(DocumentGenerationError):
    """Raised when DOCX document generation fails."""
    pass


def generate_docx(data):
    """Generate a clean, valid ATS-friendly DOCX resume using pure Python python-docx.

    Provides 100% backward compatibility for existing callers without external Node.js dependencies.
    """
    try:
        return python_generate_docx(data)
    except Exception as e:
        raise DocxGenerationError(str(e)) from e

