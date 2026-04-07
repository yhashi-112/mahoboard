#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAG機能テストスクリプト - test_rag.py

使い方:
1. knowledge_base/ディレクトリにQ&A知識ベースを配置
2. python test_rag.py を実行

このスクリプトでRAG機能が正しく動作するかテストできます。
"""

import os
import json
import sys

# 知識ベースのパス
KNOWLEDGE_BASE_PATH = "./knowledge_base/qa_knowledge_base_all.json"

def load_knowledge_base():
    """知識ベース読み込み"""
    if not os.path.exists(KNOWLEDGE_BASE_PATH):
        print(f"❌ エラー: 知識ベースが見つかりません")
        print(f"   パス: {KNOWLEDGE_BASE_PATH}")
        print(f"\n📁 knowledge_base/ディレクトリを作成し、")
        print(f"   qa_knowledge_base_all.json を配置してください。")
        return None
    
    with open(KNOWLEDGE_BASE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def search_knowledge_base(question, kb, max_results=3):
    """知識ベース検索"""
    import re
    
    qa_pairs = kb.get("qa_pairs", [])
    scored_pairs = []
    question_lower = question.lower()
    q_words = [w for w in re.split(r'[、。？！\s]+', question_lower) if len(w) > 1]
    
    for qa in qa_pairs:
        score = 0
        qa_question = qa.get("question", "").lower()
        qa_keywords = [kw.lower() for kw in qa.get("keywords", [])]
        
        if question_lower in qa_question:
            score += 20
        
        for word in q_words:
            if word in qa_question:
                score += 5
            
            for kw in qa_keywords:
                if word in kw or kw in word:
                    score += 8
        
        if score > 0:
            scored_pairs.append((score, qa))
    
    scored_pairs.sort(reverse=True, key=lambda x: x[0])
    return [qa for score, qa in scored_pairs[:max_results]]

def run_tests():
    """テスト実行"""
    print("="*70)
    print(" RAG機能テスト")
    print("="*70)
    
    # 知識ベース読み込み
    print("\n【ステップ1】知識ベース読み込み")
    kb = load_knowledge_base()
    if not kb:
        sys.exit(1)
    
    qa_count = len(kb.get("qa_pairs", []))
    print(f"✅ 読み込み成功: {qa_count}件のQ&A")
    
    # テストケース
    test_cases = [
        {
            "question": "正規分布とt分布の違いは何ですか？",
            "expected_ids": ["BS003", "BS004"],
            "category": "生物統計"
        },
        {
            "question": "RCTとは何ですか？",
            "expected_ids": ["RD010"],
            "category": "研究デザイン"
        },
        {
            "question": "PICOとは？",
            "expected_ids": ["EBM010"],
            "category": "EBM"
        },
        {
            "question": "感度が高い検査はどんな時に使いますか？",
            "expected_ids": ["SS040", "SS001"],
            "category": "感度・特異度"
        },
        {
            "question": "p値の意味を教えてください",
            "expected_ids": ["BS020", "BS021"],
            "category": "生物統計"
        },
    ]
    
    print("\n【ステップ2】検索テスト")
    print("-"*70)
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        question = test["question"]
        expected = test["expected_ids"]
        category = test["category"]
        
        print(f"\nテスト{i}: {category}")
        print(f"質問: {question}")
        
        # 検索実行
        results = search_knowledge_base(question, kb, max_results=3)
        
        if results:
            result_ids = [qa.get("id", "?") for qa in results]
            print(f"検索結果: {result_ids}")
            
            # 期待されるIDのいずれかが含まれているか
            if any(exp_id in result_ids for exp_id in expected):
                print("✅ PASS: 期待されるQ&Aが見つかりました")
                passed += 1
                
                # 詳細表示
                for qa in results[:1]:  # 最上位のみ表示
                    print(f"\n  【参照Q&A】")
                    print(f"  ID: {qa.get('id')}")
                    print(f"  質問: {qa.get('question')}")
                    print(f"  回答: {qa.get('answer', '')[:100]}...")
            else:
                print(f"❌ FAIL: 期待されるQ&Aが見つかりませんでした")
                print(f"   期待: {expected}")
                failed += 1
        else:
            print("❌ FAIL: 検索結果なし")
            failed += 1
    
    # 結果サマリー
    print("\n" + "="*70)
    print(" テスト結果")
    print("="*70)
    print(f"合計: {passed + failed}件")
    print(f"✅ PASS: {passed}件")
    print(f"❌ FAIL: {failed}件")
    
    if failed == 0:
        print("\n🎉 全テストPASS！RAG機能は正常に動作しています。")
    else:
        print("\n⚠️  一部テストが失敗しました。検索ロジックの調整が必要かもしれません。")
    
    print("="*70)

if __name__ == "__main__":
    run_tests()
