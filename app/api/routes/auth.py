import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.security import (
    verify_password,
)
from app.db.database import get_db
from app.schemas.user import UserCreate
from app.services import history_service
from app.services.auth_service import (
    change_password,
    create_user,
    create_user_session,
    deactivate_session,
    get_session_by_id,
    get_session_by_user,
    get_user_by_email,
    get_user_by_session_token,
    get_user_session_by_token,
    get_user_sessions,
    get_users,
    reset_user_password,
    update_user_activation,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _role_names(user) -> List[str]:
    return [ur.role.role_name for ur in user.user_roles]


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    roles: List[str] = []
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    id: int
    email: str
    name: str
    roles: List[str] = []
    user_login: Optional[datetime] = None
    user_create: Optional[datetime] = None
    user_update: Optional[datetime] = None
    is_deleted: bool

    class Config:
        from_attributes = True


class SessionResponse(BaseModel):
    session_id: int
    user_id: int
    created_at: datetime
    expires_at: Optional[datetime]
    is_active: bool
    ip_address: Optional[str]
    user_agent: Optional[str]

    class Config:
        from_attributes = True


def get_current_user(request: Request, db: Session = Depends(get_db)):
    session_token = request.cookies.get("session_token")

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 세션이 없습니다.",
        )

    session = get_user_session_by_token(db, session_token)

    if not session or not session.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 세션입니다.")

    if session.expires_at < datetime.now(timezone.utc):
        deactivate_session(db, session.session_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="세션이 만료되었습니다.")

    return session.user


def get_current_active_user(current_user=Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="비활성화된 계정입니다")
    return current_user


def get_current_admin(current_user=Depends(get_current_user)):
    # Assuming user.user_roles is a relationship list
    role_names = [ur.role.role_name for ur in current_user.user_roles]

    if "관리자" not in role_names:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한이 필요합니다.")
    return current_user


@router.get("/me")
def get_me(request: Request, response: Response, db: Session = Depends(get_db)):
    print("get_me 호출됨")
    user = get_current_user(request, db)
    if user:
        return {
            "authenticated": True,
            "id": user.user_id,
            "email": user.user_email,
            "name": user.user_name,
            "roles": _role_names(user),
            "created_at": user.created_at,
        }

    session_token = request.cookies.get("session_token")
    if not session_token:
        return {"authenticated": False}

    user = get_user_by_session_token(db, session_token)
    if not user:
        response.set_cookie(
            key="session_token",
            value=session_token,
            path="/",
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=1,
        )
    return {"authenticated": False}


