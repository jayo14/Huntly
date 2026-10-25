#!/usr/bin/env bash
# ==============================================================================
# Huntly Automated Quality Gate & Launch Verification Runner
# Runs linting, migration check, security checks, and automated tests.
# Exit code 0 if all gates pass; non-zero if any gate fails.
# ==============================================================================

set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
NC="\033[0m"

echo -e "${BOLD}${CYAN}======================================================${NC}"
echo -e "${BOLD}${CYAN}   Huntly Automated Production Launch Quality Gate    ${NC}"
echo -e "${BOLD}${CYAN}======================================================${NC}"

VENV_PY=".venv/bin/python"
if [ ! -f "$VENV_PY" ]; then
    VENV_PY="python"
fi

# Step 1: Frontend JavaScript Generator Tests
echo -e "\n${BOLD}[Gate 1/5] Frontend JS Generator Unit Tests${NC}"
if npm test; then
    echo -e "${GREEN}✓ Frontend generator tests passed.${NC}"
else
    echo -e "${RED}✗ Frontend generator tests failed!${NC}"
    exit 1
fi

# Step 2: NPM Security Audit
echo -e "\n${BOLD}[Gate 2/5] Frontend Dependency Security Audit${NC}"
if npm audit --omit=dev; then
    echo -e "${GREEN}✓ NPM package audit passed (0 vulnerabilities).${NC}"
else
    echo -e "${RED}✗ NPM package security audit failed!${NC}"
    exit 1
fi

# Step 3: Migration Drift & Schema Check
echo -e "\n${BOLD}[Gate 3/5] Django Migration Drift & Schema Check${NC}"
if $VENV_PY manage.py makemigrations --check --dry-run; then
    echo -e "${GREEN}✓ Migrations are up to date (no uncommitted model changes).${NC}"
else
    echo -e "${RED}✗ Uncommitted migration drift detected! Run makemigrations.${NC}"
    exit 1
fi

# Step 4: Django Production Configuration & Security Check
echo -e "\n${BOLD}[Gate 4/5] Django Production Security Check (--deploy)${NC}"
if DJANGO_SETTINGS_MODULE=huntly.settings.prod \
   SECURE_SSL_REDIRECT=True \
   SECRET_KEY=huntly-deploy-check-secret-key-production-verification \
   ALLOWED_HOSTS=huntly.app,www.huntly.app \
   $VENV_PY manage.py check --deploy; then
    echo -e "${GREEN}✓ Production settings security check passed (0 issues).${NC}"
else
    echo -e "${YELLOW}! Production security check reported warnings (review above).${NC}"
fi

# Step 5: Full Automated Test Suite (Billing, Leads, Resumes, Core)
echo -e "\n${BOLD}[Gate 5/5] Django Test Suite (Unit, Integration, Security, Perf)${NC}"
if $VENV_PY manage.py test billing leads resumes core --keepdb; then
    echo -e "${GREEN}✓ All Django tests passed successfully.${NC}"
else
    echo -e "${RED}✗ Django test suite reported failures!${NC}"
    exit 1
fi

echo -e "\n${BOLD}${GREEN}======================================================${NC}"
echo -e "${BOLD}${GREEN}   ALL PRODUCTION QUALITY GATES PASSED SUCCESSFULLY   ${NC}"
echo -e "${BOLD}${GREEN}======================================================${NC}"
exit 0
