from sqlalchemy.orm import Session

from app.db.models import Document


def get_docs(
    db: Session,
    user_id: int | None = None,
    category: str | None = None,
    skip: int = 0,
    limit: int = 50,
):
    query = db.query(Document).filter(Document.is_hidden.is_(False))
    if user_id is not None:
        query = query.filter(Document.user_id == user_id)  # Document 기준
    if category:
        query = query.filter(Document.category == category)
    return query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()
