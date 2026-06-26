"""
PDF / DOCX 추출기
 - PDF  :
   · PyMuPDF    → 페이지 내 이미지 오브젝트 감지 + PPStructureV3 OCR
   · Docling    → 텍스트/표 레이아웃 분석 (PICTURE/CHART 무시)
   · pypdfium2  → 텍스트 레이어 추출
   (이미지 영역은 PyMuPDF만, 텍스트·표는 Docling만 처리 — 역할 분리)
 - DOCX : Docling (레이아웃 + 텍스트 + 표)
"""

import gc
import re

import cv2
import fitz
import numpy as np
import pypdfium2 as pdfium
from paddleocr import PaddleOCR, PPStructureV3

from app.ocr.paddleocr_engine import blocks_to_markdown
from app.ocr.utils import BATCH_SIZE, OCR_ZOOM, clean_text

MIN_IMAGE_PX = 50  # 이보다 작은 이미지는 아이콘/장식으로 판단 → 스킵
MIN_IMAGE_TEXT_CHARS = 10  # 이미지 bbox 안에 이 글자 수 이상 텍스트 레이어가 있으면 OCR 스킵

_basic_ocr_instance: PaddleOCR | None = None


def _get_basic_ocr() -> PaddleOCR:
    global _basic_ocr_instance
    if _basic_ocr_instance is None:
        _basic_ocr_instance = PaddleOCR(use_textline_orientation=True, lang="korean")
    return _basic_ocr_instance


def _basic_ocr_arr(img_bgr) -> str:
    """차트/인포그래픽 등 PPStructureV3로 추출 실패 시 기본 PaddleOCR 폴백."""
    ocr = _get_basic_ocr()
    lines = []
    for res in ocr.predict(img_bgr):
        for text, score in zip(res.get("rec_texts", []), res.get("rec_scores", [])):
            if score >= 0.4 and text.strip():
                lines.append(text.strip())
    return "\n".join(lines)


def _escape_dash_lines(text: str) -> str:
    """마크다운 수평선/제목 밑줄로 오해석될 수 있는 대시 줄 이스케이프."""
    return re.sub(r"^(-{3,})$", r"\\\1", text, flags=re.MULTILINE)


# ── pypdfium2: bbox 영역 텍스트 추출 ─────────────────────────────────────────
def extract_text_with_pypdfium2(pdf_pdfium, item) -> str:
    try:
        if not item.prov:
            return ""
        prov = item.prov[0]
        bbox = prov.bbox
        page = pdf_pdfium[prov.page_no - 1]
        textpage = page.get_textpage()
        text = textpage.get_text_bounded(
            left=bbox.l,
            bottom=bbox.b,
            right=bbox.r,
            top=bbox.t,
        )
        textpage.close()
        return text.strip()
    except Exception:
        return ""


# ── Docling PDF 배치 변환 ─────────────────────────────────────────────────────
def convert_pdf_batch(pdf_path: str, batch_pages: list):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False

    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)})
    result = converter.convert(
        pdf_path,
        page_range=(min(batch_pages), max(batch_pages)),
    )
    return result.document


