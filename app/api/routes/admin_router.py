from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Document, Job, RagQuery, User

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


class JobItem(BaseModel):
    job_id: int
    doc_id: Optional[int]
    file_name: Optional[str]
    user_name: Optional[str]
    job_type: Optional[str]
    job_status: Optional[str]
    pipeline_stage: Optional[str]
    error_stage: Optional[str]
    error_message: Optional[str]
    job_start: Optional[str]
    job_finish: Optional[str]


class PaginatedJobs(BaseModel):
    total: int
    items: List[JobItem]


@router.get("/jobs", response_model=PaginatedJobs)
def get_admin_jobs(
    request: Request,
    status: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if not current_user or "관리자" not in _role_names(current_user):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")

    q = db.query(Job)
    if status:
        q = q.filter(Job.job_status == status)
    if job_type:
        q = q.filter(Job.job_type == job_type)
    if user_id:
        q = q.filter(Job.user_id == user_id)

    total = q.count()
    jobs = q.order_by(Job.job_start.desc()).offset(skip).limit(limit).all()

    items = []
    for job in jobs:
        doc = db.get(Document, job.doc_id) if job.doc_id else None
        user = db.get(User, job.user_id) if job.user_id else None
        items.append(
            JobItem(
                job_id=job.job_id,
                doc_id=job.doc_id,
                file_name=doc.file_name if doc else None,
                user_name=user.user_name if user else None,
                job_type=job.job_type,
                job_status=job.job_status,
                pipeline_stage=job.pipeline_stage,
                error_stage=job.error_stage,
                error_message=job.error_message,
                job_start=job.job_start.isoformat() if job.job_start else None,
                job_finish=job.job_finish.isoformat() if job.job_finish else None,
            )
        )

    return PaginatedJobs(total=total, items=items)
