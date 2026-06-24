"""RAG 성능 평가 API 라우터 (RAGAS 기반)"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

router = APIRouter(prefix="/evaluation", tags=["evaluation"])
_executor = ThreadPoolExecutor(max_workers=1)  # 평가는 순차 실행


# ── 요청/응답 스키마 ────────────────────────────────────────────────────────────
class EvaluationRequest(BaseModel):
    questions: list[str]
    ground_truths: Optional[list[str]] = None
    user_id: Optional[int] = None

    @field_validator("questions")
    @classmethod
    def questions_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("questions 가 비어 있습니다")
        return v

    @field_validator("ground_truths")
    @classmethod
    def gt_length_match(cls, v, info):
        if v is not None:
            qs = info.data.get("questions", [])
            if qs and len(v) != len(qs):
                raise ValueError("ground_truths 개수가 questions 개수와 일치해야 합니다")
        return v


# ── 엔드포인트 ──────────────────────────────────────────────────────────────────
@router.post(
    "/run",
    summary="RAG 파이프라인 성능 평가",
    description=(
        "RAGAS를 사용해 RAG 파이프라인을 평가합니다.\n\n"
        "**ground_truths 없이**: faithfulness, answer_relevancy 측정\n\n"
        "**ground_truths 포함**: 위 2개 + context_precision, context_recall 추가 측정"
    ),
)
async def run_evaluation(req: EvaluationRequest):
    """
    요청 예시:
    ```json
    {
      "questions": ["계약 해지 요건은?", "손해배상 기준은?"],
      "ground_truths": ["민법 544조에 따르면...", "실손해를 기준으로..."],
      "user_id": null
    }
    ```
    """
    from app.llm.evaluator import evaluate_rag

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor,
            lambda: evaluate_rag(
                questions=req.questions,
                ground_truths=req.ground_truths,
                user_id=req.user_id,
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"평가 실패: {e}") from e

    return result