# ── PyMuPDF 이미지 감지 + PPStructureV3 OCR ───────────────────────────────────
def _ocr_page_images(pipeline, page, page_no: int, pdf_doc_pdfium=None) -> list[tuple]:
    """페이지 내 이미지 오브젝트를 PyMuPDF로 감지 후 PPStructureV3 OCR.
    pdf_doc_pdfium 전달 시 이미지 bbox 영역에 텍스트 레이어가 있으면 해당 이미지 스킵.
    반환값: [(y_fitz, x_fitz, markdown_str), ...]
    """
    results = []
    seen_xrefs = set()
    page_height = page.rect.height

    for img_info in page.get_image_info(xrefs=True):
        xref = img_info.get("xref", -1)
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)

        bbox = img_info.get("bbox")
        if not bbox:
            continue
        x0, y0, x1, y1 = bbox
        if (x1 - x0) < MIN_IMAGE_PX or (y1 - y0) < MIN_IMAGE_PX:
            continue

        # 이미지 bbox 영역에 텍스트 레이어가 이미 있으면 스킵 (중복 방지)
        if pdf_doc_pdfium is not None:
            try:
                pdfium_page = pdf_doc_pdfium[page_no - 1]
                textpage = pdfium_page.get_textpage()
                # PyMuPDF(상단 원점) → PDF(하단 원점) 좌표 변환
                text_in_bbox = textpage.get_text_bounded(
                    left=x0,
                    bottom=page_height - y1,
                    right=x1,
                    top=page_height - y0,
                )
                textpage.close()
                if len(text_in_bbox.strip()) >= MIN_IMAGE_TEXT_CHARS:
                    print(f"  Page {page_no} [IMAGE] bbox에 텍스트 레이어 있음 → 스킵")
                    continue
            except Exception:
                pass

        rect = fitz.Rect(x0, y0, x1, y1) & page.rect
        if rect.is_empty:
            continue

        pix = page.get_pixmap(matrix=fitz.Matrix(OCR_ZOOM, OCR_ZOOM), clip=rect)
        img_arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        if pix.n == 4:
            img_arr = img_arr[:, :, :3]
        img_bgr = cv2.cvtColor(img_arr, cv2.COLOR_RGB2BGR)
        pix = None

        ocr_results = list(pipeline.predict(img_bgr))
        gc.collect()

        got_result = False
        for res in ocr_results:
            parsing_res_list = res.get("parsing_res_list", [])
            md = blocks_to_markdown(parsing_res_list)
            if md:
                print(f"  Page {page_no} [IMAGE] OCR 성공!")
                results.append((y0, x0, md + "\n\n"))
                got_result = True

        # PPStructureV3로 아무것도 못 읽으면 (차트/인포그래픽 등) 기본 OCR 폴백
        if not got_result:
            fallback_text = _basic_ocr_arr(img_bgr)
            if fallback_text:
                print(f"  Page {page_no} [IMAGE] 기본 OCR 폴백 성공!")
                results.append((y0, x0, fallback_text + "\n\n"))

        img_bgr = None

    return results


# ── 페이지 경계 분리 표 병합 ────────────────────────────────────────────────────
def _col_count(table_block: str) -> int:
    """마크다운 표의 열 수 (구분선 제외 첫 번째 행 기준)."""
    for line in table_block.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        if not set(s.replace("|", "").replace("-", "").replace(":", "").replace(" ", "")):
            continue  # 구분선 → 스킵
        return s.count("|") - 1
    return 0


def _strip_separators(block: str) -> str:
    """구분선(|---|) 행만 제거, 데이터 행은 모두 보존."""
    lines = block.splitlines(keepends=True)
    result = []
    for line in lines:
        s = line.strip()
        if s.startswith("|") and not set(s.replace("|", "").replace("-", "").replace(":", "").replace(" ", "")):
            continue
        result.append(line)
    return "".join(result)


