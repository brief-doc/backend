"""임베딩 모델 싱글톤 — ingest·retriever 공통 사용

sentence_transformers 의 C 확장이 chromadb 와 충돌하여 segfault 를 유발합니다.
transformers 를 직접 사용하는 TransformersEmbeddings 로 교체하여 문제를 해결합니다.

레고 교체:
    이 파일의 get_embeddings() 반환값을 바꾸면
    ingest·retriever 양쪽이 동시에 교체됩니다.

    예) Ollama 임베딩으로 교체:
        from langchain_ollama import OllamaEmbeddings
        _instance = OllamaEmbeddings(model="nomic-embed-text")
"""

from __future__ import annotations

import os

# sentence_transformers 의 Rust tokenizer 병렬 처리가 segfault 를 유발 → 반드시 비활성화
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from typing import TYPE_CHECKING

import torch
from langchain_core.embeddings import Embeddings

from .config import EMBEDDING_CONFIG

if TYPE_CHECKING:
    pass


class TransformersEmbeddings(Embeddings):
    """transformers AutoModel 기반 임베딩 (sentence_transformers 없이 동작)

    sentence_transformers 는 C 확장이 chromadb 와 충돌하므로
    transformers 를 직접 호출하여 [CLS] 토큰 벡터를 임베딩으로 사용합니다.

    BGE-M3 권장 설정:
        normalize_embeddings=True  — 코사인 유사도 계산 최적화
        pooling="cls"              — [CLS] 토큰 벡터 사용
    """

    def __init__(
        self,
        model_name: str,
        device: str = "cpu",
        normalize_embeddings: bool = True,
        batch_size: int = 16,
        max_length: int = 512,
        pooling: str = "cls",
    ) -> None:
        from transformers import AutoModel, AutoTokenizer

        self.model_name = model_name
        self.device = device
        self.normalize_embeddings = normalize_embeddings
        self.batch_size = batch_size
        self.max_length = max_length
        self.pooling = pooling

        print(f"[embeddings] 모델 로드: {model_name} (device={device})")
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModel.from_pretrained(model_name)
        self._model.eval()
        if device != "cpu":
            try:
                self._model = self._model.to(device)
            except Exception as e:
                print(f"[embeddings] {device} 이동 실패, CPU 사용: {e}")
                self.device = "cpu"
        print("[embeddings] 로드 완료 (이후 재사용)")

    def _encode(self, texts: list[str]) -> list[list[float]]:
        all_vecs: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            inputs = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            )
            if self.device != "cpu":
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                out = self._model(**inputs)

            if self.pooling == "cls":
                vecs = out.last_hidden_state[:, 0]  # [CLS] 토큰
            else:
                # mean pooling
                mask = inputs["attention_mask"].unsqueeze(-1).float()
                vecs = (out.last_hidden_state * mask).sum(1) / mask.sum(1)

            if self.normalize_embeddings:
                vecs = torch.nn.functional.normalize(vecs, p=2, dim=-1)

            all_vecs.extend(vecs.cpu().tolist())
        return all_vecs

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """문서 목록을 벡터화합니다."""
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        """단일 쿼리를 벡터화합니다."""
        return self._encode([text])[0]


# ── 싱글톤 ─────────────────────────────────────────────────────────────────────
_instance: TransformersEmbeddings | None = None


def get_embeddings() -> TransformersEmbeddings:
    """BGE-M3 로컬 임베딩 싱글톤 반환 (최초 1회 로드 후 재사용)"""
    global _instance
    if _instance is None:
        _instance = TransformersEmbeddings(
            model_name=EMBEDDING_CONFIG["model_name"],
            device=EMBEDDING_CONFIG.get("device", "cpu"),
            normalize_embeddings=EMBEDDING_CONFIG.get("normalize_embeddings", True),
        )
    return _instance
