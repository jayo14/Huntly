"""High-level Resume Import Pipeline Orchestrator.

Orchestrates document extraction, validation, structured parsing,
scanned document detection, and draft state persistence.
"""

import logging
from typing import Dict, Any
from resumes.models import ResumeImport
from .extractor import (
    extract_document_content,
    DocumentExtractionError,
    DocumentFormatError,
    DocumentOversizedError,
)
from .parser import parse_resume_text

logger = logging.getLogger(__name__)


def process_resume_import_file(import_obj: ResumeImport) -> ResumeImport:
    """Execute the end-to-end extraction and parsing pipeline on a ResumeImport.

    Updates the record state to 'processing', then either 'review_required' or 'failed'.
    """
    if import_obj.status == 'processing':
        # Prevent concurrent duplicate processing
        return import_obj

    import_obj.status = 'processing'
    import_obj.error_message = ''
    import_obj.save(update_fields=['status', 'error_message', 'updated_at'])

    try:
        # Read file bytes from private storage
        if not import_obj.file:
            raise DocumentExtractionError("No uploaded document file was attached.")

        import_obj.file.open('rb')
        try:
            file_bytes = import_obj.file.read()
        finally:
            import_obj.file.close()

        import_obj.file_size = len(file_bytes)

        # 1. Extract text and detect file type / scanned status
        extracted_text, detected_type, metadata = extract_document_content(
            file_bytes=file_bytes,
            filename=import_obj.file_name or import_obj.file.name,
        )

        import_obj.file_type = detected_type
        import_obj.extracted_text = extracted_text
        import_obj.is_scanned = metadata.get('is_scanned', False)
        import_obj.ocr_recommended = metadata.get('ocr_recommended', False)

        warnings = list(metadata.get('warnings', []))

        # 2. Check if document has insufficient text or is completely blank
        if len(extracted_text.strip()) == 0:
            if import_obj.is_scanned:
                raise DocumentExtractionError(
                    "The uploaded PDF appears to be a scanned image or photo with no extractable text. "
                    "Huntly currently requires text-based PDFs or Word (.docx) files so your real career facts "
                    "can be extracted without OCR errors."
                )
            else:
                raise DocumentExtractionError("The document contains no readable text. Please upload a valid resume.")

        # 3. Parse extracted text into structured candidate schema
        parsed_data = parse_resume_text(extracted_text, allow_ai=True)

        # Merge warnings
        parsing_warnings = parsed_data.get('warnings', [])
        combined_warnings = list(dict.fromkeys(warnings + parsing_warnings))

        import_obj.parsed_data = parsed_data
        import_obj.warnings = combined_warnings
        import_obj.status = 'review_required'
        import_obj.save()
        return import_obj

    except (DocumentFormatError, DocumentOversizedError, DocumentExtractionError) as e:
        logger.warning(f"Resume import extraction error for import {import_obj.pk}: {e}")
        import_obj.status = 'failed'
        import_obj.error_message = str(e)
        import_obj.save()
        return import_obj
    except Exception as e:
        logger.exception(f"Unexpected error processing resume import {import_obj.pk}: {e}")
        import_obj.status = 'failed'
        import_obj.error_message = f"An unexpected error occurred while processing your resume: {e}"
        import_obj.save()
        return import_obj
