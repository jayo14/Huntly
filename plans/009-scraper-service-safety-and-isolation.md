# Plan 009: Scraper Service Safety, SSRF Prevention, and Resource Limits

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 5e1e430..HEAD -- leads/scraper_service.py`

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: plans/001-fix-test-verification-baseline.md
- **Category**: tech-debt
- **Planned at**: commit `5e1e430`, 2026-10-21

## Why this matters

`leads/scraper_service.py` runs headless Chrome using Selenium inside an unmanaged background thread spawned directly from Django view workers (`threading.Thread`).
This contains several production risks:
1. Dynamic binary installation (`ChromeDriverManager().install()`) fails on read-only container filesystems or serverless environments.
2. `driver.get(res['url'])` visits unvalidated URLs directly from external search results without IP checks, introducing Server-Side Request Forgery (SSRF) risk to internal services (e.g. cloud metadata services `169.254.169.254`).
3. If an error occurs or a thread terminates unexpectedly, Chrome processes can leak, causing CPU/RAM exhaustion.

## Current state

- `leads/scraper_service.py:58-60`:
  `service = Service(ChromeDriverManager().install())`
- `leads/scraper_service.py:114`:
  `driver.get(res['url'])` without scheme validation or private IP filtering.
- `leads/scraper_service.py:161-164`:
  `thread = threading.Thread(...)` without worker pool, rate-limiting, or supervisor.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run tests | `python3 manage.py test leads` | All tests pass |

## Scope

**In scope**:
- `leads/scraper_service.py`
- `leads/tests.py`

**Out of scope**:
- Rewriting the scraper into a full distributed crawler cluster.

## Steps

1. In `leads/scraper_service.py`:
   - Implement SSRF URL validator:
     ```python
     import ipaddress
     import socket
     from urllib.parse import urlparse

     def is_safe_url(url):
         try:
             parsed = urlparse(url)
             if parsed.scheme not in ('http', 'https'):
                 return False
             hostname = parsed.hostname
             if not hostname:
                 return False
             ip_str = socket.gethostbyname(hostname)
             ip = ipaddress.ip_address(ip_str)
             if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                 return False
             return True
         except Exception:
             return False
     ```
   - Before calling `driver.get(res['url'])`, check `if not is_safe_url(res['url']): continue`.
2. Ensure strict driver resource lifecycle:
   - Wrap the entire driver session in a `try...finally` block ensuring `driver.quit()` is ALWAYS executed, even on unexpected exceptions, user cancellation, or process signals.
3. Configure bounded execution:
   - Cap maximum websites visited per scraping job (e.g. `MAX_SITES = 10`) to prevent runaway resource consumption.
   - Enforce timeouts on page loads (`driver.set_page_load_timeout(15)`).
4. In `leads/tests.py`:
   - Add unit tests for `is_safe_url`:
     - Assert `http://127.0.0.1`, `http://localhost`, `http://169.254.169.254/latest/meta-data`, and `file:///etc/passwd` return `False`.
     - Assert valid public domains return `True`.
5. Run tests:
   ```bash
   python3 manage.py test leads
   ```

## STOP conditions

- If socket lookup in `is_safe_url` blocks in offline test runner, mock DNS resolution in tests.
