
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger

logger = get_logger("aggregator")

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

SEVERITY_EMOJI = {
    "CRITICAL": "🔴",
    "HIGH":     "🟠",
    "MEDIUM":   "🟡",
    "LOW":      "🔵",
}


def _lines_overlap(start1: int, end1: int, start2: int, end2: int) -> bool:
    
    return not (end1 < start2 or end2 < start1)


def deduplicate(findings: list[dict]) -> list[dict]:

    unique = []
    for f in findings:
        is_dup = False
        for u in unique:
            if (
                f.get("file_path") == u.get("file_path")
                and _lines_overlap(
                    f.get("line_start", 0), f.get("line_end", 0),
                    u.get("line_start", 0), u.get("line_end", 0),
                )
            ):
                
                if SEVERITY_ORDER.get(f.get("severity", "LOW"), 3) < \
                   SEVERITY_ORDER.get(u.get("severity", "LOW"), 3):
                    unique.remove(u)
                    unique.append(f)
                is_dup = True
                break
        if not is_dup:
            unique.append(f)
    return unique


def sort_by_severity(findings: list[dict]) -> list[dict]:
   
    return sorted(
        findings,
        key=lambda f: SEVERITY_ORDER.get(f.get("severity", "LOW"), 3),
    )


def build_markdown(findings: list[dict], repo: str, pr_number: int) -> str:

    if not findings:
        return (
            "## CodeSentinel AI Review ✅\n\n"
            "**No issues found** — looks good!\n\n"
            f"*Reviewed by CodeSentinel AI | {repo}#{pr_number}*"
        )

    critical = sum(1 for f in findings if f.get("severity") == "CRITICAL")
    high     = sum(1 for f in findings if f.get("severity") == "HIGH")
    medium   = sum(1 for f in findings if f.get("severity") == "MEDIUM")
    low      = sum(1 for f in findings if f.get("severity") == "LOW")

    
    lines = [
        "## CodeSentinel AI Review",
        "",
        f"**{len(findings)} issue{'s' if len(findings) > 1 else ''} found**",
    ]

   
    summary_parts = []
    if critical: summary_parts.append(f"🔴 {critical} critical")
    if high:     summary_parts.append(f"🟠 {high} high")
    if medium:   summary_parts.append(f"🟡 {medium} medium")
    if low:      summary_parts.append(f"🔵 {low} low")
    if summary_parts:
        lines.append(f"*{', '.join(summary_parts)}*")

    lines.append("")

    for f in findings:
        severity = f.get("severity", "MEDIUM")
        emoji    = SEVERITY_EMOJI.get(severity, "⚪")
        f_type   = f.get("finding_type", "issue").replace("_", " ").title()

        lines.append(f"### {emoji} {severity} — {f_type}")
        lines.append(f"**File:** `{f.get('file_path', 'unknown')}` "
                     f"(lines {f.get('line_start', '?')}–{f.get('line_end', '?')})")
        lines.append(f"**Issue:** {f.get('description', '')}")
        lines.append(f"**Fix:** {f.get('fix_suggestion', '')}")

       
        if f.get("owasp_category"):
            lines.append(f"**OWASP:** {f['owasp_category']}")
        if f.get("cwe_id"):
            lines.append(f"**CWE:** {f['cwe_id']}")
        if f.get("estimated_impact"):
            lines.append(f"**Impact:** {f['estimated_impact']}")

        conf = f.get("confidence", 0)
        lines.append(f"**Confidence:** {conf:.0%}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"*CodeSentinel AI | {repo}#{pr_number}*")
    return "\n".join(lines)


def aggregate_findings(
    bug_findings:      list[dict],
    security_findings: list[dict],
    perf_findings:     list[dict],
    repo:              str,
    pr_number:         int,
) -> dict:

    all_raw = bug_findings + security_findings + perf_findings
    logger.info(
        f"Aggregating: {len(bug_findings)} bugs + "
        f"{len(security_findings)} security + "
        f"{len(perf_findings)} perf = {len(all_raw)} total"
    )

    
    deduped = deduplicate(all_raw)
    logger.info(f"After dedup: {len(deduped)} unique findings")

    
    sorted_findings = sort_by_severity(deduped)

    
    markdown = build_markdown(sorted_findings, repo, pr_number)

  
    has_critical = any(f.get("severity") == "CRITICAL" for f in sorted_findings)

    return {
        "all_findings":      sorted_findings,
        "findings_markdown": markdown,
        "has_critical":      has_critical,
        "total_findings":    len(sorted_findings),
    }
