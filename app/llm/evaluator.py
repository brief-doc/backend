"""RAGAS 기반 RAG 파이프라인 성능 평가 모듈 (ragas 0.4.x API)

평가 지표
---------
ground_truth 없이 측정 가능:
  - faithfulness      : 답변이 검색 컨텍스트에 충실한지 (0~1)
  - answer_relevancy  : 답변이 질문과 얼마나 관련 있는지 (0~1)

ground_truth 제공 시 추가 측정:
  - context_precision : 검색된 컨텍스트 중 관련 내용 비율 (0~1)
  - context_recall    : 정답을 컨텍스트가 얼마나 커버하는지 (0~1)

사용 예시
---------
from app.llm.evaluator import evaluate_rag

result = evaluate_rag(
    questions=["계약 해지 요건은?", "손해배상 기준은?"],
    ground_truths=["...", "..."],   # 생략 가능
)
print(result["metrics"])
"""

from __future__ import annotations

import math
from typing import Optional

from .config import CURRENT_MODEL, OLLAMA_EMBED_MODEL
from .pipeline import run_query


def _patch_vertexai() -> None:
    """ragas 0.4.x 가 langchain_community 0.4.x 에서 제거된 vertexai 모듈을
    참조하는 버그를 우회합니다 (Ollama 사용 시 vertexai 불필요)."""
    import sys
    from types import ModuleType

    mod_name = "langchain_community.chat_models.vertexai"
    if mod_name not in sys.modules:
        dummy = ModuleType(mod_name)

        class _Stub:  # 사용되지 않는 더미 클래스
            pass

        dummy.ChatVertexAI = _Stub  # type: ignore[attr-defined]
        sys.modules[mod_name] = dummy


def evaluate_rag(
    questions: list[str],
    ground_truths: Optional[list[str]] = None,
    user_id: Optional[int] = None,
) -> dict:
    """
    RAG 파이프라인 성능을 RAGAS로 평가합니다.

    Returns:
        {
            "metrics": {"faithfulness": 0.85, "answer_relevancy": 0.72, ...},
            "per_question": [{"question": ..., "answer": ..., "faithfulness": ...}, ...],
            "question_count": int,
            "ground_truth_provided": bool,
        }
    """
    # 1) vertexai 호환 패치 (ragas import 전에 반드시 실행)
    _patch_vertexai()

    # 2) ragas 관련 임포트 (startup segfault 방지를 위해 lazy)
    from langchain_ollama import ChatOllama, OllamaEmbeddings
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, ResponseRelevancy

    has_gt = bool(ground_truths and len(ground_truths) == len(questions))

    ragas_llm = LangchainLLMWrapper(ChatOllama(model=CURRENT_MODEL, temperature=0))
    ragas_emb = LangchainEmbeddingsWrapper(OllamaEmbeddings(model=OLLAMA_EMBED_MODEL))

    # 3) 질문별 RAG 실행
    samples: list[SingleTurnSample] = []
    per_question: list[dict] = []

    for i, question in enumerate(questions):
        rag_result = run_query(question)
        answer = rag_result.get("answer", "")
        contexts = rag_result.get("contexts", [])

        sample_kw: dict = {
            "user_input": question,
            "response": answer,
            "retrieved_contexts": contexts,
        }
        if has_gt:
            sample_kw["reference"] = ground_truths[i]  # type: ignore[index]

        samples.append(SingleTurnSample(**sample_kw))
        per_question.append({
            "question": question,
            "answer": answer,
            "contexts_count": len(contexts),
            "ground_truth": ground_truths[i] if has_gt else None,  # type: ignore[index]
        })

    dataset = EvaluationDataset(samples=samples)

    # 4) 메트릭 구성
    metrics: list = [
        Faithfulness(llm=ragas_llm),
        ResponseRelevancy(llm=ragas_llm, embeddings=ragas_emb),
    ]
    if has_gt:
        from ragas.metrics import LLMContextPrecisionWithReference, LLMContextRecall

        metrics += [
            LLMContextPrecisionWithReference(llm=ragas_llm),
            LLMContextRecall(llm=ragas_llm),
        ]

    metric_names = [type(m).__name__ for m in metrics]
    print(f"[evaluator] RAGAS 평가 시작 — {len(questions)}개 질문, 지표: {metric_names}")

    result_df = evaluate(dataset=dataset, metrics=metrics).to_pandas()

    # 5) 점수 집계
    skip_cols = {"user_input", "response", "retrieved_contexts", "reference"}
    score_cols = [c for c in result_df.columns if c not in skip_cols]

    avg_metrics = {
        col: _safe_round(result_df[col].mean())
        for col in score_cols
    }
    for i, row in result_df.iterrows():
        for col in score_cols:
            per_question[i][col] = _safe_round(row[col])  # type: ignore[index]

    print(f"[evaluator] 평가 완료 — 평균 점수: {avg_metrics}")
    return {
        "metrics": avg_metrics,
        "per_question": per_question,
        "question_count": len(questions),
        "ground_truth_provided": has_gt,
    }


def _safe_round(value, ndigits: int = 4):
    try:
        f = float(value)
        return None if math.isnan(f) else round(f, ndigits)
    except Exception:
        return None
