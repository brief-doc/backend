"""
UT-ADM-001: 대시보드·세션 관리
- admin 외 계정 접근 차단 (role 확인)
- force-logout → 세션 is_active=false
"""

from datetime import datetime, timedelta, timezone

from app.core.security import verify_password
from app.db.models import UserSession
from app.services import auth_service

KST = timezone(timedelta(hours=9))


class TestAdminRoleCheck:
    """UT-ADM-001-1: admin 외 계정 접근 차단"""

    def test_admin_has_manager_role(self, db, users, roles):
        """관리자 계정은 '관리자' 역할 보유"""
        admin = users["admin"]
        role_names = [ur.role.role_name for ur in admin.user_roles]
        assert "관리자" in role_names

    def test_staff_does_not_have_manager_role(self, db, users):
        """실무자 계정은 '관리자' 역할 미보유"""
        staff = users["staff"]
        role_names = [ur.role.role_name for ur in staff.user_roles]
        assert "관리자" not in role_names


class TestSessionManagement:
    """UT-ADM-001-3: force-logout → 세션 is_active=false"""

    def _create_session(self, db, user_id):
        session = UserSession(
            user_id=user_id,
            session_token=f"token_{user_id}_{datetime.now().timestamp()}",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            is_active=True,
        )
        db.add(session)
        db.commit()
        return session

    def test_deactivate_session_sets_inactive(self, db, users):
        """강제 로그아웃 → 세션 is_active=false"""
        staff = users["staff"]
        session = self._create_session(db, staff.user_id)
        assert session.is_active is True

        auth_service.deactivate_session(db, session)

        db.expire(session)
        updated = db.query(UserSession).filter(UserSession.session_id == session.session_id).first()
        assert updated.is_active is False

    def test_deactivated_user_sessions_all_inactive(self, db, users):
        """계정 비활성화 시 세션 전체 종료"""
        staff = users["staff"]
        self._create_session(db, staff.user_id)
        self._create_session(db, staff.user_id)

        auth_service.update_user_activation(db, staff.user_id, is_deleted=True)

        sessions = auth_service.get_user_sessions(db, staff.user_id)
        assert all(not s.is_active for s in sessions)

    def test_get_session_by_invalid_token_returns_none(self, db):
        """유효하지 않은 토큰 → None 반환"""
        result = auth_service.get_user_session_by_token(db, "invalid_token_xyz")
        assert result is None

    def test_expired_session_returns_none(self, db, users):
        """만료된 세션 → None 반환 (SQLite는 naive datetime 사용)"""
        staff = users["staff"]
        expired_session = UserSession(
            user_id=staff.user_id,
            session_token="expired_token",
            created_at=datetime.now() - timedelta(hours=48),
            expires_at=datetime.now() - timedelta(hours=24),
            is_active=True,
        )
        db.add(expired_session)
        db.commit()

        result = auth_service.get_user_session_by_token(db, "expired_token")
        assert result is None


class TestPasswordChange:
    """비밀번호 변경 검증"""

    def test_change_password_with_correct_current_password(self, db, users):
        """올바른 현재 비밀번호 → 변경 성공"""
        staff = users["staff"]

        result = auth_service.change_password(db, staff.user_id, "000000", "newpass123")

        assert result is not None
        assert verify_password("newpass123", result.user_password)

    def test_change_password_with_wrong_current_password_returns_none(self, db, users):
        """틀린 현재 비밀번호 → None 반환"""
        staff = users["staff"]

        result = auth_service.change_password(db, staff.user_id, "wrongpassword", "newpass123")

        assert result is None

    def test_reset_password_sets_default(self, db, users):
        """비밀번호 초기화 → 000000으로 리셋"""
        staff = users["staff"]
        auth_service.change_password(db, staff.user_id, "000000", "changed123")

        result = auth_service.reset_user_password(db, staff.user_id)

        assert result is not None
        assert verify_password("000000", result.user_password)
