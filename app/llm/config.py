import os
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

# ── LLM 공급자 선택 ──────────────────────────────
# "ollama"       → Ollama 로컬 서버 (기본값)
# "huggingface"  → HuggingFace transformers 로컬 모델
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")

# ── Ollama 설정 ───────────────────────────────────
CURRENT_MODEL = os.getenv("CURRENT_MODEL", "gemma2:2b")
_OLLAMA_DEFAULT_URL = "http://localhost:11434"
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", _OLLAMA_DEFAULT_URL)

# base_url 이 기본값과 같으면 생략 — 명시할 경우 chromadb 와 httpx 충돌(segfault) 발생
_ollama_extra: dict = {}
if _OLLAMA_BASE_URL != _OLLAMA_DEFAULT_URL:
    _ollama_extra["base_url"] = _OLLAMA_BASE_URL

LLM_CONFIG = {
    "model": CURRENT_MODEL,
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
    "num_ctx": int(os.getenv("LLM_NUM_CTX", "4096")),
    "num_predict": int(os.getenv("LLM_NUM_PREDICT", "512")),
    **_ollama_extra,
}

# ── HuggingFace 설정 ──────────────────────────────
HF_LLM_CONFIG = {
    # HuggingFace Hub 모델 ID (로컬 경로도 가능)
    "model_id": os.getenv("HF_MODEL_ID", "rudalson/Llama-3.2-3B-Instruct-Legal-Chatbot"),
    # 최대 생성 토큰 수
    "max_new_tokens": int(os.getenv("HF_MAX_NEW_TOKENS", "512")),
    # 온도 (0.0 = 결정론적)
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
    # GPU 사용 여부: "auto" → GPU 있으면 자동 사용, "cpu" → CPU 강제
    "device": os.getenv("HF_DEVICE", "auto"),
    # 메모리 절약: float16 (GPU) / float32 (CPU)
    "torch_dtype": os.getenv("HF_TORCH_DTYPE", "float16"),
}

# ── 요약 전용 LLM 설정 (속도 우선) ───────────────────────────────────────────
SUMMARY_LLM_CONFIG = {
    **LLM_CONFIG,
    "temperature": 0.1,
    "num_ctx": int(os.getenv("SUMMARY_NUM_CTX", "2048")),
    "num_predict": int(os.getenv("SUMMARY_NUM_PREDICT", "300")),
}

HF_SUMMARY_LLM_CONFIG = {
    **HF_LLM_CONFIG,
    "temperature": 0.0,
    "max_new_tokens": int(os.getenv("SUMMARY_NUM_PREDICT", "300")),
}

# ── Map-Reduce 병렬 처리 설정 ─────────────────────────────────────────────────
SUMMARY_MAP_WORKERS = int(os.getenv("SUMMARY_MAP_WORKERS", "3"))  # 동시 Map 호출 수

# ── Embedding ─────────────────────────────────────
# ingest / retriever 양쪽이 동일 모델을 참조해야 벡터 공간이 일치함
EMBEDDING_CONFIG = {
    "model_name": os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
    "device": os.getenv("EMBEDDING_DEVICE", "cpu"),
    "normalize_embeddings": os.getenv("NORMALIZE_EMBEDDINGS", "True").lower() == "true",
}

# ── ChromaDB ─────────────────────────────────────
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_pdf_db")
COLLECTION_NAME = "qa_collection"

# ── Retrieval ────────────────────────────────────
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
TOP_K_RETRIEVE = int(os.getenv("TOP_K_RETRIEVE", "10"))  # 초기 후보 수 (20→10 속도 최적화)
TOP_K_FINAL = int(os.getenv("TOP_K_FINAL", "5"))  # 리랭킹 후 최종 수

# ── PostgreSQL ───────────────────────────────────
_db_url = os.getenv("DATABASE_URL", "")
if _db_url:
    _p = urlparse(_db_url)
    DB_CONFIG = {
        "host": _p.hostname or "localhost",
        "port": _p.port or 5432,
        "database": (_p.path or "/pdf_db").lstrip("/"),
        "user": _p.username or "postgres",
        "password": _p.password or os.getenv("DB_PASSWORD", "8342"),
    }
else:
    DB_CONFIG = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "pdf_db"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "8342"),
    }