@router.post("/register", response_model=UserResponse)
def register(user: UserCreate, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    if get_user_by_email(db, user.email, is_new=True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 존재하는 이메일입니다")
    new_user = create_user(db, user)
    history_service.record(db, new_user.user_id, "user", "계정 생성")
    db.commit()
    return {
        "id": new_user.user_id,
        "email": new_user.user_email,
        "name": new_user.user_name,
        "roles": _role_names(new_user),
    }


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    email: str
    userId: int
    current_password: str
    new_password: str
    user_login: Optional[datetime] = None


@router.post("/login")
def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    user = get_user_by_email(db, login_data.email)

    if not user or not verify_password(login_data.password, user.user_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다",
        )
    new_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    session = get_session_by_user(db, user.user_id)

    if session:
        # Update existing row with a fresh, secure random token
        session.session_token = new_token
        session.expires_at = expires_at
        session.is_active = True
        db.commit()

    else:
        create_user_session(
            db,
            user.user_id,
            new_token,
            expires_at,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
        )

    response.set_cookie(
        key="session_token",
        value=new_token,
        path="/",
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24,
    )

    return {
        "message": "로그인 성공",
        "id": user.user_id,
        "email": user.user_email,
        "name": user.user_name,
        "roles": _role_names(user),
        "user_login": user.user_login,
    }


@router.get("/approvers")
def list_approvers(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다")

    users = get_users(db)
    return [
        {"id": u.user_id, "name": u.user_name}
        for u in users
        if not u.is_deleted and u.user_id != current_user.user_id and any(ur.role.role_name == "결재권자" for ur in u.user_roles)
    ]


@router.get("/users", response_model=List[UserListResponse])
def list_users(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다")

    if "관리자" not in _role_names(current_user):
        raise HTTPException(status_code=403, detail="권한이 없습니다.")

    users = get_users(db)
    return [
        {
            "id": user.user_id,
            "email": user.user_email,
            "name": user.user_name,
            "roles": _role_names(user),
            "user_login": user.user_login,
            "user_create": user.created_at,
            "user_update": user.updated_at,
            "is_deleted": user.is_deleted,
        }
        for user in users
    ]


class ActivationRequest(BaseModel):
    is_deleted: bool


@router.patch("/users/{user_id}/activation")
def toggle_user_activation(user_id: int, payload: ActivationRequest, request: Request, db: Session = Depends(get_db)):
    """
    Endpoint to activate/deactivate users. Restricted to Admin role only.
    """
    # 1. Verify admin is logged in
    current_user = get_current_user(request, db)
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다")

    if "관리자" not in _role_names(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한이 필요합니다")

    # 2. Prevent admins from deactivating themselves accidentally
    if current_user.user_id == user_id and payload.is_deleted:
        raise HTTPException(status_code=400, detail="본인 계정은 비활성화할 수 없습니다.")

    # 3. Update status
    updated_user = update_user_activation(db, user_id, payload.is_deleted)
    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다")

    action = "비활성화" if payload.is_deleted else "활성화"
    history_service.record(db, user_id, "user", f"관리자에 의해 계정 {action}")
    db.commit()
    return {"message": f"사용자가 성공적으로 {action}되었습니다."}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다")

    updated_user = reset_user_password(db, user_id)
    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다")

    history_service.record(db, user_id, "user", "관리자에 의해 비밀번호 초기화")
    db.commit()
    return {"message": "암호가 초기화되었습니다"}


@router.post("/users/{user_id}/force-logout")
def force_logout_user(user_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다")

    sessions = get_user_sessions(db, user_id)
    for session in sessions:
        deactivate_session(db, session)

    history_service.record(db, user_id, "user", "관리자에 의해 강제 로그아웃")
    db.commit()
    return {"message": "사용자가 로그아웃되었습니다", "logged_out_sessions": len(sessions)}


@router.get("/sessions", response_model=List[SessionResponse])
def get_sessions(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다")
    return get_user_sessions(db, user.user_id)


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다")

    session = get_session_by_id(db, session_id)
    if not session or session.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다")

    deactivate_session(db, session)
    if request.cookies.get("session_token") == session.session_token:
        response.set_cookie(
            key="session_token",
            value="",
            path="/",
            expires="Thu, 01 Jan 1970 00:00:00 GMT",
            max_age=0,
            httponly=True,
            secure=False,  # Match this to your current environment
            samesite="lax",
        )

    return {"message": "세션이 종료되었습니다"}


@router.post("/change-password")
def change_password_endpoint(
    change_req: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    사용자 비밀번호 변경 및 user_login 시간 업데이트

    - 현재 비밀번호 검증 후 새로운 비밀번호로 변경
    - user_login이 null인 경우, 현재 시간으로 설정
    - user_login이 이미 있는 경우, 새로운 로그인 시간으로 업데이트
    """
    user = get_user_by_email(db, change_req.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다")

    if user.user_id != change_req.userId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="사용자 ID가 일치하지 않습니다")

    login_time = change_req.user_login if change_req.user_login else datetime.now(timezone.utc)
    updated_user = change_password(
        db,
        user.user_id,
        change_req.current_password,
        change_req.new_password,
        login_time,
    )

    if not updated_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="현재 비밀번호가 올바르지 않습니다")

    history_service.record(db, updated_user.user_id, "user", "비밀번호 변경")
    db.commit()
    return {
        "message": "비밀번호가 성공적으로 변경되었습니다",
        "id": updated_user.user_id,
        "email": updated_user.user_email,
        "user_login": updated_user.user_login,
    }


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    session_token = request.cookies.get("session_token")
    if session_token:
        session = get_user_session_by_token(db, session_token)
        if session:
            deactivate_session(db, session)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.delete_cookie(key="session_token", path="/", domain="localhost", httponly=True, samesite="lax")
    return {"message": "로그아웃 성공"}