def _collapse_colspan_headers(md: str) -> str:
    """헤더 행에 연속 중복 셀(colspan 반복)이 있으면 그룹별로 축약하고 데이터 셀도 병합."""
    lines = md.splitlines(keepends=True)

    def parse_cells(line: str) -> list[str] | None:
        s = line.strip()
        if not s.startswith("|"):
            return None
        parts = s.split("|")
        return [c.strip() for c in parts[1:-1]]

    def is_sep_row(cells: list[str]) -> bool:
        return bool(cells) and all(not set(c.replace("-", "").replace(":", "").replace(" ", "")) for c in cells)

    # 첫 번째 비구분선 행 = 헤더 행
    hdr_idx: int | None = None
    hdr_cells: list[str] = []
    for i, ln in enumerate(lines):
        cells = parse_cells(ln)
        if cells is not None and not is_sep_row(cells):
            hdr_idx = i
            hdr_cells = cells
            break
    if hdr_idx is None:
        return md

    # 연속 중복 그룹 계산
    groups: list[tuple[str, list[int]]] = []
    for ci, cell in enumerate(hdr_cells):
        if groups and groups[-1][0] == cell:
            groups[-1][1].append(ci)
        else:
            groups.append((cell, [ci]))

    # 중복 없으면 변환 불필요
    if all(len(g[1]) == 1 for g in groups):
        return md

    new_hdr = "| " + " | ".join(g[0] for g in groups) + " |"
    new_sep = "| " + " | ".join("---" for _ in groups) + " |"

    out: list[str] = []
    sep_pending = False
    for i, ln in enumerate(lines):
        cells = parse_cells(ln)
        if cells is None:
            out.append(ln)
            sep_pending = False
            continue
        if is_sep_row(cells):
            if sep_pending:
                out.append(new_sep + "\n")
                sep_pending = False
            else:
                out.append(ln)
            continue
        if i == hdr_idx:
            out.append(new_hdr + "\n")
            sep_pending = True
            continue
        # 데이터 행: 같은 그룹 내 셀 합치기
        if len(cells) == len(hdr_cells):
            merged = [" ".join(cells[j] for j in idx_list if cells[j].strip()) for _, idx_list in groups]
            out.append("| " + " | ".join(merged) + " |\n")
        else:
            out.append(ln)

    return "".join(out)


def _dedup_table_rows(md: str) -> str:
    """마크다운 표에서 연속 중복 행 제거 (colspan 반복 헤더 보정)."""
    lines = md.splitlines(keepends=True)
    result = []
    prev_normalized: str | None = None
    for line in lines:
        s = line.strip()
        if s.startswith("|") and not set(s.replace("|", "").replace("-", "").replace(":", "").replace(" ", "")):
            # 구분선 → 항상 통과, 이전 행 비교 리셋
            result.append(line)
            prev_normalized = None
            continue
        if s.startswith("|"):
            normalized = re.sub(r"\s+", " ", s)
            if normalized == prev_normalized:
                continue  # 직전 행과 동일 → 제거
            prev_normalized = normalized
        else:
            prev_normalized = None
        result.append(line)
    return "".join(result)


def _merge_split_tables(blocks: list[str]) -> list[str]:
    """연속된 동일 열 수 표를 하나로 합침 (Docling 페이지 경계 분리 보정).

    두 번째 블록은 구분선만 제거하고 데이터 행은 그대로 이어붙임.
    열 수가 다르거나 중간에 줄글/제목이 있으면 병합하지 않음.
    """

    def is_table(b: str) -> bool:
        return b.lstrip().startswith("|")

    merged: list[str] = []
    for block in blocks:
        if merged and is_table(merged[-1]) and is_table(block) and _col_count(merged[-1]) == _col_count(block) and _col_count(block) > 0:
            continuation = _strip_separators(block).strip()
            if continuation:
                merged[-1] = merged[-1].rstrip("\n") + "\n" + continuation + "\n\n"
        else:
            merged.append(block)
    return merged


