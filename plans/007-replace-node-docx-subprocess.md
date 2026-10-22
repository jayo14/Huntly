# Plan 007: Replace Fragile Node DOCX Subprocess with Robust Generation

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 5e1e430..HEAD -- resumes/views.py scripts/resume_generator.js`

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: plans/001-fix-test-verification-baseline.md
- **Category**: tech-debt
- **Planned at**: commit `5e1e430`, 2026-10-21

## Why this matters

In `resumes/views.py:165-175`, DOCX generation calls `subprocess.Popen(['node', 'scripts/resume_generator.js', json.dumps(data)], ...)` synchronously.
This creates three severe operational problems:
1. In serverless deployments (such as `@vercel/python`), the runtime does not provide Node.js, causing execution to fail.
2. Passing large JSON payloads via `argv` is subject to OS argument limits and shell interpretation.
3. Errors in the Node script are swallowed: `if stderr: print(...)` does not raise an exception or set an HTTP error status; `stdout` is empty (0 bytes), and Huntly serves a corrupted 0-byte document with HTTP 200 OK.

## Current state

- `resumes/views.py:165-175`:
```python
def generate_docx(data):
    process = subprocess.Popen(
        ['node', 'scripts/resume_generator.js', json.dumps(data)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = process.communicate()
    if stderr:
        print(f"Error in node script: {stderr.decode()}")
    return stdout # Returns empty bytes if node failed
```

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run tests | `python3 manage.py test resumes` | All tests pass |

## Scope

**In scope**:
- `resumes/views.py` (`generate_docx` function and related view error handling)
- `resumes/docx_generator.py` (native Python generator or fortified process handler)
- `resumes/tests.py`

**Out of scope**:
- Resume UI layout templates.

## Steps

1. Implement robust document generation in `resumes/`:
   - Either: Port the document structure to `python-docx` directly in Python (eliminating the Node.js runtime dependency entirely).
   - Or: Fortify the subprocess invocation:
     - Check `shutil.which('node')` before executing.
     - Pass JSON payload via `stdin` rather than CLI `argv` (`process.communicate(input=json.dumps(data).encode('utf-8'))`).
     - Check `process.returncode != 0`; if nonzero or if `stdout` is empty, raise a custom `DocxGenerationError` instead of returning 0 bytes.
2. Update `resume_create`, `resume_update`, and `resume_download` in `resumes/views.py`:
   - Catch `DocxGenerationError` or file generation failures.
   - Return a clean HTTP 500 error or redirect with user-facing message `messages.error(request, "Failed to generate resume document.")` instead of returning a corrupt 0-byte file with HTTP 200.
3. In `resumes/tests.py`:
   - Add test case verifying valid document generation produces a valid non-empty byte stream (`len(response.content) > 1000`).
   - Add test case simulating generator error; assert view handles failure gracefully without returning empty HTTP 200.
4. Run tests:
   ```bash
   python3 manage.py test resumes
   ```

## STOP conditions

- If `python-docx` is chosen, verify it is listed in `requirements.txt`.
