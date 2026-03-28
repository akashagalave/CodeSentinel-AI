# ingestion-pipeline/src/code_chunker.py
"""
Convert parsed AST function dicts into LangChain Documents.
Each function = one Document with rich metadata.

Why LangChain Documents?
  ChromaDB accepts LangChain Documents directly.
  Metadata stored separately from content → filterable queries.
  e.g. "find functions in flask/app.py with complexity > 5"
"""
import sys
from pathlib import Path

from langchain_core.documents import Document

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.logger import get_logger

logger = get_logger("code_chunker")


def function_to_document(fn: dict) -> Document:
    """
    Convert one function dict → LangChain Document.

    page_content: what gets embedded (function body + docstring)
    metadata: searchable fields (repo, file, complexity, lines, etc.)
    """
    # Build embeddable content
    content_parts = []

    # Include docstring as comment if present
    if fn.get("docstring"):
        content_parts.append(f"# {fn['full_name']}\n# {fn['docstring']}")

    # Body with surrounding context lines
    content_parts.append(fn.get("body_with_context", fn["body"]))

    page_content = "\n".join(content_parts)

    metadata = {
        "function_name":        fn["function_name"],
        "class_name":           fn.get("class_name") or "",
        "full_name":            fn["full_name"],
        "file_path":            fn["file_path"],
        "repo":                 fn.get("repo", "unknown"),
        "language":             fn["language"],
        "start_line":           fn["start_line"],
        "end_line":             fn["end_line"],
        "lines_count":          fn["lines_count"],
        "cyclomatic_complexity": fn["cyclomatic_complexity"],
        "is_async":             fn.get("is_async", False),
        "has_docstring":        bool(fn.get("docstring")),
        "params_count":         len(fn.get("params", [])),
    }

    return Document(page_content=page_content, metadata=metadata)


def build_documents(functions: list[dict]) -> list[Document]:
    """Convert list of function dicts to list of LangChain Documents."""
    docs = []
    skipped = 0

    for fn in functions:
        try:
            doc = function_to_document(fn)
            # Skip trivially short content
            if len(doc.page_content.strip()) < 50:
                skipped += 1
                continue
            docs.append(doc)
        except Exception as e:
            logger.warning(f"Failed to convert {fn.get('full_name', 'unknown')}: {e}")
            skipped += 1

    if skipped > 0:
        logger.info(f"Skipped {skipped} trivially short functions")

    return docs
