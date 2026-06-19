"""파인튜닝된 BGE-M3 임베딩 초기화 테스트 (chromadb 없이)"""
import sys
import os

# .env 로드
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

print("EMBED_PROVIDER:", os.getenv("EMBED_PROVIDER"))

from app.llm.embeddings import get_embeddings

print("get_embeddings() 호출...")
emb = get_embeddings()
print("임베딩 타입:", type(emb).__name__)

test_text = "민사법에 관한 계약 분쟁 사례"
print(f"테스트 텍스트: {test_text}")
vec = emb.embed_query(test_text)
print(f"벡터 차원: {len(vec)}")
print(f"벡터 앞 5개 값: {vec[:5]}")
print("SUCCESS")
