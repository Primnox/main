import os
import ast
import re
import sys

print("[*] Initiating Zero-Trust AST-based Static Analysis...")

# Resolve paths relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
backend_dir = os.path.join(PROJECT_ROOT, "backend")
frontend_src_dir = os.path.join(PROJECT_ROOT, "frontend", "src")

if not os.path.exists(backend_dir) or not os.path.exists(frontend_src_dir):
    print("[!] CRITICAL: Backend or Frontend directories not found. Run this from the project root or scripts directory.")
    sys.exit(1)

failed = False

def is_loopback(url):
    # Better check to prevent bypass like 'https://evil.com/localhost'
    return any(url.startswith(p) for p in ["http://localhost", "http://127.0.0.1", "ws://localhost", "ws://127.0.0.1"]) or "loopback" in url

def is_model_api(url):
    return any(x in url for x in ["api.groq.com", "api.openai.com", "api.anthropic.com", "api.tavily.com"])

class OutboundCallVisitor(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.violations = []

    def visit_Call(self, node):
        func = node.func
        is_http_call = False
        url_arg = None

        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name):
                if func.value.id in ["requests", "httpx"] and func.attr in ["get", "post", "request", "put", "delete"]:
                    is_http_call = True
        
        if is_http_call:
            if len(node.args) > 0:
                if func.attr == "request" and len(node.args) > 1:
                    url_arg = node.args[1]
                else:
                    url_arg = node.args[0]
            else:
                for kw in node.keywords:
                    if kw.arg == "url":
                        url_arg = kw.value
                        break

            if url_arg:
                if isinstance(url_arg, ast.Constant) and isinstance(url_arg.value, str):
                    url_str = url_arg.value
                    if not is_loopback(url_str):
                        basename = os.path.basename(self.filename)
                        if basename in ["brain.py", "sensor_vision.py", "tools.py"] and is_model_api(url_str):
                            pass
                        else:
                            self.violations.append((node.lineno, url_str))
                else:
                    basename = os.path.basename(self.filename)
                    # Dynamic URLs are a security risk if not strictly controlled.
                    # We now flag all dynamic URLs as violations. The code should use constants or specific whitelists.
                    self.violations.append((node.lineno, "<dynamic/variable URL>"))

        self.generic_visit(node)

# Python AST scan
for root, dirs, files in os.walk(backend_dir):
    if "tests" in dirs:
        dirs.remove("tests")
    for file in files:
        if file.endswith(".py") and file not in ["audit.py", "verify_imports.py"]:
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                tree = ast.parse(content, filename=path)
                visitor = OutboundCallVisitor(path)
                visitor.visit(tree)
                for line, url in visitor.violations:
                    print(f"[!] CRITICAL: Unauthorized outbound network request in Backend: {path}:{line} -> {url}")
                    failed = True
            except Exception as e:
                print(f"[!] Error parsing AST of {path}: {e}")
                failed = True

# Frontend TS/JS scanner
# Better regex to handle fetch calls (though proper AST is better, this is an improvement)
ts_fetch_pattern = re.compile(r"fetch\s*\(\s*(['\"`][^'\"]+['\"`]|\w+)", re.IGNORECASE)
for root, dirs, files in os.walk(frontend_src_dir):
    if "node_modules" in dirs:
        dirs.remove("node_modules")
    for file in files:
        if file.endswith((".ts", ".tsx", ".js", ".jsx", ".html")):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                for match in ts_fetch_pattern.finditer(content):
                    arg = match.group(1).strip()
                    # Stricter checks for frontend fetch urls
                    is_safe = False
                    if "API_BASE_URL" in arg:
                        is_safe = True
                    elif arg.startswith(("'", '"', "`")):
                        val = arg[1:-1]
                        if val.startswith("/") or val.startswith("./") or val.startswith("../"):
                            is_safe = True
                        elif any(val.startswith(p) for p in ["http://localhost", "http://127.0.0.1"]):
                            is_safe = True
                        
                    if is_safe:
                        pass
                    else:
                        line_num = content[:match.start()].count("\n") + 1
                        print(f"[!] CRITICAL: Unauthorized outbound fetch in Frontend: {path}:{line_num} -> fetch({arg})")
                        failed = True
            except Exception as e:
                print(f"[!] Error scanning {path}: {e}")

if failed:
    print("[!] Audit Failed. Security perimeter violations found.")
    sys.exit(1)
else:
    print("[+] Audit Passed. Zero-Trust perimeter is secure.")
    sys.exit(0)
