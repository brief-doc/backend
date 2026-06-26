BEGIN;

-- ── 역할 (role) ─────────────────────────────────────────────
INSERT INTO public.role (role_name, description) VALUES
    ('실무 담당자', '문서 업로드/요약/RAG 질의/기안 작성'),
    ('결재권자',   '상신된 기안 승인/반려'),
    ('관리자',     '사용자/권한 관리, 통계 조회')
ON CONFLICT (role_name) DO NOTHING;

-- ── 사용자 (users) ─────────────────────────────────────────────
INSERT INTO public.users -- 초기 비밀번호 000000
    (user_email, user_password, user_name, created_at)
VALUES
    -- 1) 시스템 관리자
    ('admin@agency.go.kr',
     '$5$rounds=535000$eWXQtRpuhm6Pp4Ta$iU/8OnPLQ7T6Jr0ExwXMP7uNvdllnabDN/u3e7WU8d8',
      '김관리', '2026-06-01 09:00:00.000001+09'),
 
    -- 2) 박과장 — 결재권자 겸 실무 (프론트엔드 박과장 케이스)
    ('park.jihun@agency.go.kr',
     '$5$rounds=535000$b7Ulg2rRKCGqdJgG$i9ubG0MFZANEMAq2s/zLJBW7g5X3T.JhkIHZT21Mm77',
      '박지훈', '2026-06-01 09:00:00.000002+09');
 
 -- ── 사용자역할 (user_role) ─────────────────────────────────────────────
INSERT INTO public.user_role 
(user_id, role_id)
VALUES(1,1),(1,2),(1,3),(2,1);


-- ── 문서 (doc) ─────────────────────────────────────────────
INSERT INTO public.doc
    (doc_id, file_name, file_type, category, content_full, content_sum, created_at, updated_at, is_deleted, user_id)
OVERRIDING SYSTEM VALUE
VALUES
    (1, '특허법_주요_판례_분석.pdf', 'pdf', '지식재산법',
     '2025년 주요 특허 침해 소송 판례 분석 보고서. 균등론 적용 기준 및 특허청구범위 해석 원칙. 대법원 2025다12345 판결 포함.',
     '○ 분석 대상: 2025년 특허 침해 소송 주요 판례\n○ 핵심 쟁점: 균등론 적용 기준, 청구범위 해석\n○ 주요 판결: 대법원 2025다12345',
     '2026-06-01 09:12:00+09', '2026-06-01 09:30:00+09', false, 2),

    (2, '행정처분_불복절차_안내.pdf', 'pdf', '행정법',
     '행정처분에 대한 이의신청·행정심판·행정소송 절차 안내. 처분 통지일로부터 90일 이내 행정심판 청구 가능. 집행정지 신청 요건 포함.',
     '○ 이의신청: 처분청에 60일 이내 제출\n○ 행정심판: 처분 통지일로부터 90일 이내\n○ 행정소송: 행정심판 재결 후 90일 이내\n○ 집행정지: 회복 어려운 손해 발생 우려 시',
     '2026-05-30 14:05:00+09', '2026-05-30 14:20:00+09', false, 2),

    (3, '형사소송_증거법칙_요약.pdf', 'pdf', '형사법',
     '형사소송법상 위법수집증거 배제법칙 및 전문증거 규정 요약. 피의자 자백의 증거능력 제한 원칙. 영장주의 예외 사유 정리.',
     '○ 위법수집증거 배제: 적법절차 위반 증거 원칙적 배제\n○ 자백 보강법칙: 자백만으로 유죄 불가\n○ 전문증거 원칙 배제, 예외 요건 명시\n○ 영장주의 예외: 긴급체포·현행범 체포',
     '2026-05-28 10:40:00+09', '2026-05-28 11:00:00+09', false, 1),

    (4, '민법_계약해제_효과_검토.pdf', 'pdf', '민사법',
     '민법상 계약 해제 시 원상회복 의무 및 손해배상 청구 범위 검토. 해제권 발생 요건(이행지체·이행불능·불완전이행) 및 법정해제·약정해제 비교.',
     '○ 해제권 발생: 이행지체·이행불능·불완전이행\n○ 원상회복 의무: 수령한 급부 반환, 이자 부가\n○ 손해배상: 이행이익 or 신뢰이익 청구 가능\n○ 법정해제 vs 약정해제 효과 비교',
     '2026-05-25 16:20:00+09', '2026-05-25 16:35:00+09', false, 1);

