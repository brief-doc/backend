"""청킹 전략 모음 — 교체 가능한 레고 블록

사용법:
    from .chunker import pdf_splitter, markdown_splitter, split_by_headers

레고 교체:
    pdf_splitter / markdown_splitter 를 원하는 Splitter 로 교체하면
    ingest.py 전체에 즉시 반영됩니다.

주의:
    langchain_text_splitters 는 일부 환경에서 segfault 를 유발하므로
    순수 Python 구현 SimpleCharacterSplitter 를 사용합니다.
"""

from __future__ import annotations

from langchain_core.documents import Document

# ── PDF 기본값 ────────────────────────────────────────────────────────────────
PDF_CHUNK_SIZE = 1000
PDF_CHUNK_OVERLAP = 200

# ── 마크다운 기본값 ───────────────────────────────────────────────────────────
MD_CHUNK_SIZE = 500
MD_CHUNK_OVERLAP = 50


# ── 순수 Python 텍스트 분할기 ─────────────────────────────────────────────────
class SimpleCharacterSplitter:
    """langchain_text_splitters 없이 동작하는 경량 텍스트 분할기.

    separators 리스트 순서대로 시도하여 chunk_size 이하로 분할합니다.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: list[str] | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", "。", "，", " ", ""]

    def split_text(self, text: str) -> list[str]:
        """텍스트를 chunk_size 이하 조각으로 분할합니다."""
        if not text:
            return []
        chunks: list[str] = []
        self._split(text, self.separators, chunks)
        return [c for c in chunks if c.strip()]

    def _split(self, text: str, seps: list[str], out: list[str]) -> None:
        sep = ""
        remaining = list(seps)
        while remaining:
            s = remaining.pop(0)
            if s == "" or s in text:
                sep = s
                break

        parts = text.split(sep) if sep else [text]
        current = ""
        for part in parts:
            candidate = (current + sep + part).lstrip(sep) if current else part
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    out.append(current)
                    # overlap: 마지막 chunk_overlap 글자를 다음 청크 앞에 붙임
                    current = current[-self.chunk_overlap :] + sep + part if self.chunk_overlap else part
                else:
                    # part 자체가 너무 크면 재귀 분할
                    if remaining:
                        self._split(part, list(remaining), out)
                    else:
                        # 더 이상 구분자 없음 → 강제 슬라이싱
                        for i in range(0, len(part), self.chunk_size - self.chunk_overlap):
                            out.append(part[i : i + self.chunk_size])
                    current = ""
        if current:
            out.append(current)

    def create_documents(
        self,
        texts: list[str],
        metadatas: list[dict] | None = None,
    ) -> list[Document]:
        """텍스트 리스트를 Document 리스트로 변환합니다."""
        docs: list[Document] = []
        for i, text in enumerate(texts):
            meta = metadatas[i] if metadatas else {}
            for chunk in self.split_text(text):
                docs.append(Document(page_content=chunk, metadata=dict(meta)))
        return docs

    def split_documents(self, documents: list[Document]) -> list[Document]:
        """Document 리스트를 청크 단위로 분할합니다.

        langchain TextSplitter 호환 메서드.
        기존 metadata 를 그대로 복사합니다.
        """
        result: list[Document] = []
        for doc in documents:
            for chunk in self.split_text(doc.page_content):
                result.append(Document(page_content=chunk, metadata=dict(doc.metadata)))
        return result


# ── 싱글톤 splitter 인스턴스 ──────────────────────────────────────────────────
pdf_splitter = SimpleCharacterSplitter(
    chunk_size=PDF_CHUNK_SIZE,
    chunk_overlap=PDF_CHUNK_OVERLAP,
)

markdown_splitter = SimpleCharacterSplitter(
    chunk_size=MD_CHUNK_SIZE,
    chunk_overlap=MD_CHUNK_OVERLAP,
    separators=["\n\n", "\n", "。", "，", ""],
)


def split_by_headers(content: str) -> list[Document]:
    """마크다운 헤더(#, ##, ###) 기준으로 청킹합니다.

    MarkdownHeaderTextSplitter 대신 직접 구현하여 의존성 segfault 를 방지합니다.
    반환 Document 의 metadata 에 'section' 키로 섹션 제목이 포함됩니다.
    """
    docs: list[Document] = []
    current_lines: list[str] = []
    current_section = "본문"

    for line in content.split("\n"):
        if line.startswith("#"):
            # 이전 청크 저장
            text = "\n".join(current_lines).strip()
            if len(text) > 10:
                docs.append(Document(page_content=text, metadata={"section": current_section}))
            # 새 섹션 시작
            current_section = line.lstrip("#").strip() or "본문"
            current_lines = [line]
        else:
            current_lines.append(line)

    # 마지막 청크
    text = "\n".join(current_lines).strip()
    if len(text) > 10:
        docs.append(Document(page_content=text, metadata={"section": current_section}))

    return docs


def split_by_size(
    content: str,
    chunk_size: int = MD_CHUNK_SIZE,
    chunk_overlap: int = MD_CHUNK_OVERLAP,
) -> list[Document]:
    """글자 수 기준으로 청킹합니다 (커스텀 크기 지정 가능)."""
    splitter = SimpleCharacterSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "，", ""],
    )
    return splitter.create_documents([content])
