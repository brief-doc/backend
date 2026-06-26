import difflib
from datetime import datetime, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.models import Document, Job
from app.llm.ingest import delete_document_by_id
from app.schemas.document import DocResponse, DocUpdate
from app.services import history_service

_MAX_DIFF_ITEMS = 5


def _summarize_diff(old: str, new: str) -> str:
    old_words = (old or "").split()
    new_words = (new or "").split()
    matcher = difflib.SequenceMatcher(None, old_words, new_words)
    changes = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            changes.append(f"'{' '.join(old_words[i1:i2])}' → '{' '.join(new_words[j1:j2])}'")
        elif tag == "delete":
            changes.append(f"'{' '.join(old_words[i1:i2])}' 삭제")
        elif tag == "insert":
            changes.append(f"'{' '.join(new_words[j1:j2])}' 추가")
    if not changes:
        return "요약 수정 (변경 없음)"
    if len(changes) > _MAX_DIFF_ITEMS * 3:
        return f"요약 전체 수정 ({len(old_words)}단어 → {len(new_words)}단어)"
    shown = changes[:_MAX_DIFF_ITEMS]
    suffix = f" 외 {len(changes) - _MAX_DIFF_ITEMS}건" if len(changes) > _MAX_DIFF_ITEMS else ""
    return f"요약 수정: {', '.join(shown)}{suffix}"


# 문서 목록 조회(최신 작업 상태와 함께)
def get_docs_with_latest_job(
    db: Session,
    user_id: int,
    category: str | None = None,
    keyword: str | None = None,
    sort_by: str = "created_at",
    skip: int = 0,
    limit: int = 50,
) -> tuple[int, list[DocResponse]]:

    # 1. 기본 베이스 쿼리 빌드
    query = (
        db.query(Document, Job)
        .join(Job, Job.doc_id == Document.doc_id)
        .distinct(Document.doc_id)
        .filter(Document.user_id == user_id, Document.is_deleted.is_(False))
    )

    # 2. 카테고리
    if category is not None:
        query = query.filter(Document.category == category)

    # 3. 검색어(keyword)
    if keyword is not None and keyword.strip() != "":
        query = query.filter(Document.file_name.contains(keyword))

    if sort_by == "oldest":
        # 오래된순 — doc_id ASC로 DISTINCT ON 기준 유지
        order_stmt = [Document.doc_id.asc(), Job.job_start.asc()]
    else:
        # 최신순(기본값) / 제목순 모두 doc_id DESC 우선으로 DISTINCT ON 충족 후 2차 정렬
        secondary = Document.file_name.asc() if sort_by == "title" else desc(Job.job_start)
        order_stmt = [Document.doc_id.desc(), secondary]

    # 4. 필터링된 전체 개수를 구함.
    total_count = query.count()

    # 5. 정렬 및 페이징 분량=
    stmt = query.order_by(*order_stmt).offset(skip).limit(limit)
    results = stmt.all()  # list[(Document, Job)]

    # 6. DTO 변환 연산
    docs_list = [
        DocResponse(
            doc_id=doc.doc_id,
            file_name=doc.file_name,
            category=doc.category,
            created_at=doc.created_at,
            user_id=doc.user_id,
            job_status=job.job_status,
        )
        for doc, job in results
    ]

    # 7. 총 개수와 리스트를 함께 리턴
    return total_count, docs_list


# 문서 상세 조회
def get_docs_detail(
    db: Session,
    doc_id: int,
    user_id: int,
):
    doc_detail = (
        db.query(Document)
        .filter(
            Document.user_id == user_id,
            Document.is_deleted.is_(False),
            Document.doc_id == doc_id,
            # 완료 상태만 조회 가능
        )
        .first()
    )

    return doc_detail


# 문서 삭제
def soft_delete_doc(
    db: Session,
    doc_id: int,
    user_id: int,
):
    doc = db.query(Document).filter(Document.doc_id == doc_id, Document.user_id == user_id, Document.is_deleted.is_(False)).first()
    if not doc:
        return False

    doc.is_deleted = True
    history_service.record(db, user_id, "doc", f"문서 '{doc.file_name}' 삭제")
    db.commit()
    delete_document_by_id(doc_id)
    return True


def update_doc(db: Session, doc_id: int, user_id: int, payload: DocUpdate):
    doc = get_docs_detail(db, doc_id, user_id)
    if not doc:
        return None

    data = payload.model_dump(exclude_unset=True)
    original_name = doc.file_name
    change_parts = []
    for key, value in data.items():
        old_val = getattr(doc, key, None)
        if key == "content_sum":
            change_parts.append(_summarize_diff(old_val or "", value or ""))
        else:
            label = {"file_name": "파일명", "category": "카테고리"}.get(key, key)
            if old_val != value:
                change_parts.append(f"{label} '{old_val}' → '{value}'")
        setattr(doc, key, value)

    if change_parts:
        history_service.record(db, user_id, "doc", f"문서 '{original_name}': {', '.join(change_parts)}")

    doc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(doc)
    return doc
