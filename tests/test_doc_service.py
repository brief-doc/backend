"""
UT-DOC-002: 문서 목록·검색
UT-DOC-003: 문서 상세·수정·삭제
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.db.models import Document, History, Job
from app.schemas.document import DocUpdate
from app.services import document_service

KST = timezone(timedelta(hours=9))


# ── UT-DOC-002: 문서 목록·검색 ────────────────────────────────────────────────


class TestDocListSearch:
    """UT-DOC-002 - 카테고리 필터, 키워드 검색, 페이지네이션"""

    def _make_mock_db(self, docs_jobs: list[tuple]):
        """(Document, Job) 튜플 리스트를 반환하는 mock db 생성."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.distinct.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = len(docs_jobs)
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = docs_jobs
        return mock_db

    def _make_doc(self, doc_id, file_name, category, user_id):
        doc = MagicMock(spec=Document)
        doc.doc_id = doc_id
        doc.file_name = file_name
        doc.category = category
        doc.created_at = datetime.now(KST)
        doc.user_id = user_id
        return doc

    def _make_job(self, job_status="success"):
        job = MagicMock(spec=Job)
        job.job_status = job_status
        job.job_start = datetime.now(KST)
        return job

    def test_category_filter_returns_matching_docs(self):
        """UT-DOC-002-1: category=행정법 → 해당 카테고리 문서만 표출"""
        doc = self._make_doc(1, "행정처분_불복절차_안내.pdf", "행정법", 1)
        job = self._make_job()
        mock_db = self._make_mock_db([(doc, job)])

        total, result = document_service.get_docs_with_latest_job(mock_db, user_id=1, category="행정법")

        assert total == 1
        assert result[0].category == "행정법"

    def test_keyword_search_returns_matching_docs(self):
        """UT-DOC-002-2: keyword=특허 → 일치 문서 표출"""
        doc = self._make_doc(2, "특허법_주요_판례_분석.pdf", "지식재산법", 1)
        job = self._make_job()
        mock_db = self._make_mock_db([(doc, job)])

        total, result = document_service.get_docs_with_latest_job(mock_db, user_id=1, keyword="특허")

        assert total == 1
        assert "특허" in result[0].file_name

    def test_pagination_limit(self):
        """UT-DOC-002-3: skip=0, limit=10 → 10건 단위 조회"""
        pairs = [(self._make_doc(i, f"doc_{i}.pdf", "기타", 1), self._make_job()) for i in range(1, 11)]
        mock_db = self._make_mock_db(pairs)

        total, result = document_service.get_docs_with_latest_job(mock_db, user_id=1, skip=0, limit=10)

        assert total == 10
        assert len(result) == 10

    def test_empty_result_for_no_matching_category(self):
        """UT-DOC-002-1 엣지: 매칭 없는 카테고리 → 빈 목록"""
        mock_db = self._make_mock_db([])

        total, result = document_service.get_docs_with_latest_job(mock_db, user_id=1, category="민사법")

        assert total == 0
        assert result == []


# ── UT-DOC-003: 문서 상세·수정·삭제 ──────────────────────────────────────────


class TestDocDetail:
    """UT-DOC-003-1: 상세 원문·요약 표출"""

    def test_get_doc_detail_returns_doc(self, db, docs_with_jobs, users):
        """GET /documents/{id} → 원문·요약 출력"""
        doc1 = docs_with_jobs["doc1"]
        staff = users["staff"]

        result = document_service.get_docs_detail(db, doc1.doc_id, staff.user_id)

        assert result is not None
        assert result.doc_id == doc1.doc_id
        assert result.content_full is not None
        assert result.content_sum is not None

    def test_get_doc_detail_other_user_returns_none(self, db, docs_with_jobs, users):
        """UT-DOC-003-4: 타 사용자 문서 접근 차단"""
        doc1 = docs_with_jobs["doc1"]
        admin = users["admin"]

        result = document_service.get_docs_detail(db, doc1.doc_id, admin.user_id)

        assert result is None

    def test_get_deleted_doc_returns_none(self, db, docs_with_jobs, users):
        """삭제된 문서는 조회 불가"""
        doc1 = docs_with_jobs["doc1"]
        staff = users["staff"]
        doc1.is_deleted = True
        db.commit()

        result = document_service.get_docs_detail(db, doc1.doc_id, staff.user_id)

        assert result is None


class TestDocUpdate:
    """UT-DOC-003-2: 요약/카테고리 수정 저장 + history 기록"""

    def test_update_category_and_logs_history(self, db, docs_with_jobs, users):
        """카테고리 변경 → 저장 완료, history 변경 로그 기록"""
        doc1 = docs_with_jobs["doc1"]
        staff = users["staff"]
        payload = DocUpdate(category="형사법")

        result = document_service.update_doc(db, doc1.doc_id, staff.user_id, payload)

        assert result is not None
        assert result.category == "형사법"

        history = db.query(History).filter(History.user_id == staff.user_id).first()
        assert history is not None
        assert "카테고리" in history.change_text

    def test_update_summary_and_logs_history(self, db, docs_with_jobs, users):
        """요약 수정 → history 기록"""
        doc1 = docs_with_jobs["doc1"]
        staff = users["staff"]
        payload = DocUpdate(content_sum="새로운 요약 내용입니다.")

        result = document_service.update_doc(db, doc1.doc_id, staff.user_id, payload)

        assert result is not None
        assert result.content_sum == "새로운 요약 내용입니다."

        history = db.query(History).filter(History.user_id == staff.user_id).first()
        assert history is not None

    def test_update_other_user_doc_returns_none(self, db, docs_with_jobs, users):
        """타 사용자 문서 수정 시도 → 차단"""
        doc1 = docs_with_jobs["doc1"]
        admin = users["admin"]
        payload = DocUpdate(category="행정법")

        result = document_service.update_doc(db, doc1.doc_id, admin.user_id, payload)

        assert result is None


class TestDocSoftDelete:
    """UT-DOC-003-3: 소프트 삭제 + 벡터 색인 제거"""

    @patch("app.services.document_service.delete_document_by_id")
    def test_soft_delete_sets_is_deleted(self, mock_chroma_delete, db, docs_with_jobs, users):
        """DELETE /documents/{id} → is_deleted=true, ChromaDB 색인 삭제"""
        doc1 = docs_with_jobs["doc1"]
        staff = users["staff"]

        result = document_service.soft_delete_doc(db, doc1.doc_id, staff.user_id)

        assert result is True
        db.expire(doc1)
        deleted_doc = db.query(Document).filter(Document.doc_id == doc1.doc_id).first()
        assert deleted_doc.is_deleted is True
        mock_chroma_delete.assert_called_once_with(doc1.doc_id)

    @patch("app.services.document_service.delete_document_by_id")
    def test_soft_delete_other_user_doc_fails(self, mock_chroma_delete, db, docs_with_jobs, users):
        """타 사용자 문서 삭제 시도 → 차단"""
        doc1 = docs_with_jobs["doc1"]
        admin = users["admin"]

        result = document_service.soft_delete_doc(db, doc1.doc_id, admin.user_id)

        assert result is False
        mock_chroma_delete.assert_not_called()
