"""
문서 추출 진입점
확장자 확인 후 적절한 추출기로 라우팅

사용 예시:
    process_document("path/to/file.hwp")
    process_document(tmp_path) : fastApi로 받아온 파일

명령어 :
    backend 디렉토리에서
    # PDF
    python -m app.ocr.extractor "C:/Users/2class_8/Downloads/문서.pdf"

    # PDF 특정 페이지만
    python -m app.ocr.extractor "C:/Users/2class_8/Downloads/문서.pdf" 1,2,3

    # HWP
    python -m app.ocr.extractor "C:/Users/2class_8/Downloads/문서.hwp"

지원 포맷:
    .pdf  .docx               → extractor_pdf_docx.py  (Docling + pypdfium2 + PaddleOCR)
    .doc                      → extractor_doc.py        (LlamaParse)
    .hwp  .hwpx               → extractor_hwp.py        (rhwp-python + PaddleOCR)
    .png  .jpg  .jpeg  .webp  → paddleocr_test.py       (PPStructureV3)
"""

import sys
from pathlib import Path

from app.ocr.utils import SUPPORTED_EXTENSIONS


def process_document(file_path: str, pages: list = None, cancel_check=None) -> str:
    """
    확장자에 맞는 추출기를 호출하고 마크다운 문자열 반환.

    Args:
        file_path : 문서 경로
        pages     : PDF 전용 페이지 필터 (1-indexed 리스트). None이면 전체.
                    예) [3, 4] → 3, 4페이지만

    Returns:
        마크다운 형식의 추출 텍스트.
        지원하지 않는 포맷이면 빈 문자열("") 반환.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    print(f"\n처리 시작: {path.name}  [{ext.upper()}]")

    # ── PDF / DOCX ────────────────────────────────────────────────────────────
    if ext in (".pdf", ".docx"):
        from app.ocr.extractor_pdf_docx import extract

        if ext == ".pdf":
            print("  엔진: Docling + pypdfium2 + paddleocr")
        else:
            print("  엔진: Docling")
        result = extract(file_path, pages=pages, cancel_check=cancel_check)
        print(result)
        return result
        # return extract(file_path, pages=pages)

    # ── DOC ───────────────────────────────────────────────────────────────────
    elif ext == ".doc":
        from app.ocr.extractor_doc import extract

        print("  엔진: LlamaParse")
        result = extract(file_path)
        print(result)
        return result

    # ── HWP / HWPX ───────────────────────────────────────────────────────────
    elif ext in (".hwp", ".hwpx"):
        from app.ocr.extractor_hwp import extract

        print("  엔진: rhwp-python + paddleocr")
        return extract(file_path)

    # ── 이미지 ────────────────────────────────────────────────────────────────
    elif ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"):
        from app.ocr.paddleocr_engine import extract

        print("  엔진: PPStructureV3 (PaddleOCR)")
        return extract(file_path)

    # ── 미지원 포맷 ───────────────────────────────────────────────────────────
    else:
        print(f"  지원하지 않는 포맷: {ext}")
        print(f"  지원 포맷: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        return ""


# ── CLI 실행 ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "test2.pdf")
    pages = None
    if len(sys.argv) > 2:
        pages = [int(p) for p in sys.argv[2].split(",")]

    markdown = process_document(path, pages=pages)

    if markdown:
        print(f"\n--- 추출 결과 미리보기 ({len(markdown):,} chars) ---")
        print(markdown)
        # print("..." if len(markdown) > 500 else "")

        out = Path(path).with_suffix(".md").name
        Path(out).write_text(markdown, encoding="utf-8")
        print(f"\n저장: {out}")
