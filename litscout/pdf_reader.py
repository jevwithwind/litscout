"""litscout.pdf_reader — Extract text from PDF files."""

import logging
import os
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def extract_pages(pdf_path: str) -> dict[str, Any]:
    """Extract text from a PDF file page by page.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        A dict with:
            - "success": bool indicating if extraction succeeded
            - "total_pages": int, total number of pages in the PDF
            - "pages": list of dicts with "page_num" and "text" keys
            - "error": str (only if success is False)

    Note:
        Pages with less than 50 characters are skipped (likely images/charts).
    """
    result: dict[str, Any] = {
        "success": False,
        "total_pages": 0,
        "pages": [],
    }

    if not os.path.exists(pdf_path):
        result["error"] = f"File not found: {pdf_path}"
        logger.warning(result["error"])
        return result

    try:
        doc = fitz.open(pdf_path)
        result["total_pages"] = len(doc)

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()

            # Skip pages with very little text (likely images/charts)
            if len(text.strip()) < 50:
                logger.debug(
                    "Skipping page %d (too little text: %d chars)",
                    page_num + 1,
                    len(text),
                )
                continue

            result["pages"].append({
                "page_num": page_num + 1,
                "text": text,
            })

        doc.close()

        if result["pages"]:
            result["success"] = True
            logger.info(
                "Extracted %d pages from %s (total: %d pages)",
                len(result["pages"]),
                pdf_path,
                result["total_pages"],
            )
        else:
            result["error"] = "No readable text found in PDF"
            logger.warning(result["error"])

    except fitz.FileDataError as e:
        result["error"] = f"Corrupted or password-protected PDF: {e}"
        logger.warning(result["error"])
    except Exception as e:
        result["error"] = f"Error reading PDF: {e}"
        logger.error("Error reading PDF %s: %s", pdf_path, e)

    return result