-- ── 작업 이력 (job) — 요약/임베딩/파이프라인 처리 ───────────
INSERT INTO public.job
    (job_id, job_start, job_finish, doc_id, user_id, job_type, job_status,
     pipeline_stage, is_cancelled, file_path, error_stage, error_message)
OVERRIDING SYSTEM VALUE
VALUES
    -- 기존 단순 요약/임베딩 Job (파이프라인 컬럼은 NULL)
    (1, '2026-06-01 09:13:00', '2026-06-01 09:14:30', 1, 2, 'summarize', 'success', NULL, NULL, NULL, NULL, NULL),
    (2, '2026-06-01 09:15:00', '2026-06-01 09:16:10', 1, 2, 'embed',     'success', NULL, NULL, NULL, NULL, NULL),
    (3, '2026-05-30 14:06:00', '2026-05-30 14:07:20', 2, 2, 'summarize', 'success', NULL, NULL, NULL, NULL, NULL),
    (4, '2026-05-28 10:41:00', '2026-05-28 10:42:30', 3, 1, 'summarize', 'success', NULL, NULL, NULL, NULL, NULL),
    (5, '2026-06-08 09:00:00', NULL,                  4, 1, 'summarize', 'running', NULL, NULL, NULL, NULL, NULL),
    (6, '2026-06-07 18:20:00', '2026-06-07 18:20:40', 4, 1, 'embed',     'failed',  NULL, NULL, NULL, NULL, NULL),

    -- 파이프라인 Job 샘플 (완료)
    (7, '2026-06-10 10:00:00', '2026-06-10 10:02:15', 1, 2, 'document_pipeline', 'completed',
     'completed', false, NULL, NULL, NULL),

    -- 파이프라인 Job 샘플 (OCR 단계 실패)
    (8, '2026-06-11 14:30:00', '2026-06-11 14:30:45', NULL, 2, 'document_pipeline', 'failed',
     'failed', false, NULL, 'ocr', '원문 텍스트를 추출할 수 없습니다. 스캔 이미지이거나 암호화된 파일일 수 있습니다.');

-- ── 변경 감사 로그 (history) ───────────────────────────────
INSERT INTO public.history
    (history_id, user_id, change_table, change_text, change_time)
OVERRIDING SYSTEM VALUE
VALUES
    (1, 2, 'doc',   'doc_id=1 문서 업로드 (특허법_주요_판례_분석.pdf)',    '2026-06-01 09:12:00+09'),
    (2, 1, 'doc',   'doc_id=3 문서 업로드 (형사소송_증거법칙_요약.pdf)',   '2026-05-28 10:40:00+09'),
    (3, 1, 'draft', 'draft_id=1 기안 승인 처리',                           '2026-06-01 15:10:00+09'),
    (4, 1, 'draft', 'draft_id=3 기안 반려 처리',                           '2026-05-31 11:25:00+09'),
    (5, 1, 'users', 'user_id=2 계정 권한 변경 (실무 담당자 부여)',          '2026-05-20 09:00:00+09');

-- ── RAG 질의 로그 (rag_query) ──────────────────────────────
INSERT INTO public.rag_query
    (query_id, user_id, query_text, answer_text, source_count, created_at)
OVERRIDING SYSTEM VALUE
VALUES
    (1, 2, '특허 침해 소송에서 균등론은 어떻게 적용되나요?',
        '특허법 주요 판례 분석에 따르면 균등론은 청구범위 문언과 다소 다르더라도 실질적으로 동일한 수단·기능·효과를 가지는 경우 침해로 인정됩니다. 대법원 2025다12345 판결 참고.', 1, '2026-06-02 10:15:00+09'),
    (2, 2, '행정처분에 이의가 있을 때 행정심판 청구 기간은?',
        '행정처분 불복절차 안내에 따르면 행정심판은 처분이 있음을 안 날로부터 90일, 처분이 있은 날로부터 180일 이내에 청구해야 합니다.', 1, '2026-06-03 11:40:00+09'),
    (3, 1, '형사소송에서 위법수집증거는 항상 배제되나요?',
        '형사소송법상 위법수집증거 배제법칙에 따라 원칙적으로 배제되지만, 예외적으로 적법절차를 실질적으로 위반하지 않은 경우 증거능력이 인정될 수 있습니다.', 1, '2026-05-30 15:05:00+09');

-- ── RAG 출처 매핑 (rag_query_ref) ──────────────────────────
INSERT INTO public.rag_query_ref
    (ref_id, query_id, doc_id, snippet)
