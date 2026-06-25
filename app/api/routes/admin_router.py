from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Document, RagQuery, User

from .auth import _role_names, get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


class CategoryStat(BaseModel):
    category: str
    count: int


class AdminStatsResponse(BaseModel):
    total_users: int
    total_documents: int
    total_rag_queries: int
    documents_this_month: int
    rag_queries_this_week: int
    category_distribution: List[CategoryStat]


@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_stats(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user or "관리자" not in _role_names(current_user):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    total_users = db.query(func.count(User.user_id)).filter(User.is_deleted.is_(False)).scalar()
    total_documents = db.query(func.count(Document.doc_id)).filter(Document.is_deleted.is_(False)).scalar()
    total_rag_queries = db.query(func.count(RagQuery.query_id)).scalar()

    documents_this_month = db.query(func.count(Document.doc_id)).filter(Document.is_deleted.is_(False), Document.created_at >= month_start).scalar()
    rag_queries_this_week = db.query(func.count(RagQuery.query_id)).filter(RagQuery.created_at >= week_start).scalar()

    category_rows = (
        db.query(Document.category, func.count(Document.doc_id).label("count"))
        .filter(Document.is_deleted.is_(False))
        .group_by(Document.category)
        .order_by(func.count(Document.doc_id).desc())
        .all()
    )
    category_distribution = [{"category": row.category or "미분류", "count": row.count} for row in category_rows]

    return {
        "total_users": total_users,
        "total_documents": total_documents,
        "total_rag_queries": total_rag_queries,
        "documents_this_month": documents_this_month,
        "rag_queries_this_week": rag_queries_this_week,
        "category_distribution": category_distribution,
    }
