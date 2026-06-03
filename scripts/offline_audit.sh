#!/bin/bash
# Primnox Offline-First Security Audit

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR/.." || exit 1

echo "[*] Initiating Zero-Trust Static Analysis..."

if [ ! -d "./backend" ] || [ ! -d "./frontend/src" ]; then
    echo "[!] CRITICAL: Directories ./backend or ./frontend/src not found."
    exit 1
fi

# The python AST script is more robust for Python. This bash script is a fallback.
# Scan for unauthorized outbound HTTP requests in Python files.
# Extract the URLs with grep -o to avoid line-based bypasses.
if grep -hroE "(requests|httpx)\.(get|post|put|delete|request)\([^\)]+\)|urllib\.request" ./backend/ --exclude-dir=tests --exclude="audit.py" --exclude="verify_imports.py" | grep -vE "(api\.groq\.com|api\.openai\.com|api\.anthropic\.com|api\.tavily\.com|localhost|127\.0\.0\.1|::1)"; then
    echo "[!] CRITICAL: Unauthorized outbound network request detected in backend code."
    exit 1
fi

# Scan for unauthorized fetch/axios calls in TypeScript files
if grep -hroE "(fetch|axios\.[a-z]+)\([^\)]+\)" ./frontend/src/ --exclude-dir=node_modules | grep -vE "(localhost|127\.0\.0\.1|::1|API_BASE_URL|^\/|^\.\/|^\.\.\/)"; then
    echo "[!] CRITICAL: Unauthorized outbound network request detected in frontend code."
    exit 1
fi

echo "[+] Audit Passed. Zero-Trust perimeter is secure."
exit 0
