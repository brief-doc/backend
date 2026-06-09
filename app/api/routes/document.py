from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.document import DocResponse  # 상세 쓸 거면 DocDetail도 추가
from app.services import document_service as doc_service

router = APIRouter(prefix="/docs", tags=["docs"])


@router.get("/", response_model=list[DocResponse])
def list_documents(
    category: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    # current_user: User = Depends(get_current_user),
):
    return doc_service.get_docs_with_latest_job(
        db,
        #  user_id=current_user.user_id,
        category=category,
        skip=skip,
        limit=limit,
    )
