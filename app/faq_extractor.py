"""
FAQ Excel extractor for client-facing Q&A documents.

Reads an Excel file where:
  - Column A: Question  (e.g. "Will the folder/label structure be preserved?")
  - Column B: Answer/Response

The combination name (migration_display) is extracted from the file name:
  "Gmail to Outlook FAQ's.xlsx"  →  "Gmail to Outlook"
  "Slack to Teams FAQs.xlsx"     →  "Slack to Teams"

Each FAQ row becomes one LangChain Document with migration_display in metadata,
so the existing capabilities retrieval filter works automatically with zero changes.
"""

import os
import re
import io
import logging
from typing import List, Union

import pandas as pd
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

_SKIP_HEADERS = {"client faq", "question", "faq", "q", "query", "client question"}


def extract_combination_from_filename(file_name: str) -> str:
    """
    Extract the migration combination name from the Excel file name.

    Examples:
      "Gmail to Outlook FAQ's.xlsx"  →  "Gmail to Outlook"
      "Slack to Teams FAQs.xlsx"     →  "Slack to Teams"
      "Box to OneDrive.xlsx"         →  "Box to OneDrive"
    """
    name = os.path.splitext(file_name)[0]
    # Remove trailing FAQ / FAQ's / FAQs (case-insensitive)
    name = re.sub(r"(?i)\s*faq'?s?\s*$", "", name).strip()
    # Remove trailing hyphens, underscores, or spaces
    name = name.rstrip("-_ ")
    logger.debug("[faq_extractor] Filename '%s' → combination '%s'", file_name, name)
    return name


def _cell_str(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "") else s


def _open_excel(excel_source: Union[bytes, bytearray, str], file_name: str = "") -> pd.ExcelFile:
    """
    Open an Excel file trying multiple engines in order:
      1. openpyxl  — standard .xlsx (ZIP/OOXML format)
      2. xlrd      — old .xls binary format (BIFF), or .xlsx files saved by older Excel versions

    This handles the common case where a file has a .xlsx extension but is actually
    in the legacy .xls binary format, which causes a BadZipFile error with openpyxl.
    """
    buf = io.BytesIO(excel_source) if isinstance(excel_source, (bytes, bytearray)) else excel_source
    engine_errors: dict = {}

    for engine in ("openpyxl", "xlrd"):
        try:
            # Reset buffer position for each attempt (bytes only)
            if isinstance(buf, io.BytesIO):
                buf.seek(0)
            xl = pd.ExcelFile(buf, engine=engine)
            logger.info("[faq_extractor] Opened '%s' with engine='%s'", file_name, engine)
            return xl
        except Exception as e:
            engine_errors[engine] = str(e)
            logger.debug("[faq_extractor] Engine '%s' failed for '%s': %s", engine, file_name, e)

    raise ValueError(
        f"Could not open '{file_name}' with any Excel engine. "
        f"Tried: {engine_errors}. "
        f"Ensure the file is a valid .xlsx or .xls Excel workbook."
    )


def extract_faq_documents(
    excel_source: Union[bytes, bytearray, str],
    file_name: str,
) -> List[Document]:
    """
    Extract LangChain Documents from a FAQ Excel file.

    Args:
        excel_source: Either bytes/bytearray (from file upload) or a local file path string.
        file_name:    The original file name — used to derive combination name and stored
                      in metadata as ``source``.

    Returns:
        List of Documents. Each document represents one FAQ row with:
          page_content:  "Question: <question>\\nAnswer: <answer>"
          metadata:      migration_display, source, source_type, tag, sheet_name, content_type
    """
    documents: List[Document] = []
    combination = extract_combination_from_filename(file_name)

    logger.info(
        "[faq_extractor] ▶ Starting extraction | file='%s' | combination='%s' | "
        "source=%s",
        file_name,
        combination,
        "bytes upload" if isinstance(excel_source, (bytes, bytearray)) else "local path",
    )

    try:
        xl = _open_excel(excel_source, file_name)
        sheet_names = xl.sheet_names
        logger.info("[faq_extractor] Found %d sheet(s): %s", len(sheet_names), sheet_names)

        with xl:
            for sheet_name in sheet_names:
                try:
                    df = pd.read_excel(xl, sheet_name=sheet_name, header=0)
                except Exception as e:
                    logger.warning("[faq_extractor] Skipping sheet '%s': %s", sheet_name, e)
                    continue

                if df.empty:
                    logger.debug("[faq_extractor] Sheet '%s' is empty — skipped", sheet_name)
                    continue

                if len(df.columns) < 2:
                    logger.warning(
                        "[faq_extractor] Sheet '%s' has only %d column(s) — need at least 2 (Question + Answer), skipped",
                        sheet_name,
                        len(df.columns),
                    )
                    continue

                sheet_docs = 0
                skipped_blank = 0
                skipped_header = 0

                for row_idx, row in df.iterrows():
                    question = _cell_str(row.iloc[0]) if len(row) > 0 else ""
                    answer   = _cell_str(row.iloc[1]) if len(row) > 1 else ""

                    if not question or not answer:
                        skipped_blank += 1
                        continue

                    if question.lower() in _SKIP_HEADERS:
                        logger.debug(
                            "[faq_extractor] Row %d in sheet '%s': header row skipped ('%s')",
                            row_idx,
                            sheet_name,
                            question,
                        )
                        skipped_header += 1
                        continue

                    content = f"Question: {question}\nAnswer: {answer}"
                    doc = Document(
                        page_content=content,
                        metadata={
                            "source": file_name,
                            "source_type": "client_faq",
                            "migration_display": combination,
                            "sheet_name": sheet_name,
                            "tag": "faq",
                            "content_type": "client_faq",
                        },
                    )
                    documents.append(doc)
                    sheet_docs += 1

                logger.info(
                    "[faq_extractor] Sheet '%s': %d FAQ docs created | %d blank rows skipped | %d header rows skipped",
                    sheet_name,
                    sheet_docs,
                    skipped_blank,
                    skipped_header,
                )

    except Exception as e:
        logger.error("[faq_extractor] Failed to read '%s': %s", file_name, e, exc_info=True)

    logger.info(
        "[faq_extractor] ✓ Extraction complete | file='%s' | combination='%s' | total_docs=%d",
        file_name,
        combination,
        len(documents),
    )
    return documents
