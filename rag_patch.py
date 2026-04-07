#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAG機能統合パッチ for app.py

このコードを app.py の適切な位置に挿入してください
"""

import json

# ============================================================
# 【追加1】app.pyの冒頭付近（MODEL_NAME定義の後）に追加
# ============================================================

# RAG機能: 知識ベース検索
KNOWLEDGE_BASE_DIR = os.path.join(BASE_DIR, "knowledge_base")
KNOWLEDGE_BASE_PATH = os.path.join(KNOWLEDGE_BASE_DIR, "qa_knowledge_base_all.json")

# RAG有効化フラグ（環境変数で制御可能）
RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"

def load_knowledge_base():
    """知識ベース（統合版）を読み込む"""
    if not os.path.exists(KNOWLEDGE_BASE_PATH):
        print(f"[RAG] 知識ベースが見つかりません: {KNOWLEDGE_BASE_PATH}")
        return None
    
    try:
        with open(KNOWLEDGE_BASE_PATH, 'r', encoding='utf-8') as f:
            kb = json.load(f)
            print(f"[RAG] 知識ベース読み込み成功: {len(kb.get('qa_pairs', []))}件のQ&A")
            return kb
    except Exception as e:
        print(f"[RAG] 知識ベース読み込みエラー: {e}")
        return None

def search_knowledge_base(question, max_results=3):
    """
    知識ベースから関連するQ&Aを検索（簡易版：キーワードマッチング）
    
    Args:
        question: 学生の質問文
        max_results: 返す最大件数
        
    Returns:
        関連するQ&Aのリスト（スコア順）
    """
    kb = load_knowledge_base()
    if not kb or "qa_pairs" not in kb:
        return []
    
    qa_pairs = kb["qa_pairs"]
    scored_pairs = []
    question_lower = question.lower()
    
    # 質問文を単語に分割（簡易版）
    import re
    q_words = [w for w in re.split(r'[、。？！\s]+', question_lower) if len(w) > 1]
    
    for qa in qa_pairs:
        score = 0
        qa_question = qa.get("question", "").lower()
        qa_answer = qa.get("answer", "").lower()
        qa_keywords = [kw.lower() for kw in qa.get("keywords", [])]
        
        # 1. 質問文の完全マッチ（最高スコア）
        if question_lower in qa_question:
            score += 20
        
        # 2. 質問文の部分マッチ
        for word in q_words:
            if word in qa_question:
                score += 5
        
        # 3. キーワードマッチ
        for word in q_words:
            for kw in qa_keywords:
                if word in kw or kw in word:
                    score += 8
        
        # 4. 回答文にマッチ（低スコア）
        for word in q_words:
            if word in qa_answer:
                score += 1
        
        # 5. カテゴリマッチ
        category = qa.get("category", "").lower()
        for word in q_words:
            if word in category:
                score += 3
        
        if score > 0:
            scored_pairs.append((score, qa))
    
    # スコア順にソート
    scored_pairs.sort(reverse=True, key=lambda x: x[0])
    
    # デバッグ出力
    if scored_pairs[:max_results]:
        top_ids = [qa.get('id', '?') for _, qa in scored_pairs[:max_results]]
        print(f"[RAG] 質問「{question[:30]}...」→ 参照: {top_ids}")
    
    # 上位max_results件を返す
    return [qa for score, qa in scored_pairs[:max_results]]

def format_context_from_kb(related_qas):
    """検索結果を文脈として整形"""
    if not related_qas:
        return ""
    
    context = "\n" + "="*60 + "\n"
    context += "【参考：教科書・講義資料からの関連情報】\n"
    context += "="*60 + "\n"
    
    for i, qa in enumerate(related_qas, 1):
        context += f"\n▼ 参考{i}: {qa.get('question', '')}\n"
        answer = qa.get('answer', '')
        # 回答が長すぎる場合は省略
        if len(answer) > 500:
            answer = answer[:500] + "..."
        context += f"{answer}\n"
        
        if 'source' in qa and qa['source']:
            context += f"（出典: {', '.join(qa['source'])}）\n"
    
    context += "\n" + "="*60 + "\n"
    context += "【指示】上記の参考情報を基に、学生の質問に答えてください。\n"
    context += "参考情報にない内容の場合は、一般的な知識で回答しつつ「詳しくは教科書を確認してください」と伝えてください。\n"
    context += "="*60 + "\n\n"
    
    return context

# RAG用の追加プロンプト
RAG_SYSTEM_INSTRUCTION = """
【知識ベース活用ルール】
- 上記の【参考：教科書・講義資料からの関連情報】が提供されている場合、その内容を優先的に参照してください
- 参考情報の内容と矛盾しないように回答してください
- 出典が記載されている場合は、回答の最後に「（参考：〜）」として明記してください
- 参考情報にない内容を質問された場合は、一般的な知識で回答しつつ「この内容は現在の講義範囲外です」または「詳しくは教科書のXXページを確認してください」と伝えてください
"""

# ============================================================
# 【追加2】student_view()関数内の質問応答部分を修正
# 元のコード（約1858-1881行目）を以下に置き換え
# ============================================================

def ask_with_rag(question, model=MODEL_NAME, max_tokens=800):
    """
    RAG機能を使って質問に回答
    
    Args:
        question: 学生の質問
        model: 使用するモデル名
        max_tokens: 最大トークン数
        
    Returns:
        回答テキスト
    """
    # RAGが無効の場合は通常の処理
    if not RAG_ENABLED:
        res = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": PHARMACY_GUARDRAILS + "\n" + STUDENT_STYLE_PROMPT,
                },
                {
                    "role": "user",
                    "content": question,
                },
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return res.choices[0].message.content
    
    # RAG有効: 知識ベースから関連情報を検索
    related_qas = search_knowledge_base(question, max_results=3)
    kb_context = format_context_from_kb(related_qas)
    
    # システムプロンプトにRAG指示を追加
    system_prompt = PHARMACY_GUARDRAILS + "\n" + STUDENT_STYLE_PROMPT + "\n" + RAG_SYSTEM_INSTRUCTION
    
    # ユーザーメッセージに文脈を追加
    user_message = kb_context + "【学生からの質問】\n" + question
    
    # GPTに質問
    res = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_message,
            },
        ],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    
    return res.choices[0].message.content

# ============================================================
# 【修正3】student_view()内の該当箇所を以下のように変更
# 元: 1858-1881行目付近
# ============================================================

# 修正前のコードを探して、以下のように変更:

"""
# === 元のコード（削除または コメントアウト） ===
res = client.chat.completions.create(
    model=model,
    messages=[
        {
            "role": "system",
            "content": PHARMACY_GUARDRAILS + "\n" + STUDENT_STYLE_PROMPT,
        },
        {
            "role": "user",
            "content": q,
        },
    ],
    max_tokens=600,
    temperature=0.3,
)
draft = res.choices[0].message.content

# === 新しいコード（RAG対応） ===
draft = ask_with_rag(q, model=model, max_tokens=800)
"""

# その後、self_check_answer と apply_classification_filter はそのまま継続
# checked = self_check_answer(model, PHARMACY_GUARDRAILS, q, draft, silent=True)
# ans = apply_classification_filter(checked, q)

# ============================================================
# 【追加4】StreamlitのサイドバーにRAG設定を追加（オプション）
# ============================================================

# サイドバーに以下を追加:
"""
with st.sidebar:
    st.divider()
    st.subheader("⚙️ RAG設定")
    
    # 知識ベースの状態表示
    kb = load_knowledge_base()
    if kb:
        qa_count = len(kb.get("qa_pairs", []))
        st.success(f"✅ 知識ベース: {qa_count}件のQ&A")
    else:
        st.error("❌ 知識ベースが読み込めません")
    
    # RAG有効/無効切り替え
    global RAG_ENABLED
    RAG_ENABLED = st.checkbox(
        "RAG機能を使用",
        value=RAG_ENABLED,
        help="教科書・講義資料の知識ベースを参照して回答します"
    )
"""

print("[RAG] パッチファイル読み込み完了")
