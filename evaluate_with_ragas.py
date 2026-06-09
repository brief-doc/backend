#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RAGAS를 사용하여 LLM의 답변 품질을 평가하는 스크립트
Retrieval-Augmented Generation Assessment를 통한 평가
"""

import json
import os
from pathlib import Path
from typing import List, Dict
import chromadb
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall
)
from datasets import Dataset

# ChromaDB 경로
CHROMA_DB_PATH = "./chroma_pdf_db"

class RAGASEvaluator:
    """RAGAS를 사용한 RAG 시스템 평가 클래스"""
    
    def __init__(self):
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        self.collection = self.chroma_client.get_collection(name="qa_collection")
        
    def retrieve_documents(self, query: str, num_docs: int = 3) -> List[str]:
        """ChromaDB에서 관련 문서 검색
        
        Args:
            query: 검색 쿼리
            num_docs: 반환할 문서 개수
            
        Returns:
            검색된 문서 리스트
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=num_docs,
                include=['documents', 'metadatas']
            )
            
            if results and results['documents']:
                # 빈 문서 필터링
                docs = [doc for doc in results['documents'][0] if doc and doc.strip()]
                return docs if docs else []
            return []
        except Exception as e:
            print(f"문서 검색 실패: {e}")
            return []
    
    def prepare_evaluation_dataset(self, test_samples: List[Dict]) -> Dataset:
        """평가용 데이터셋 준비
        
        Args:
            test_samples: 테스트 샘플 리스트
                         각 샘플: {
                             "question": 질문,
                             "answer": LLM 생성 답변,
                             "ground_truth": 정답 (선택사항)
                         }
        
        Returns:
            RAGAS 평가용 Dataset
        """
        eval_data = []
        
        for sample in test_samples:
            question = sample.get("question", "")
            answer = sample.get("answer", "")
            ground_truth = sample.get("ground_truth", answer)
            
            # 질문에서 관련 문서 검색
            contexts = self.retrieve_documents(question, num_docs=3)
            
            eval_data.append({
                "question": question,
                "answer": answer,
                "contexts": contexts,
                "ground_truth": ground_truth
            })
        
        return Dataset.from_dict({
            "question": [d["question"] for d in eval_data],
            "answer": [d["answer"] for d in eval_data],
            "contexts": [d["contexts"] for d in eval_data],
            "ground_truth": [d["ground_truth"] for d in eval_data]
        })
    
    def evaluate(self, test_samples: List[Dict]) -> Dict:
        """RAGAS 메트릭으로 평가
        
        Args:
            test_samples: 테스트 샘플 리스트
        
        Returns:
            평가 결과
        """
        print("=" * 70)
        print("RAGAS 평가 시작")
        print("=" * 70)
        
        # 데이터셋 준비
        print("\n📊 평가용 데이터셋 준비 중...")
        dataset = self.prepare_evaluation_dataset(test_samples)
        print(f"✓ 준비 완료: {len(dataset)} 샘플")
        
        # 평가 메트릭 설정
        print("\n🔍 평가 메트릭 계산 중...")
        metrics = [
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall
        ]
        
        try:
            # RAGAS 평가 실행
            results = evaluate(
                dataset,
                metrics=metrics,
                raise_exceptions=False  # 에러 발생 시에도 계속 진행
            )
            
            return results
        
        except Exception as e:
            print(f"✗ 평가 중 오류: {e}")
            return None
    
    def print_results(self, results):
        """평가 결과 출력
        
        Args:
            results: RAGAS 평가 결과
        """
        if results is None:
            print("평가 결과가 없습니다")
            return
        
        print("\n" + "=" * 70)
        print("✨ RAGAS 평가 결과")
        print("=" * 70)
        
        # 개별 메트릭
        print("\n📈 평가 메트릭:")
        
        metrics_info = {
            "faithfulness": "답변이 검색된 문서에 얼마나 충실한가 (0~1, 높을수록 좋음)",
            "answer_relevancy": "답변이 질문과 관련성이 얼마나 있는가 (0~1, 높을수록 좋음)",
            "context_precision": "검색된 문서가 얼마나 관련성 있는가 (0~1, 높을수록 좋음)",
            "context_recall": "검색된 문서가 필요한 정보를 얼마나 포함하는가 (0~1, 높을수록 좋음)"
        }
        
        if isinstance(results, dict):
            for metric_name, description in metrics_info.items():
                if metric_name in results:
                    value = results[metric_name]
                    if isinstance(value, (int, float)):
                        score = value
                    else:
                        try:
                            score = float(value)
                        except:
                            score = None
                    
                    if score is not None:
                        # 점수에 따라 이모지 추가
                        if score >= 0.8:
                            emoji = "✅"
                        elif score >= 0.6:
                            emoji = "⚠️ "
                        else:
                            emoji = "❌"
                        
                        print(f"\n   {emoji} {metric_name.upper()}: {score:.4f}")
                        print(f"      → {description}")
        
        # 전체 평균
        if isinstance(results, dict):
            valid_scores = []
            for key in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
                if key in results:
                    try:
                        valid_scores.append(float(results[key]))
                    except:
                        pass
            
            if valid_scores:
                avg_score = sum(valid_scores) / len(valid_scores)
                print(f"\n📊 평균 점수: {avg_score:.4f}")
                
                # 종합 평가
                if avg_score >= 0.8:
                    level = "매우 좋음 (Excellent)"
                elif avg_score >= 0.6:
                    level = "좋음 (Good)"
                elif avg_score >= 0.4:
                    level = "보통 (Fair)"
                else:
                    level = "개선 필요 (Poor)"
                
                print(f"   종합 평가: {level}")
        
        print("\n" + "=" * 70)