# ── PDF 처리 ──────────────────────────────────────────────────────────────────
def process_pdf(pdf_path: str, page_filter: set = None, cancel_check=None) -> list[str]:
    pipeline = PPStructureV3(
        lang="korean",
        use_table_recognition=True,
        use_formula_recognition=False,
        use_chart_recognition=False,
        use_seal_recognition=False,
    )
    pdf_doc = fitz.open(pdf_path)
    pdf_doc_pdfium = pdfium.PdfDocument(pdf_path)
    total_pages = len(pdf_doc_pdfium)
    blocks = []

    if page_filter:
        batches = [sorted(page_filter)]
    else:
        all_pages = list(range(1, total_pages + 1))
        batches = [all_pages[i : i + BATCH_SIZE] for i in range(0, len(all_pages), BATCH_SIZE)]

    for batch_idx, batch_pages in enumerate(batches):
        if cancel_check and cancel_check():
            raise InterruptedError("cancelled")
        print(f"  배치 {batch_idx + 1}/{len(batches)}  페이지 {batch_pages}")

        # page_no → [(y_fitz, x_fitz, content), ...]
        page_contents = {p: [] for p in batch_pages}
        page_heights: dict[int, float] = {}

        # ── Step 1: PyMuPDF로 이미지 감지 + PPStructureV3 OCR ──
        for page_no in batch_pages:
            page = pdf_doc.load_page(page_no - 1)
            page_heights[page_no] = page.rect.height
            img_results = _ocr_page_images(pipeline, page, page_no, pdf_doc_pdfium)
            page_contents[page_no].extend(img_results)

        # ── Step 2: Docling으로 텍스트/표 추출 (PICTURE/CHART 무시) ──
        try:
            doc = convert_pdf_batch(pdf_path, batch_pages)
        except Exception as e:
            print(f"  변환 실패 → skip: {e}")
            gc.collect()
            for page_no in batch_pages:
                for _, _, content in sorted(page_contents[page_no], key=lambda x: (x[0], x[1])):
                    blocks.append(content)
            continue

        for item, _ in doc.iterate_items():
            if not item.prov:
                continue
            prov = item.prov[0]
            page_no = prov.page_no
            if page_filter and page_no not in page_filter:
                continue

            label = item.label.name

            # 이미지 관련 레이블은 PyMuPDF+PPStructureV3가 처리하므로 무시
            # 머리말/꼬리말 제외
            if label in ("PICTURE", "CHART", "FIGURE", "HEADER", "FOOTER"):
                continue

            bbox = prov.bbox
            y_fitz = page_heights.get(page_no, 842) - bbox.t
            x_fitz = bbox.l

            if label in ["TEXT", "CAPTION", "PARAGRAPH", "TITLE", "DOCUMENT_INDEX", "SECTION_HEADER", "LIST_ITEM", "FOOTNOTE"]:
                text = extract_text_with_pypdfium2(pdf_doc_pdfium, item)
                if not text:
                    text = getattr(item, "text", None) or ""
                if text:
                    if label in ("SECTION_HEADER", "TITLE"):
                        content = f"### {clean_text(text)}\n\n"
                    elif label == "LIST_ITEM":
                        content = f"{clean_text(text)}\n"
                    elif label == "FOOTNOTE":
                        content = f"각주) {clean_text(text)}\n\n"
                    else:
                        content = f"{_escape_dash_lines(clean_text(text))}\n\n"
                    page_contents[page_no].append((y_fitz, x_fitz, content))

            elif label == "TABLE":
                if hasattr(item, "export_to_markdown"):
                    md = item.export_to_markdown(doc=doc)
                    md = _dedup_table_rows(_collapse_colspan_headers(_escape_dash_lines(md.replace("~", "\\~"))))
                    content = f"\n{md}\n\n"
                    page_contents[page_no].append((y_fitz, x_fitz, content))

        del doc
        gc.collect()

        # ── Step 3: 페이지별 위치 순(위→아래, 좌→우)으로 정렬 후 수집 ──
        # 같은 줄(y좌표 ±5pt)의 줄글은 띄어쓰기로 이어붙임
        for page_no in batch_pages:
            sorted_items = sorted(page_contents[page_no], key=lambda x: (x[0], x[1]))
            merged: list[tuple] = []
            for y, x, content in sorted_items:
                stripped = content.lstrip()
                is_prose = not stripped.startswith("###") and not stripped.startswith("|")
                if merged and is_prose:
                    prev_y, prev_x, prev_content = merged[-1]
                    prev_stripped = prev_content.lstrip()
                    prev_is_prose = not prev_stripped.startswith("###") and not prev_stripped.startswith("|")
                    if prev_is_prose and abs(y - prev_y) <= 5:
                        merged[-1] = (prev_y, prev_x, prev_content.rstrip("\n") + " " + stripped)
                    else:
                        merged.append((y, x, content))
                else:
                    merged.append((y, x, content))
            for _, _, content in merged:
                blocks.append(content)

    pdf_doc.close()
    pdf_doc_pdfium.close()
    return _merge_split_tables(blocks)


