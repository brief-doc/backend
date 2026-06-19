"""
HWP / HWPX 추출기
 - HWP/HWPX : rhwp-python (로컬, 한컴오피스 불필요)
 - 이미지 영역 : paddleocr

"""

import cv2
import numpy as np
from paddleocr import PPStructureV3

from app.ocr.paddleocr_engine import blocks_to_markdown
from app.ocr.utils import clean_text


def process_hwp(file_path: str, pipeline=None) -> list[str]:
    try:
        import rhwp
    except ImportError:
        raise ImportError("pip install rhwp-python")

    print("  rhwp-python으로 파싱 중...")
    try:
        doc = rhwp.parse(file_path)
        ir = doc.to_ir()
        blocks = []

        def cell_text(cell) -> str:
            """TableCell에서 텍스트 추출."""
            parts = []
            for b in getattr(cell, "blocks", None) or []:
                t = (getattr(b, "text", "") or "").strip()
                if t:
                    parts.append(t)
            return " ".join(parts)

        def process_block(block):
            kind = block.__class__.__name__

            # ── 단락 ─────────────────────────────────────────────────────────
            if kind == "ParagraphBlock":
                text = (getattr(block, "text", "") or "").strip()
                if not text:
                    return
                level = getattr(block, "outline_level", 0) or 0
                if level == 1:
                    blocks.append("## " + clean_text(text) + "\n\n")
                elif level >= 2:
                    blocks.append("### " + clean_text(text) + "\n\n")
                else:
                    blocks.append(clean_text(text) + "\n\n")

            # ── 리스트 항목 ───────────────────────────────────────────────────
            elif kind == "ListItemBlock":
                text = (getattr(block, "text", "") or "").strip()
                if text:
                    blocks.append(clean_text(text) + "\n")

            # ── 표 ───────────────────────────────────────────────────────────
            elif kind == "TableBlock":
                tbl_cells = getattr(block, "cells", []) or []
                if not tbl_cells:
                    return

                row_map = {}
                for tc in tbl_cells:
                    tr = getattr(tc, "row", 0)
                    tc_col = getattr(tc, "col", 0)
                    if tr not in row_map:
                        row_map[tr] = {}
                    row_map[tr][tc_col] = cell_text(tc)

                md_rows = []
                sorted_rows = sorted(row_map.keys())
                for row_idx, tr_idx in enumerate(sorted_rows):
                    sorted_cols = sorted(row_map[tr_idx].keys())
                    row_cells = [row_map[tr_idx][tc_idx] for tc_idx in sorted_cols]
                    md_rows.append("| " + " | ".join(row_cells) + " |")
                    if row_idx == 0:
                        md_rows.append("| " + " | ".join(["---"] * len(row_cells)) + " |")
                if md_rows:
                    blocks.append("\n" + "\n".join(md_rows) + "\n\n")

            # ── 이미지 → PPStructureV3 ───────────────────────────────────────
            elif kind == "PictureBlock":
                if pipeline is None:
                    return
                try:
                    img_bytes = doc.bytes_for_image(block)
                    if not img_bytes:
                        return
                    img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
                    img_bgr = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                    if img_bgr is None:
                        return
                    results = list(pipeline.predict(img_bgr))
                    img_bgr = None
                    for res in results:
                        md = blocks_to_markdown(res.get('parsing_res_list', []))
                        if md:
                            blocks.append(md + '\n\n')
                except Exception as img_e:
                    print("  이미지 OCR 실패: " + str(img_e))

        for block in ir.body:
            process_block(block)

        print("  rhwp-python 완료 (" + str(len(blocks)) + "개 블록)")
        return blocks

    except Exception as e:
        print("  rhwp-python 오류: " + str(e))
        import traceback

        traceback.print_exc()
        return ["[rhwp-python 파싱 실패: " + str(e) + "]\n\n"]


# ── 공개 인터페이스 ───────────────────────────────────────────────────────────
def extract(file_path: str, **kwargs) -> str:
    """
    HWP / HWPX 파일에서 마크다운 텍스트 추출.

    Args:
        file_path : HWP 또는 HWPX 파일 경로

    Returns:
        마크다운 문자열
    """
    from pathlib import Path

    ext = Path(file_path).suffix.lower()
    if ext not in (".hwp", ".hwpx"):
        raise ValueError(f"지원하지 않는 포맷: {ext} (hwp, hwpx만 가능)")

    pipeline = PPStructureV3(
        lang='korean',
        use_table_recognition=True,
        use_formula_recognition=False,
        use_chart_recognition=False,
        use_seal_recognition=False,
    )
    return "".join(process_hwp(file_path, pipeline=pipeline))