def create_sample_test_data() -> List[Dict]:
    """샘플 테스트 데이터 생성
    
    ChromaDB에서 실제 데이터를 가져와 테스트 데이터 생성
    """
    print("📚 테스트 데이터 생성 중...")
    
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_collection(name="qa_collection")
    
    # 임의의 샘플 문서 가져오기
    sample_results = collection.get(limit=5)
    
    test_samples = []
    
    if sample_results and sample_results['documents']:
        for i, (doc_id, doc_content) in enumerate(zip(
            sample_results['ids'],
            sample_results['documents']
        )):
            # 문서에서 질문과 답변 추출
            lines = doc_content.split('\n')
            
            # 질문 찾기 (Q: 로 시작하는 줄)
            questions = [line[2:].strip() for line in lines if line.startswith('Q:')]
            
            if questions:
                question = questions[0][:200]  # 처음 200자만 사용
                
                # 생성된 답변 (여기서는 샘플용으로 문서의 처음 부분 사용)
                answer = doc_content[:300]
                
                test_samples.append({
                    "question": question,
                    "answer": answer,
                    "ground_truth": doc_content[:500]  # 전체 문서를 정답으로 사용
                })
    
    print(f"✓ 생성 완료: {len(test_samples)}개 샘플")
    return test_samples

def main():
    """메인 평가 함수"""
    
    print("=" * 70)
    print("RAGAS를 사용한 LLM 답변 품질 평가")
    print("=" * 70 + "\n")
    
    # RAGAS 평가기 초기화
    evaluator = RAGASEvaluator()
    
    # 테스트 데이터 생성
    print("\n[단계 1] 테스트 데이터 준비")
    print("-" * 70)
    test_samples = create_sample_test_data()
    
    if not test_samples:
        print("⚠️  테스트 데이터를 생성할 수 없습니다")
        return
    
    print(f"\n테스트 샘플 미리보기:")
    for i, sample in enumerate(test_samples[:2], 1):
        print(f"\n  [{i}] 질문: {sample['question'][:100]}...")
    
    # 평가 실행
    print("\n\n[단계 2] RAGAS 평가 실행")
    print("-" * 70)
    results = evaluator.evaluate(test_samples)
    
    # 결과 출력
    print("\n[단계 3] 평가 결과 분석")
    print("-" * 70)
    evaluator.print_results(results)
    
    # 결과 저장
    if results:
        results_file = Path(__file__).parent / "ragas_evaluation_results.json"
        
        # 결과를 JSON 직렬화 가능한 형태로 변환
        results_dict = {}
        if isinstance(results, dict):
            for key, value in results.items():
                try:
                    results_dict[key] = float(value)
                except:
                    results_dict[key] = str(value)
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results_dict, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 결과 저장: {results_file}")

if __name__ == "__main__":
    main()
