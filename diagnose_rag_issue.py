#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RAG 시스템 문제 진단 스크립트
"""

import chromadb
import requests
import os
from pathlib import Path

CHROMA_DB_PATH = "./chroma_pdf_db"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("CURRENT_MODEL", "gemma3n:e2b")

print("=" * 70)
print("RAG 시스템 문제 진단")
print("=" * 70)

# 1. ChromaDB 검색 테스트
print("\n[진단 1] ChromaDB 검색 결과 확인")
print("-" * 70)

try:
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_collection(name="qa_collection")
    
    question = "국가유공자 등록 신청 시 신체검사가 필요한가요?"
    print(f"질문: {question}\n")
    
    results = collection.query(
        query_texts=[question],
        n_results=3
    )
    
    print("검색 결과:")
    if results['documents']:
        for i, docs in enumerate(results['documents']):
            print(f"\n  [쿼리 {i}]")
            for j, doc in enumerate(docs):
                if doc:
                    print(f"    문서 {j+1}: {len(doc)}자")
                    print(f"    내용: {doc[:100]}...")
                else:
                    print(f"    문서 {j+1}: [비어있음]")
    
except Exception as e:
    print(f"✗ 검색 오류: {e}")

# 2. OLLAMA 모델 상태 확인
print("\n\n[진단 2] OLLAMA 모델 상태")
print("-" * 70)

try:
    response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
    if response.status_code == 200:
        models = response.json().get('models', [])
        
        print(f"설치된 모델: {len(models)}개\n")
        
        for model in models[:5]:
            name = model.get('name', '')
            size = model.get('size', 0)
            size_gb = size / (1024**3)
            print(f"  - {name} ({size_gb:.1f}GB)")
            
            if name == LLM_MODEL or LLM_MODEL in name:
                print(f"    ✓ 사용할 모델: {name}")
    else:
        print(f"✗ OLLAMA 응답 실패: {response.status_code}")
        
except Exception as e:
    print(f"✗ OLLAMA 연결 오류: {e}")

# 3. 빠른 생성 테스트 (짧은 프롬프트)
print("\n\n[진단 3] 빠른 생성 테스트")
print("-" * 70)

try:
    print(f"모델: {LLM_MODEL}")
    print("프롬프트: 민사법이란?")
    print("대기 중... (최대 10초)")
    
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": "민사법이란?",
            "stream": False,
            "temperature": 0.5
        },
        timeout=15
    )
    
    if response.status_code == 200:
        result = response.json()
        answer = result.get("response", "").strip()
        print(f"✓ 응답 성공")
        print(f"답변: {answer[:100]}...")
    else:
        print(f"✗ 응답 실패: {response.status_code}")
        
except requests.exceptions.Timeout:
    print(f"✗ 타임아웃 (모델이 너무 느림)")
except Exception as e:
    print(f"✗ 오류: {e}")

print("\n" + "=" * 70)
print("진단 완료")
print("=" * 70)
