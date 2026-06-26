"""
공통 fixture: SQLite in-memory DB + 기본 데이터 구성
"""

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


@event.listens_for(Engine, "connect")
def _register_sqlite_now(dbapi_conn, _connection_record):
    """SQLite에는 now()가 없으므로 테스트용으로 등록."""
    if isinstance(dbapi_conn, sqlite3.Connection):
        dbapi_conn.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())


# ── 1. 필수 환경변수 주입 (앱 import 전) ─────────────────────────────────────
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# ── 2. 무거운 LLM/벡터 의존성을 stub 모듈로 대체 ─────────────────────────────
_HEAVY = [
    "langchain_core",
    "langchain_core.documents",
    "langchain",
    "langchain.schema",
    "langchain.text_splitter",
    "langchain_community",
    "langchain_chroma",
    "langchain_huggingface",
    "langchain_ollama",
    "langchain_text_splitters",
    "chromadb",
    "sentence_transformers",
    "rank_bm25",
    "redis",
    "pypdf",
    "fitz",
    "paddlepaddle",
    "paddleocr",
    "paddlex",
    "cv2",
    "docling",
    "llama_parse",
]
for _mod in _HEAVY:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# ── 3. app.llm 패키지 전체를 stub으로 대체 ───────────────────────────────────
_llm_pkg = ModuleType("app.llm")
_llm_pkg.NO_ANSWER_MSG = ""
sys.modules["app.llm"] = _llm_pkg
sys.modules["app.llm.ingest"] = MagicMock(delete_document_by_id=MagicMock())
sys.modules["app.llm.pipeline"] = MagicMock(
    NO_ANSWER_MSG="",
    build_rag_chain=MagicMock(),
    invalidate_cache=MagicMock(),
    run_query=MagicMock(),
)
for _sub in ["vectorstore", "embeddings", "retriever", "summarizer", "chunker", "loader", "prompts", "evaluator", "diagnose", "markdown_processor"]:
    sys.modules[f"app.llm.{_sub}"] = MagicMock()
sys.modules["app.llm.config"] = MagicMock(CURRENT_MODEL="test", LLM_CONFIG={})
sys.modules["app.ocr"] = MagicMock()
sys.modules["app.ocr.extractor"] = MagicMock()

# ── 4. 앱 모듈 import (stub 등록 후) ─────────────────────────────────────────
from app.core.security import hash_password  # noqa: E402
from app.db.models import Base, Document, Job, Role, User, UserRole  # noqa: E402

KST = timezone(timedelta(hours=9))


@pytest.fixture(scope="function")
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def roles(db):
    role_list = [
        Role(role_name="실무 담당자", description="문서 업로드/요약/RAG 질의/기안 작성"),
        Role(role_name="결재권자", description="상신된 기안 승인/반려"),
        Role(role_name="관리자", description="사용자/권한 관리, 통계 조회"),
    ]
    for r in role_list:
        db.add(r)
    db.commit()
    return {r.role_name: r for r in role_list}


@pytest.fixture
def users(db, roles):
    admin = User(
        user_email="admin@test.com",
        user_password=hash_password("000000"),
        user_name="김관리",
        created_at=datetime.now(KST),
        is_deleted=False,
    )
    staff = User(
        user_email="staff@test.com",
        user_password=hash_password("000000"),
        user_name="박실무",
        created_at=datetime.now(KST),
        is_deleted=False,
    )
    db.add(admin)
    db.add(staff)
    db.flush()

    db.add(UserRole(user_id=admin.user_id, role_id=roles["관리자"].role_id))
    db.add(UserRole(user_id=admin.user_id, role_id=roles["결재권자"].role_id))
    db.add(UserRole(user_id=staff.user_id, role_id=roles["실무 담당자"].role_id))
    db.commit()
    return {"admin": admin, "staff": staff}


@pytest.fixture
def docs_with_jobs(db, users):
    staff = users["staff"]
    doc1 = Document(
        file_name="특허법_주요_판례_분석.pdf",
        file_type="pdf",
        category="지식재산법",
        content_full="2025년 주요 특허 침해 소송 판례 분석 보고서.",
        content_sum="○ 분석 대상: 2025년 특허 침해 소송 주요 판례",
        created_at=datetime.now(KST),
        updated_at=datetime.now(KST),
        is_deleted=False,
        user_id=staff.user_id,
    )
    doc2 = Document(
        file_name="행정처분_불복절차_안내.pdf",
        file_type="pdf",
        category="행정법",
        content_full="행정처분에 대한 이의신청·행정심판·행정소송 절차 안내.",
        content_sum="○ 이의신청: 처분청에 60일 이내 제출",
        created_at=datetime.now(KST),
        updated_at=datetime.now(KST),
        is_deleted=False,
        user_id=staff.user_id,
    )
    db.add(doc1)
    db.add(doc2)
    db.flush()

    db.add(Job(doc_id=doc1.doc_id, user_id=staff.user_id, job_type="summarize", job_status="success", job_start=datetime.now(KST)))
    db.add(Job(doc_id=doc2.doc_id, user_id=staff.user_id, job_type="summarize", job_status="success", job_start=datetime.now(KST)))
    db.commit()
    return {"doc1": doc1, "doc2": doc2}
