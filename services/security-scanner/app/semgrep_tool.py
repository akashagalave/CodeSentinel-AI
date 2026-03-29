# services/security-scanner/app/semgrep_tool.py
"""
Semgrep OWASP scan as LangChain Tool.

Why Semgrep as a Tool (not standalone)?
  Semgrep = static analysis (rules-based, fast, no false positives on syntax)
  GPT-4o = semantic reasoning (understands context, can filter Semgrep FPs)
  Together: Semgrep finds candidates → GPT-4o validates them → better precision

Why LangChain Tool?
  Security agent can decide WHEN to call Semgrep based on diff content.
  Not every diff needs a full OWASP scan.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from langchain_core.tools import tool

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger

logger = get_logger("semgrep_tool")


@tool
def run_semgrep_scan(code: str, language: str = "python") -> str:
    """
    Run Semgrep OWASP Top 10 security scan on code.
    Returns JSON string of security findings.
    Use this to scan code for security vulnerabilities.
    """
    suffix = ".py" if language == "python" else ".js"

    try:
        # Write code to temp file — Semgrep needs a file path
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        ) as f:
            # Extract only added lines from diff (lines starting with +)
            if code.startswith("@@"):
                added_lines = [
                    line[1:]   # Remove the leading +
                    for line in code.split("\n")
                    if line.startswith("+") and not line.startswith("+++")
                ]
                f.write("\n".join(added_lines))
            else:
                f.write(code)
            temp_path = f.name

        # Run Semgrep with OWASP Top 10 rules
        result = subprocess.run(
            [
                "semgrep",
                "--config", "p/owasp-top-ten",   # OWASP rules
                "--config", "p/python",           # Python-specific rules
                "--json",                          # JSON output for parsing
                "--quiet",                         # No progress output
                "--no-git-ignore",                 # Scan temp file
                temp_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,   # 30 second timeout — don't block review
        )

        # Clean up temp file
        Path(temp_path).unlink(missing_ok=True)

        # Semgrep returns 0 (no findings) or 1 (findings found) — both are normal
        if result.returncode not in (0, 1):
            logger.warning(f"Semgrep error: {result.stderr[:200]}")
            return json.dumps({"findings": [], "error": result.stderr[:200]})

        if not result.stdout:
            return json.dumps({"findings": []})

        data = json.loads(result.stdout)
        findings = []

        for r in data.get("results", []):
            severity = r.get("extra", {}).get("severity", "WARNING")

            # Only include HIGH and CRITICAL severity findings
            # Filter out low-severity noise before sending to GPT-4o
            if severity not in ("ERROR", "WARNING"):
                continue

            metadata = r.get("extra", {}).get("metadata", {})
            findings.append({
                "rule_id":  r.get("check_id", ""),
                "severity": "HIGH" if severity == "ERROR" else "MEDIUM",
                "message":  r.get("extra", {}).get("message", ""),
                "line":     r.get("start", {}).get("line", 0),
                "owasp":    metadata.get("owasp", ""),
                "cwe":      metadata.get("cwe", ""),
            })

        logger.info(f"Semgrep found {len(findings)} potential issues")
        return json.dumps({"findings": findings[:10]})  # cap at 10

    except subprocess.TimeoutExpired:
        logger.warning("Semgrep timed out after 30s")
        return json.dumps({"findings": [], "error": "Semgrep timeout"})

    except Exception as e:
        logger.warning(f"Semgrep error: {e}")
        return json.dumps({"findings": [], "error": str(e)})
