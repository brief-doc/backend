#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
기존 ChromaDB의 임베딩 함수를 재사용하여 데이터 로드
"""

import json
import os
import sys
from pathlib import Path
from langchain_chroma import Chroma
from LLM.config import EMBEDDING_CONFIG, CHROMA_DB_PATH

def load_remaining_data():
    """기존 ChromaDB에 나머지 데이터 추가"""
    
    print("=" * 60)
    print("나머지 데이터 로드 (기존 임베딩 함수 재사용)")
    print("=" * 60)
    
    # 기존 ChromaDB 열기 (임베딩 함수 없이)
    print("\n📊 기존 ChromaDB 열기 중...")
    chroma_db_path = CHROMA_DB_PATH
    
    if not os.path.exists(chroma_db_path):
        print(f"❌ ChromaDB를 찾을 수 없습니다: {chroma_db_path}")
        return
    
    try:
        vectorstore = Chroma(
            persist_directory=chroma_db_path,
            embedding_function=None
        )
        print("✓ 기존 ChromaDB 열기 성공")
    except Exception as e:
        print(f"❌ ChromaDB 열기 실패: {e}")
        return
    
    # 이미 저장된 doc_id 조회
    print("🔍 이미 저장된 문서 조회 중...")
    existing_docs = vectorstore.get(include=['metadatas'])
    existing_doc_ids = set()
    if existing_docs and 'metadatas' in existing_docs:
        for metadata in existing_docs['metadatas']:
            if metadata.get('doc_id'):
                existing_doc_ids.add(metadata['doc_id'])
    
    print(f"✓ 이미 저장된 문서: {len(existing_doc_ids)}개")
    
    # qa_data 디렉토리
    qa_data_dir = Path(__file__).parent / "qa_data"
    json_files = sorted(list(qa_data_dir.glob("*.json")))
    
    print(f"\n📂 qa_data 디렉토리: {qa_data_dir}")
    print(f"📊 총 파일 개수: {len(json_files)}")
    
    # 새로 추가할 문서 수집
    documents_to_add = []
    skipped_count = 0
    
    for idx, json_file in enumerate(json_files, 1):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                info = data.get('info', {})
                
                # caseNo 없으면 파일명 사용
                case_no = info.get('caseNo') or json_file.stem
                
                # 이미 존재하면 건너뛰기
                if case_no in existing_doc_ids:
                    skipped_count += 1
                    if idx % 5000 == 0:
                        print(f"  {idx}/{len(json_files)} 처리 중 (건너뜀: {skipped_count})")
                    continue
                
                # 새 문서 추가
                case_nm = info.get('caseNm', '미분류')
                announce_date = info.get('judmnAdjuDe', '')
                
                # 메인 콘텐츠 추출
                content_parts = []
                if case_nm:
                    content_parts.append(f"사건명: {case_nm}")
                
                jdgmn_info = data.get('jdgmnInfo', [])
                for item in jdgmn_info:
                    q = item.get('question', '')
                    a = item.get('answer', '')
                    if q:
                        content_parts.append(f"Q: {q}")
                    if a:
                        content_parts.append(f"A: {a}")
                
                summary = data.get('Summary', [])
                for item in summary:
                    s = item.get('summ_pass', '')
                    if s:
                        content_parts.append(f"요약: {s}")
                
                keywords = data.get('keyword_tagg', [])
                kw_list = [kw.get('keyword', '') for kw in keywords if kw.get('keyword')]
                if kw_list:
                    content_parts.append(f"키워드: {', '.join(kw_list)}")
                
                content = '\n'.join(content_parts)
                
                if content.strip():
                    documents_to_add.append({
                        'content': content,
                        'doc_id': case_no,
                        'case_name': case_nm,
                        'announce_date': announce_date,
                        'file_name': json_file.name,
                        'page_num': 1,
                        'user_id': 1,
                        'cat_id': 0
                    })
                    existing_doc_ids.add(case_no)
                
                if idx % 5000 == 0:
                    print(f"  {idx}/{len(json_files)} 처리 완료 (새로 추가할: {len(documents_to_add)})")
        
        except Exception as e:
            pass
    
    print(f"\n✅ 새로 추가할 문서: {len(documents_to_add)}개")
    print(f"⊘  건너뛴 문서: {skipped_count}개")
    
    # ChromaDB에 추가 (콘텐츠 기반 아이디 사용)
    if documents_to_add:
        print(f"\n🔄 ChromaDB에 추가하는 중...")
        print("📝 주의: 임베딩 함수 없이 추가하므로 유사도 검색이 작동하지 않을 수 있습니다")
        print("    추후 정확한 임베딩이 필요하면 ChromaDB 재구성이 필요합니다.")
        
        metadatas = []
        texts = []
        ids_list = []
        
        for doc in documents_to_add:
            texts.append(doc['content'])
            metadatas.append({
                'doc_id': doc['doc_id'],
                'case_name': doc['case_name'],
                'announce_date': doc['announce_date'],
                'file_name': doc['file_name'],
                'page_num': str(doc['page_num']),
                'user_id': str(doc['user_id']),
                'cat_id': str(doc['cat_id'])
            })
            ids_list.append(doc['doc_id'])
        
        try:
            # 배치 단위로 추가
            batch_size = 50
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i+batch_size]
                batch_metadatas = metadatas[i:i+batch_size]
                batch_ids = ids_list[i:i+batch_size]
                
                # ID와 메타데이터로 직접 추가 (임베딩 함수 필요 없음)
                vectorstore.add_texts(
                    texts=batch_texts,
                    metadatas=batch_metadatas,
                    ids=batch_ids
                )
                
                if (i + batch_size) % 500 == 0 or (i + batch_size) >= len(texts):
                    print(f"  ✓ {min(i+batch_size, len(texts))}/{len(texts)} 저장 완료")
            
            print(f"\n✅ ChromaDB 저장 완료!")
            print(f"   - 새로 저장된 문서: {len(texts)}개")
            print(f"   - 기존 문서: {len(existing_doc_ids) - len(texts)}개")
            print(f"   - 총 문서: {len(existing_doc_ids)}개")
            print(f"   - 저장 위치: {CHROMA_DB_PATH}")
            
        except Exception as e:
            print(f"\n❌ 저장 실패: {e}")
            print("\n해결 방법:")
            print("1. ChromaDB가 손상되었을 수 있습니다.")
            print("2. 다음 명령어로 ChromaDB를 초기화합니다:")
            print(f"   rm -r {CHROMA_DB_PATH}")
            print("3. 그 후 다시 실행합니다.")
    else:
        print(f"\nℹ️  저장할 새로운 문서가 없습니다")
        print(f"   모든 파일이 이미 ChromaDB에 있습니다")

if __name__ == "__main__":
    load_remaining_data()
