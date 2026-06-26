"""
UT-APR-001: 기안 작성·상신
UT-APR-002: 결재 처리
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.db.models import Draft
from app.schemas.draft import DraftCreate, DraftUpdate
from app.services import draft_service

KST = timezone(timedelta(hours=9))


# ── UT-APR-001: 기안 작성·상신 ────────────────────────────────────────────────


class TestDraftCreate:
    """기안 생성 시나리오"""

    def test_create_draft_with_source_doc(self, db, docs_with_jobs, users):
        """UT-APR-001-1,2: source_doc_id 지정 + approver_id 선택 → 기안 레코드 생성"""
        staff = users["staff"]
        admin = users["admin"]
        doc1 = docs_with_jobs["doc1"]

        payload = DraftCreate(
            title="특허 침해 대응 방안 검토 의견서",
            content="첨부된 특허법 주요 판례 분석을 토대로 검토하였습니다.",
            source_doc_id=doc1.doc_id,
            approver_id=admin.user_id,
            action="save",
        )

        result = draft_service.create_draft(db, staff.user_id, payload)

        assert result is not None
        assert result.author_id == staff.user_id
        assert result.source_doc_id == doc1.doc_id
        assert result.approver_id == admin.user_id

    def test_create_draft_save_sets_draft_status(self, db, users):
        """UT-APR-001-3: action=save → status=draft (임시저장)"""
        staff = users["staff"]
        payload = DraftCreate(
            title="임시저장 기안",
            content="임시로 저장합니다.",
            action="save",
        )

        result = draft_service.create_draft(db, staff.user_id, payload)

        assert result.status == "draft"

    @patch("app.services.draft_service.notification_service", create=True)
    def test_create_draft_submit_sets_pending(self, mock_noti, db, users):
        """UT-APR-001-4: action=submit → status=pending"""
        staff = users["staff"]
        admin = users["admin"]
        payload = DraftCreate(
            title="상신 기안",
            content="결재를 요청드립니다.",
            approver_id=admin.user_id,
            action="submit",
        )

        result = draft_service.create_draft(db, staff.user_id, payload)

        assert result.status == "pending"

    def test_submit_without_approver_raises_error(self):
        """UT-APR-001-4 엣지: 상신 시 결재권자 미지정 → 오류"""
        with pytest.raises(ValueError):
            DraftCreate(
                title="상신 기안",
                content="결재를 요청드립니다.",
                action="submit",
            )

    def test_cannot_set_self_as_approver(self, db, users):
        """본인을 결재권자로 지정 불가"""
        staff = users["staff"]
        payload = DraftCreate(
            title="본인 결재 기안",
            content="본인을 결재권자로 지정.",
            approver_id=staff.user_id,
            action="submit",
        )

        with pytest.raises(ValueError, match="본인"):
            draft_service.create_draft(db, staff.user_id, payload)


class TestDraftList:
    """기안 목록 조회 시나리오"""

    def _create_draft(self, db, author_id, title, status="draft", approver_id=None):
        draft = Draft(
            author_id=author_id,
            title=title,
            content="내용",
            status=status,
            approver_id=approver_id,
            created_at=datetime.now(KST),
            updated_at=datetime.now(KST),
        )
        db.add(draft)
        db.commit()
        return draft

    def test_get_own_drafts_only(self, db, users):
        """본인 기안만 조회"""
        staff = users["staff"]
        admin = users["admin"]
        self._create_draft(db, staff.user_id, "실무자 기안")
        self._create_draft(db, admin.user_id, "관리자 기안")

        total, drafts = draft_service.get_drafts(db, author_id=staff.user_id)

        assert total == 1
        assert drafts[0].author_id == staff.user_id

    def test_filter_by_status(self, db, users):
        """상태별 필터링"""
        staff = users["staff"]
        admin = users["admin"]
        self._create_draft(db, staff.user_id, "임시저장", status="draft")
        self._create_draft(db, staff.user_id, "상신됨", status="pending", approver_id=admin.user_id)

        total, drafts = draft_service.get_drafts(db, author_id=staff.user_id, status="pending")

        assert total == 1
        assert drafts[0].status == "pending"

    def test_canceled_drafts_excluded(self, db, users):
        """취소된 기안은 기본 조회에서 제외"""
        staff = users["staff"]
        admin = users["admin"]
        self._create_draft(db, staff.user_id, "정상 기안")
        self._create_draft(db, staff.user_id, "취소된 기안", status="canceled", approver_id=admin.user_id)

        total, drafts = draft_service.get_drafts(db, author_id=staff.user_id)

        assert total == 1
        assert all(d.status != "canceled" for d in drafts)


# ── UT-APR-002: 결재 처리 ─────────────────────────────────────────────────────


class TestDraftApproval:
    """결재 처리 시나리오"""

    def _create_pending_draft(self, db, author_id, approver_id):
        draft = Draft(
            author_id=author_id,
            title="결재 대기 기안",
            content="결재를 요청드립니다.",
            status="pending",
            approver_id=approver_id,
            created_at=datetime.now(KST),
            updated_at=datetime.now(KST),
        )
        db.add(draft)
        db.commit()
        return draft

    def test_approve_sets_status_approved(self, db, users):
        """UT-APR-002-1: 승인 → status=approved"""
        staff = users["staff"]
        admin = users["admin"]
        draft = self._create_pending_draft(db, staff.user_id, admin.user_id)

        result = draft_service.process_decision(db, draft.draft_id, admin.user_id, "approved")

        assert result is not None
        assert result.status == "approved"
        assert result.decided_at is not None

    def test_reject_with_reason_sets_status_rejected(self, db, users):
        """UT-APR-002-2: 반려(사유 입력) → status=rejected, 사유 저장"""
        staff = users["staff"]
        admin = users["admin"]
        draft = self._create_pending_draft(db, staff.user_id, admin.user_id)
        reason = "구체적인 근거가 부족합니다."

        result = draft_service.process_decision(
            db, draft.draft_id, admin.user_id, "rejected", reject_reason=reason
        )

        assert result.status == "rejected"
        assert result.reject_reason == reason

    def test_reject_without_reason_raises_error(self):
        """UT-APR-002-3: 반려 사유 미입력 → 차단(사유 필수)"""
        from app.schemas.draft import DecisionRequest

        with pytest.raises(ValueError, match="사유"):
            DecisionRequest(action="rejected", reject_reason="")

    def test_wrong_approver_cannot_decide(self, db, users):
        """다른 결재권자는 처리 불가"""
        staff = users["staff"]
        admin = users["admin"]
        draft = self._create_pending_draft(db, staff.user_id, admin.user_id)

        result = draft_service.process_decision(
            db, draft.draft_id, staff.user_id, "approved"
        )

        assert result is None

    def test_cancel_pending_draft(self, db, users):
        """pending 상태 기안 취소 → status=canceled"""
        staff = users["staff"]
        admin = users["admin"]
        draft = self._create_pending_draft(db, staff.user_id, admin.user_id)

        result = draft_service.cancel_draft(db, draft.draft_id, staff.user_id)

        assert result.status == "canceled"

    def test_cancel_approved_draft_raises_error(self, db, users):
        """승인된 기안은 취소 불가"""
        staff = users["staff"]
        admin = users["admin"]
        draft = self._create_pending_draft(db, staff.user_id, admin.user_id)
        draft.status = "approved"
        db.commit()

        with pytest.raises(ValueError):
            draft_service.cancel_draft(db, draft.draft_id, staff.user_id)

    def test_update_rejected_draft_and_resubmit(self, db, users):
        """반려 후 수정 재상신 → status=pending"""
        staff = users["staff"]
        admin = users["admin"]
        draft = Draft(
            author_id=staff.user_id,
            title="반려된 기안",
            content="내용",
            status="rejected",
            reject_reason="근거 부족",
            approver_id=admin.user_id,
            created_at=datetime.now(KST),
            updated_at=datetime.now(KST),
        )
        db.add(draft)
        db.commit()

        payload = DraftUpdate(
            content="보완된 내용입니다.",
            approver_id=admin.user_id,
            action="submit",
        )
        result = draft_service.update_draft(db, draft.draft_id, staff.user_id, payload)

        assert result.status == "pending"
        assert result.reject_reason is None
