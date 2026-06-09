from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.models import Document, Job
from app.schemas.document import DocResponse


# 문서 목록 조회(최신 작업 상태와 함께)
def get_docs_with_latest_job(
    db: Session,
    user_id: int | None = None,
    category: str | None = None,
    skip: int = 0,
    limit: int = 50,
):
    query = (
        db.query(Document, Job)
        .join(Job, Job.doc_id == Document.doc_id)
        .distinct(Document.doc_id)
        .filter(Document.is_hidden.is_(False))
    )

    if user_id is not None:
        query = query.filter(Document.user_id == user_id)
    if category is not None:
        query = query.filter(Document.category == category)

    stmt = query.order_by(Document.doc_id, desc(Job.job_start)).offset(skip).limit(limit)

    results = stmt.all()  # list[(Document, Job)]

    # 👇 튜플을 DocResponse로 펴주기
    return [
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
