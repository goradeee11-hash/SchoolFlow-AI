"""
security_scan.py
----------------
Static secret-detection scan for SchoolFlow AI project files.
Prints ONLY: filename, line number, finding type, severity.
Never prints the matched content or secret values.
"""

import re
import os
import sys

PATTERNS = [
    ("CRITICAL", "GitHub PAT (ghp_)",          r"ghp_[A-Za-z0-9]{36,}"),
    ("CRITICAL", "GitHub fine-grained PAT",     r"github_pat_[A-Za-z0-9_]{80,}"),
    ("CRITICAL", "OpenAI key (sk-)",            r"sk-[A-Za-z0-9]{32,}"),
    ("CRITICAL", "AWS access key",              r"AKIA[0-9A-Z]{16}"),
    ("CRITICAL", "Private key block",           r"-----BEGIN\s+(RSA|EC|OPENSSH|PRIVATE)"),
    ("CRITICAL", "Password hardcoded",          r"password\s*=\s*['\"][^'\"]{4,}"),
    ("HIGH",     "API Key (generic)",           r"api[_-]?key\s*=\s*['\"][^'\"]{8,}"),
    ("HIGH",     "Secret/token variable",       r"(secret|token|auth)\s*=\s*['\"][^'\"]{8,}"),
    ("HIGH",     "Bearer token",                r"Bearer\s+[A-Za-z0-9\-_\.]{20,}"),
    ("HIGH",     "SMTP credentials",            r"smtp[_.](host|user|pass|port)\s*="),
    ("HIGH",     "Database URL",                r"(postgres|mysql|mongodb|redis)://\S+"),
    ("MEDIUM",   "Email address in code",       r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
    ("LOW",      "Hardcoded localhost URL",     r"http://localhost:[0-9]{4,5}"),
    ("LOW",      "Hardcoded IP address",        r"\b(?:192\.168|10\.|172\.(1[6-9]|2[0-9]|3[01]))\.\d+\.\d+\b"),
]

EXTENSIONS = {".py", ".txt", ".md", ".toml", ".cfg", ".ini", ".env"}
EXCLUDE_DIRS = {".venv", "__pycache__", ".git"}

def scan_dir(root):
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in EXTENSIONS:
                continue
            fpath = os.path.join(dirpath, fname)
            rel   = os.path.relpath(fpath, root)
            try:
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        for severity, name, pattern in PATTERNS:
                            if re.search(pattern, line, re.IGNORECASE):
                                results.append((rel, lineno, name, severity))
            except Exception:
                pass
    return results

root = os.path.dirname(os.path.abspath(__file__))
findings = scan_dir(root)

SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
findings.sort(key=lambda x: (SEV_ORDER.get(x[3], 9), x[0], x[1]))

print("\n=== SchoolFlow AI - Security Scan Results ===\n")
if not findings:
    print("  No secret patterns detected in any project file.")
else:
    fmt = "{:<45} {:>6}   {:<12}   {}"
    print(fmt.format("File", "Line", "Severity", "Finding"))
    print("-" * 90)
    for rel, lineno, name, severity in findings:
        print(fmt.format(rel, lineno, severity, name))

print(f"\nTotal findings: {len(findings)}")
print("NOTE: Only filename, line number, and finding type are shown.")
print("      No secret values were printed.\n")
sys.exit(0 if not findings else 1)
