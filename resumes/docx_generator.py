import json
import os
import shutil
import subprocess
from django.conf import settings


class DocxGenerationError(Exception):
    """Raised when DOCX document generation fails."""
    pass


def generate_docx(data):
    """Generate a DOCX resume from a dictionary of resume data.

    Executes scripts/resume_generator.js via Node.js and returns bytes.
    Raises DocxGenerationError if Node is missing, the script fails,
    or the generated output is empty or corrupt.
    """
    node_path = shutil.which('node')
    if not node_path:
        raise DocxGenerationError("Node runtime not available")

    script_path = os.path.join(settings.BASE_DIR, 'scripts', 'resume_generator.js')
    if not os.path.exists(script_path):
        raise DocxGenerationError(f"Resume generator script not found at {script_path}")

    try:
        process = subprocess.Popen(
            [node_path, script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate(
            input=json.dumps(data).encode('utf-8'),
            timeout=30
        )
    except Exception as e:
        raise DocxGenerationError(f"Process execution failed: {e}") from e

    if process.returncode != 0:
        error_msg = stderr.decode('utf-8', errors='replace').strip() if stderr else 'Unknown error'
        raise DocxGenerationError(f"Node script failed with exit code {process.returncode}: {error_msg}")

    if not stdout or len(stdout) < 100:
        raise DocxGenerationError(
            f"Generated DOCX document is invalid or empty ({len(stdout) if stdout else 0} bytes)"
        )

    return stdout