# ── DOCX 처리 ─────────────────────────────────────────────────────────────────
def process_docx(file_path: str, page_filter: set = None, cancel_check=None) -> list[str]:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        raise ImportError("pip install docling")

    print("  Docling으로 DOCX 파싱 중...")

    pipeline = PPStructureV3(
        lang="korean",
        use_table_recognition=True,
        use_formula_recognition=False,
        use_chart_recognition=False,
        use_seal_recognition=False,
    )

    try:
        converter = DocumentConverter()
        result = converter.convert(file_path)
        doc = result.document
        blocks = []

        # TABLE 항목의 level을 추적해 그 하위 TEXT만 스킵 (테이블 셀 중복 방지)
        # level이 낮아지면(table scope 탈출) 자동으로 해제
        _in_table_level: int | None = None

        for item, level in doc.iterate_items():
            if cancel_check and cancel_check():
                raise InterruptedError("cancelled")
            if page_filter and item.prov:
                if item.prov[0].page_no not in page_filter:
                    continue
            label = item.label.name
            text = getattr(item, "text", None) or ""

            # TABLE scope 종료 감지 (같은 레벨이나 상위 레벨로 복귀)
            if _in_table_level is not None and level <= _in_table_level:
                _in_table_level = None

            if label == "TABLE":
                _in_table_level = level  # TABLE scope 진입

            # TABLE scope 내부 TEXT는 export_to_markdown에 포함 → 스킵
            if _in_table_level is not None and level > _in_table_level and label in ("TEXT", "CAPTION", "PARAGRAPH", "DOCUMENT_INDEX"):
                continue

            if label in ("TEXT", "CAPTION", "PARAGRAPH", "DOCUMENT_INDEX"):
                if text:
                    blocks.append(f"{_escape_dash_lines(clean_text(text))}\n\n")
            elif label in ("SECTION_HEADER", "TITLE"):
                if text:
                    blocks.append(f"### {clean_text(text)}\n\n")
            elif label == "LIST_ITEM":
                if text:
                    blocks.append(f"{clean_text(text)}\n")
            elif label == "TABLE":
                if hasattr(item, "export_to_markdown"):
                    md = _dedup_table_rows(_collapse_colspan_headers(_escape_dash_lines(item.export_to_markdown(doc=doc))))
                    blocks.append(f"\n{md}\n\n")
            elif label == "PICTURE":
                img_ref = getattr(item, "image", None)
                pil_img = getattr(img_ref, "pil_image", None) if img_ref else None
                if pil_img is not None:
                    img_bgr = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
                    ocr_results = list(pipeline.predict(img_bgr))
                    img_bgr = None
                    gc.collect()
                    for res in ocr_results:
                        md = blocks_to_markdown(res.get("parsing_res_list", []))
                        if md:
                            blocks.append(md + "\n\n")
                else:
                    print("  [PICTURE] 이미지 데이터 없음 → 스킵")

        print(f"  Docling DOCX 완료 ({len(blocks)}개 블록)")
        return blocks
    except Exception as e:
        print(f"  Docling DOCX 오류: {e}")
        return [f"[Docling DOCX 파싱 실패: {e}]\n\n"]


# ── 공개 인터페이스 ───────────────────────────────────────────────────────────
def extract(file_path: str, pages: list = None, cancel_check=None) -> str:
    """
    PDF 또는 DOCX 파일에서 마크다운 텍스트 추출.

    Args:
        file_path : PDF 또는 DOCX 파일 경로
        pages     : PDF 전용 페이지 필터 (1-indexed). None이면 전체.

    Returns:
        마크다운 문자열
    """
    from pathlib import Path

    ext = Path(file_path).suffix.lower()

    if ext == ".pdf":
        page_filter = set(pages) if pages else None
        return "".join(process_pdf(file_path, page_filter, cancel_check))
    if ext == ".docx":
        page_filter = set(pages) if pages else None
        return "".join(process_docx(file_path, page_filter, cancel_check))
    raise ValueError(f"지원하지 않는 포맷: {ext} (pdf, docx만 가능)")
