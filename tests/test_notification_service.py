"""
UT-APR-002 알림: 상태 변경 시 알림 생성, 읽음 처리·미읽음 카운트
"""
from datetime import timedelta, timezone
from unittest.mock import patch

from app.services import notification_service

KST = timezone(timedelta(hours=9))


class TestNotificationCreate:
    """알림 레코드 생성"""

    @patch("app.services.notification_service._push_sync")
    def test_create_notification_saves_to_db(self, mock_push, db, users):
        """상태 변경 시 알림 레코드 생성"""
        staff = users["staff"]

        noti = notification_service.create_notification(
            db,
            user_id=staff.user_id,
            message="'특허 침해 대응 방안 검토 의견서' 기안이 승인되었습니다",
            domain_type="draft",
            resource_id=1,
        )

        assert noti.noti_id is not None
        assert noti.user_id == staff.user_id
        assert noti.is_read is False
        assert noti.link == "draft:1"

    @patch("app.services.notification_service._push_sync")
    def test_create_notification_without_link(self, mock_push, db, users):
        """링크 없는 알림 생성"""
        admin = users["admin"]

        noti = notification_service.create_notification(
            db,
            user_id=admin.user_id,
            message="시스템 공지: 정기 점검이 예정되어 있습니다",
        )

        assert noti.noti_id is not None
        assert noti.link is None


class TestNotificationReadToggle:
    """읽음 처리·미읽음 카운트"""

    @patch("app.services.notification_service._push_sync")
    def test_mark_as_read_toggles_is_read(self, mock_push, db, users):
        """읽음 토글 → is_read=True"""
        staff = users["staff"]
        noti = notification_service.create_notification(
            db, staff.user_id, "테스트 알림"
        )
        assert noti.is_read is False

        updated = notification_service.mark_as_read(db, noti.noti_id, staff.user_id)

        assert updated.is_read is True

    @patch("app.services.notification_service._push_sync")
    def test_mark_as_read_other_user_returns_none(self, mock_push, db, users):
        """타 사용자 알림 읽음 처리 차단"""
        staff = users["staff"]
        admin = users["admin"]
        noti = notification_service.create_notification(
            db, staff.user_id, "실무자 알림"
        )

        result = notification_service.mark_as_read(db, noti.noti_id, admin.user_id)

        assert result is None

    @patch("app.services.notification_service._push_sync")
    def test_unread_count_decreases_after_read(self, mock_push, db, users):
        """읽음 처리 후 미읽음 카운트 갱신"""
        staff = users["staff"]
        notification_service.create_notification(db, staff.user_id, "알림1")
        noti2 = notification_service.create_notification(db, staff.user_id, "알림2")

        total_before, items_before = notification_service.get_notifications(
            db, staff.user_id
        )
        unread_before = sum(1 for n in items_before if not n.is_read)

        notification_service.mark_as_read(db, noti2.noti_id, staff.user_id)

        _, items_after = notification_service.get_notifications(db, staff.user_id)
        unread_after = sum(1 for n in items_after if not n.is_read)

        assert unread_after == unread_before - 1

    @patch("app.services.notification_service._push_sync")
    def test_get_notifications_pagination(self, mock_push, db, users):
        """알림 페이지네이션"""
        staff = users["staff"]
        for i in range(5):
            notification_service.create_notification(db, staff.user_id, f"알림{i}")

        total, items = notification_service.get_notifications(
            db, staff.user_id, skip=0, limit=3
        )

        assert total == 5
        assert len(items) == 3
