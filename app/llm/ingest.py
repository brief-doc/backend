"""문서 저장 통합 모듈 — chunker + vectorstore 레고 조합

레고 교체:
    - 청킹 전략 변경 → chunker.py 의 markdown_splitter 교체
    - 벡터 스토어 변경 → vectorstore.py 의 get_vectorstore() 교체
    - 임베딩 변경 → embeddings.py 의 get_embeddings() 교체

흐름:
    마크다운: split_by_headers / markdown_splitter → metadata 주입 → vectorstore.add_documents()
    PDF: pdfplumber → 페이지별 Document → metadata 주입 → vectorstore.add_documents()
"""

from langchain_core.documents import Document

from .chunker import markdown_splitter, split_by_headers
from .vectorstore import get_vectorstore


def _build_metadata(doc_id: int, user_id: int, doc_name: str, category: str, chunk_idx: int, page_num: str = "") -> dict:
    return {
        "doc_id": str(doc_id),
        "user_id": str(user_id),
        "doc_name": doc_name,
        "category": category,
        "chunk_id": f"{doc_id}_{chunk_idx}",
        "page_num": str(page_num),
    }


def _delete_existing_chunks(doc_name: str, user_id: int) -> int:
    """같은 사용자의 동일 doc_name 청크를 모두 삭제합니다.

    재업로드 시 서비스가 새 doc_id를 발급하더라도, 이전에 저장된 같은 파일명의
    청크를 먼저 지워 중복 누적을 막습니다(덮어쓰기 = 재업로드 갱신).

    user_id는 현재 str로 저장되지만, 과거 int로 저장된 레거시 청크도 함께 정리합니다.

    Returns:
        삭제된 청크 수
    """
    deleted = 0
    try:
        col = get_vectorstore()._collection
        for uid in (str(user_id), user_id):
            existing = col.get(where={"$and": [{"user_id": uid}, {"doc_name": doc_name}]})
            ids = existing.get("ids", [])
            if ids:
                col.delete(ids=ids)
                deleted += len(ids)
        if deleted:
            print(f"[ingest] 기존 청크 삭제: doc_name={doc_name!r}, user_id={user_id}, {deleted}개")
    except Exception as e:
        # 삭제 실패해도 저장은 계속 진행 (최초 업로드면 삭제 대상이 없는 게 정상)
        print(f"[ingest] 기존 청크 삭제 실패(계속 진행): {e}")
    return deleted


# ── PDF 로더 ──────────────────────────────────────────────────────────────────
def _load_pdf(path: str) -> list[Document]:
    """PDF 파일을 페이지별 Document 리스트로 변환합니다. pdfplumber 우선, 실패 시 pypdf."""
    docs: list[Document] = []
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    docs.append(Document(page_content=text, metadata={"page_num": i}))
        if docs:
            return docs
    except Exception as e:
        print(f"[ingest] pdfplumber 실패, pypdf 시도: {e}")

    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                docs.append(Document(page_content=text, metadata={"page_num": i}))
    except Exception as e:
        print(f"[ingest] pypdf 실패: {e}")

    return docs


# ── PDF 저장 ──────────────────────────────────────────────────────────────────
def ingest_pdf(
    path: str,
    doc_id: int,
    user_id: int,
    doc_name: str = "PDF 문서",
    category: str = "기타",
) -> dict:
    """PDF 파일을 페이지별로 청킹하여 ChromaDB에 저장합니다."""
    raw_docs = _load_pdf(path)
    if not raw_docs:
        return {"status": "error", "detail": "PDF에서 텍스트를 추출할 수 없습니다."}

    chunks: list[Document] = []
    for i, doc in enumerate(raw_docs):
        page_num = doc.metadata.get("page_num", "")
        # 페이지 단위로 다시 청킹 (긴 페이지 대비)
        sub_chunks = markdown_splitter.create_documents([doc.page_content])
        for j, chunk in enumerate(sub_chunks):
            if len(chunk.page_content.strip()) > 10:
                chunk.metadata = _build_metadata(doc_id, user_id, doc_name, category, i * 100 + j, page_num)
                chunks.append(chunk)

    if not chunks:
        return {"status": "error", "detail": "청킹 결과 없음"}

    try:
        vs = get_vectorstore()
        _delete_existing_chunks(doc_name, user_id)  # 재업로드 시 기존 청크 덮어쓰기
        vs.add_documents(chunks)
        print(f"[ingest_pdf] 저장 완료: {doc_name}, {len(chunks)}청크, user_id={user_id}")
    except Exception as e:
        print(f"[ingest_pdf] 벡터 저장 실패: {e}")
        return {"status": "error", "detail": str(e)}

    return {"status": "success", "total_chunks": len(chunks), "category": category}


# ── 마크다운 저장 ─────────────────────────────────────────────────────────────
def ingest_markdown(
    markdown_content: str,
    doc_id: int,
    user_id: int,
    doc_name: str = "마크다운 문서",
    chunking_method: str = "sections",
    category: str = "기타",
    enable_summary: bool = False,  # 하위 호환 파라미터 (미사용)
) -> dict:
    """마크다운 문서를 청킹하여 ChromaDB에 저장합니다.

    Args:
        chunking_method: "sections" (헤더 기준) | "size" (글자 수 기준)
    """
    if chunking_method == "sections":
        raw_chunks = split_by_headers(markdown_content)
    else:
        raw_chunks = markdown_splitter.create_documents([markdown_content])

    chunks = [c for c in raw_chunks if len(c.page_content.strip()) > 10]
    if not chunks:
        return {"status": "error", "detail": "청킹 결과 없음"}

    for i, chunk in enumerate(chunks):
        section = (
            chunk.metadata.get("section")
            or chunk.metadata.get("h1")
            or chunk.metadata.get("h2")
            or chunk.metadata.get("h3")
            or "본문"
        )
        chunk.metadata = _build_metadata(doc_id, user_id, doc_name, category, i)
        chunk.metadata["section"] = section

    try:
        vs = get_vectorstore()
        _delete_existing_chunks(doc_name, user_id)  # 재업로드 시 기존 청크 덮어쓰기
        vs.add_documents(chunks)
        count = vs._collection.count()
        print(f"[ingest_md] 저장 완료: {doc_name}, {len(chunks)}청크, user_id={user_id}, DB총={count}")
    except Exception as e:
        print(f"[ingest_md] 벡터 저장 실패: {e}")
        return {"status": "error", "detail": str(e)}

    return {
        "status": "success",
        "total_chunks": len(chunks),
        "category": category,
    }


# ── 하위 호환 ─────────────────────────────────────────────────────────────────
def save_markdown_to_vector_db(
    markdown_content: str,
    doc_id: int,
    user_id: int,
    doc_name: str = "마크다운 문서",
    chunking_method: str = "sections",
    enable_summary: bool = True,
) -> dict:
    return ingest_markdown(markdown_content, doc_id, user_id, doc_name, chunking_method)
