from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Draft, History, RagQuery
from app.services.auth_service import get_user

from .auth import _role_names, get_current_user

router = APIRouter(prefix="/users", tags=["users"])


class ActivityUserDetail(BaseModel):
    name: str
    email: str
    roles: List[str]
    joinDate: Optional[str] = None


class RagQueryItem(BaseModel):
    query_id: int
    query_text: str
    answer_text: Optional[str] = None
    created_at: datetime


class DraftItem(BaseModel):
    draft_id: int
    title: str
    status: str
    created_at: datetime


class HistoryItem(BaseModel):
    history_id: int
    change_table: str
    change_text: str
    change_time: datetime


class UserActivityResponse(BaseModel):
    user: ActivityUserDetail
    rag_queries: List[RagQueryItem] = []
    drafts: List[DraftItem] = []
    histories: List[HistoryItem] = []


@router.get("/activity", response_model=UserActivityResponse)
def get_user_activity(
    request: Request,
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if not current_user:
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")

    current_roles = [ur.role.role_name for ur in current_user.user_roles]

    if user_id is not None:
        if "관리자" not in current_roles:
            raise HTTPException(status_code=403, detail="타인의 활동 내역을 조회할 권한이 없습니다.")
        target_user_id = user_id
    else:
        target_user_id = current_user.user_id

    user_info = get_user(db, target_user_id)
    user_roles = _role_names(user_info)
    join_date = user_info.created_at.strftime("%Y.%m.%d") if user_info.created_at else None

    rag_queries = db.query(RagQuery).filter(RagQuery.user_id == target_user_id).order_by(RagQuery.created_at.desc()).limit(10).all()
    drafts = db.query(Draft).filter(Draft.author_id == target_user_id).order_by(Draft.created_at.desc()).limit(10).all()
    histories = db.query(History).filter(History.user_id == target_user_id).order_by(History.change_time.desc()).limit(50).all()

    return {
        "user": {
            "name": user_info.user_name,
            "email": user_info.user_email,
            "roles": user_roles,
            "joinDate": join_date,
        },
        "rag_queries": [
            {"query_id": q.query_id, "query_text": q.query_text, "answer_text": q.answer_text, "created_at": q.created_at} for q in rag_queries
        ],
        "drafts": [{"draft_id": d.draft_id, "title": d.title, "status": d.status, "created_at": d.created_at} for d in drafts],
        "histories": [
            {
                "history_id": h.history_id,
                "change_table": h.change_table,
                "change_text": h.change_text,
                "change_time": h.change_time,
            }
            for h in histories
        ],
    }