OVERRIDING SYSTEM VALUE
VALUES
    (1, 1, 1, '균등론 적용 기준 및 특허청구범위 해석 원칙'),
    (2, 2, 2, '행정심판: 처분 통지일로부터 90일 이내'),
    (3, 2, 2, '이의신청: 처분청에 60일 이내 제출'),
    (4, 3, 3, '위법수집증거 배제: 적법절차 위반 증거 원칙적 배제');

-- ── 기안/결재 (draft) ──────────────────────────────────────
INSERT INTO public.draft
    (draft_id, author_id, title, content, source_doc_id, status, approver_id, reject_reason, decided_at, created_at, updated_at)
OVERRIDING SYSTEM VALUE
VALUES
    -- 승인됨
    (1, 2, '특허 침해 대응 방안 검토 의견서',
        '첨부된 특허법 주요 판례 분석을 토대로 당사 제품의 침해 위험성을 검토하였습니다. 균등론 적용 가능성이 낮아 소송 리스크가 제한적임을 확인하였으며, 예방 차원의 특허 포트폴리오 강화를 건의드립니다.',
        1, 'approved', 1, NULL, '2026-06-01 15:10:00+09', '2026-06-01 13:00:00+09', '2026-06-01 15:10:00+09'),

    -- 대기 (결재 정보 NULL)
    (2, 2, '행정처분 불복 행정심판 청구 승인 요청',
        '행정처분 불복절차 안내를 참고하여 처분 통지일로부터 90일 이내 행정심판을 청구하고자 합니다. 집행정지 신청도 병행 추진 예정이오니 승인을 요청드립니다.',
        2, 'pending', 1, NULL, NULL, '2026-06-01 14:32:00+09', '2026-06-01 14:32:00+09'),

    -- 반려됨
    (3, 2, '위법수집증거 배제 관련 소송 전략 보고',
        '형사소송 증거법칙 검토 결과를 바탕으로 위법수집증거 배제 신청 전략을 상신합니다.',
        3, 'rejected', 1,
        '소송 전략의 구체적인 근거가 부족합니다. 해당 증거의 수집 경위와 위법성 판단 기준을 추가로 기재하여 재상신해 주시기 바랍니다.',
        '2026-05-31 11:25:00+09', '2026-05-30 16:00:00+09', '2026-05-31 11:25:00+09');

-- ── 알림 (notification) ────────────────────────────────────
INSERT INTO public.notification
    (noti_id, user_id, message, link, is_read, created_at)
OVERRIDING SYSTEM VALUE
VALUES
    -- 실무자(박지훈=2) 수신
    (1, 2, '''특허 침해 대응 방안 검토 의견서'' 기안이 승인되었습니다', '/draft/1', false, '2026-06-01 15:10:00+09'),
    (2, 2, '''위법수집증거 배제 관련 소송 전략 보고'' 반려 — 사유 확인 필요', '/draft/3', false, '2026-05-31 11:25:00+09'),
    (3, 2, '''형사소송_증거법칙_요약'' 요약이 완료되었습니다', '/document/3', true,  '2026-05-28 10:43:00+09'),
    -- 결재권자(김관리=1) 수신
    (4, 1, '새로운 기안 ''행정처분 불복 행정심판 청구 승인 요청''이 상신되었습니다', '/draft/2', false, '2026-06-01 14:32:00+09'),
    (5, 1, '시스템 공지: 정기 점검이 예정되어 있습니다', NULL, true,  '2026-06-05 09:00:00+09');

-- ── 시퀀스 재정렬 (명시적 ID 삽입 후 다음 insert 충돌 방지) ──
SELECT setval(pg_get_serial_sequence('public.doc',           'doc_id'),     (SELECT MAX(doc_id)     FROM public.doc));
SELECT setval(pg_get_serial_sequence('public.job',           'job_id'),     (SELECT MAX(job_id)     FROM public.job));  -- 현재 max=8
SELECT setval(pg_get_serial_sequence('public.history',       'history_id'), (SELECT MAX(history_id) FROM public.history));
SELECT setval(pg_get_serial_sequence('public.rag_query',     'query_id'),   (SELECT MAX(query_id)   FROM public.rag_query));
SELECT setval(pg_get_serial_sequence('public.rag_query_ref', 'ref_id'),     (SELECT MAX(ref_id)     FROM public.rag_query_ref));
SELECT setval(pg_get_serial_sequence('public.draft',         'draft_id'),   (SELECT MAX(draft_id)   FROM public.draft));
SELECT setval(pg_get_serial_sequence('public.notification',  'noti_id'),    (SELECT MAX(noti_id)    FROM public.notification));

COMMIT;