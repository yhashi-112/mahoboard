# RAG機能統合 セットアップ手順

## 📋 概要

既存の「魔法の黒板」app.pyに、Q&A知識ベースを活用したRAG（検索拡張生成）機能を追加します。

---

## 🎯 実装方法の選択

### 方法A：簡易RAG（推奨・まず試す）
- **難易度**: ★☆☆
- **実装時間**: 30分
- **メリット**: 既存コードへの変更が最小限、すぐに動作確認可能
- **月額費用**: 約4,500円-7,500円（学生100名想定）

### 方法B：上級RAG（本格運用向け）
- **難易度**: ★★☆
- **実装時間**: 1時間
- **メリット**: ベクトル検索で高精度、OpenAI Assistants APIで管理が楽
- **月額費用**: 約7,500円-12,000円（学生100名想定）

**👉 まずは方法Aで試してみることを推奨します。**

---

## 🚀 方法A：簡易RAG 実装手順

### ステップ1: ディレクトリ構成の準備

プロジェクトフォルダを以下の構成にします：

```
your_project/
├── app.py                 # 既存の魔法の黒板
├── knowledge_base/        # 新規作成
│   ├── qa_knowledge_base_all.json          # 👈 必須
│   ├── qa_knowledge_base_all.txt           # オプション
│   ├── qa_knowledge_base_biostat.json      # オプション
│   ├── qa_knowledge_base_research_design.json
│   ├── qa_knowledge_base_ebm.json
│   ├── qa_knowledge_base_sensitivity.json
│   ├── qa_knowledge_base_drug_comparison.json
│   └── qa_knowledge_base_patient_info.json
├── .env
├── requirements.txt
└── ...（その他のファイル）
```

### ステップ2: knowledge_baseディレクトリ作成

```bash
# プロジェクトのルートディレクトリで実行
mkdir knowledge_base
```

### ステップ3: 知識ベースファイルの配置

Claude が作成した以下のファイルを `knowledge_base/` に配置：

- `qa_knowledge_base_all.json` （必須・93件のQ&A統合版）
- 他の個別ファイルはオプション

### ステップ4: app.pyのバックアップ

```bash
cp app.py app_backup.py
```

### ステップ5: RAG機能コードの追加

#### 5-1. 知識ベース読み込み関数を追加

`app.py` の **MODEL_NAME = "gpt-4o"** の直後（約65行目付近）に以下を追加：

```python
# ============================================================
# RAG機能: 知識ベース検索
# ============================================================

import json

# 知識ベースのパス
KNOWLEDGE_BASE_DIR = os.path.join(BASE_DIR, "knowledge_base")
KNOWLEDGE_BASE_PATH = os.path.join(KNOWLEDGE_BASE_DIR, "qa_knowledge_base_all.json")

# RAG有効化フラグ
RAG_ENABLED = True  # Falseにすると従来の動作

def load_knowledge_base():
    """知識ベース読み込み"""
    if not os.path.exists(KNOWLEDGE_BASE_PATH):
        print(f"[RAG] 知識ベースが見つかりません: {KNOWLEDGE_BASE_PATH}")
        return None
    
    try:
        with open(KNOWLEDGE_BASE_PATH, 'r', encoding='utf-8') as f:
            kb = json.load(f)
            print(f"[RAG] 知識ベース読み込み: {len(kb.get('qa_pairs', []))}件")
            return kb
    except Exception as e:
        print(f"[RAG] エラー: {e}")
        return None

def search_knowledge_base(question, max_results=3):
    """知識ベースから関連Q&Aを検索"""
    import re
    
    kb = load_knowledge_base()
    if not kb or "qa_pairs" not in kb:
        return []
    
    qa_pairs = kb["qa_pairs"]
    scored_pairs = []
    question_lower = question.lower()
    q_words = [w for w in re.split(r'[、。？！\s]+', question_lower) if len(w) > 1]
    
    for qa in qa_pairs:
        score = 0
        qa_question = qa.get("question", "").lower()
        qa_keywords = [kw.lower() for kw in qa.get("keywords", [])]
        
        # 質問文マッチ
        if question_lower in qa_question:
            score += 20
        
        for word in q_words:
            if word in qa_question:
                score += 5
            
            # キーワードマッチ
            for kw in qa_keywords:
                if word in kw or kw in word:
                    score += 8
        
        if score > 0:
            scored_pairs.append((score, qa))
    
    scored_pairs.sort(reverse=True, key=lambda x: x[0])
    
    if scored_pairs[:max_results]:
        ids = [qa.get('id') for _, qa in scored_pairs[:max_results]]
        print(f"[RAG] 質問「{question[:30]}...」→ {ids}")
    
    return [qa for score, qa in scored_pairs[:max_results]]

def format_context_from_kb(related_qas):
    """検索結果を文脈として整形"""
    if not related_qas:
        return ""
    
    context = "\n【参考：教科書・講義資料からの関連情報】\n"
    for i, qa in enumerate(related_qas, 1):
        context += f"\n{i}. {qa.get('question')}\n"
        answer = qa.get('answer', '')
        if len(answer) > 400:
            answer = answer[:400] + "..."
        context += f"   {answer}\n"
        if 'source' in qa:
            context += f"   （出典: {', '.join(qa['source'])}）\n"
    
    context += "\n【指示】上記を参考に回答してください。\n\n"
    return context

# RAG用プロンプト追加
RAG_INSTRUCTION = """
【知識ベース活用ルール】
- 上記の【参考情報】を優先的に参照してください
- 出典がある場合は明記してください
- 知識ベースにない内容は「講義範囲外」と伝えてください
"""
```

#### 5-2. 質問応答関数の修正

`student_view()` 関数内の質問応答部分（約1858-1881行目）を探して、
以下のように修正：

**修正前:**
```python
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
```

**修正後:**
```python
# RAG機能: 知識ベース検索
related_qas = search_knowledge_base(q, max_results=3) if RAG_ENABLED else []
kb_context = format_context_from_kb(related_qas)

# システムプロンプトとユーザーメッセージ作成
system_content = PHARMACY_GUARDRAILS + "\n" + STUDENT_STYLE_PROMPT
if kb_context:
    system_content += "\n" + RAG_INSTRUCTION

user_content = kb_context + "【学生からの質問】\n" + q

res = client.chat.completions.create(
    model=model,
    messages=[
        {
            "role": "system",
            "content": system_content,
        },
        {
            "role": "user",
            "content": user_content,
        },
    ],
    max_tokens=800,  # RAGで長くなるので増やす
    temperature=0.3,
)
draft = res.choices[0].message.content
```

その後の `self_check_answer` と `apply_classification_filter` はそのまま。

### ステップ6: 動作確認

#### 6-1. テストスクリプト実行

```bash
python test_rag.py
```

期待される出力:
```
============================================================
 RAG機能テスト
============================================================

【ステップ1】知識ベース読み込み
✅ 読み込み成功: 93件のQ&A

【ステップ2】検索テスト
------------------------------------------------------------

テスト1: 生物統計
質問: 正規分布とt分布の違いは何ですか？
検索結果: ['BS003', 'BS004', 'BS002']
✅ PASS: 期待されるQ&Aが見つかりました

...

🎉 全テストPASS！RAG機能は正常に動作しています。
```

#### 6-2. アプリ起動

```bash
streamlit run app.py
```

#### 6-3. 質問してみる

学生UIで以下の質問を試してみてください：

1. 「正規分布とt分布の違いは？」
2. 「RCTとは何ですか？」
3. 「感度が高い検査はいつ使いますか？」

**期待される動作:**
- コンソールに `[RAG] 質問「...」→ ['BS003', ...]` のようなログが出る
- 回答に「（参考：第2回講義）」のような出典が含まれる

---

## 🔧 トラブルシューティング

### 問題1: 知識ベースが読み込めない

**症状:**
```
[RAG] 知識ベースが見つかりません
```

**解決策:**
1. `knowledge_base/` ディレクトリが存在するか確認
2. `qa_knowledge_base_all.json` が配置されているか確認
3. ファイルパスを絶対パスで指定してみる

### 問題2: 関連情報が検索されない

**症状:**
どの質問でも検索結果が0件

**解決策:**
1. `test_rag.py` でテストして検索ロジックを確認
2. `search_knowledge_base()` 内の `print` でデバッグ
3. スコアリングの閾値を調整

### 問題3: 回答が長すぎる

**症状:**
回答が途中で切れる

**解決策:**
`max_tokens` を 800 → 1200 に増やす

---

## 📊 費用試算（方法A）

### 前提条件
- 学生数: 100名
- 1人あたり質問数: 10回/日
- 1ヶ月稼働日数: 20日
- 合計質問数: 100 × 10 × 20 = 20,000回/月

### トークン数概算
- 入力（質問 + 知識ベース文脈）: 平均500トークン/質問
- 出力（回答）: 平均300トークン/質問

### 月額費用
- 入力: 20,000 × 500 = 1000万トークン → $50
- 出力: 20,000 × 300 = 600万トークン → $90
- **合計: 約$140 (約21,000円)**

※実際の利用パターンによって変動します

---

## 🎉 完了！

これでRAG機能の統合は完了です。

### 次のステップ

1. **少人数でテスト**: まず10名程度の学生でテスト運用
2. **フィードバック収集**: 回答の質、検索精度を評価
3. **チューニング**: 必要に応じて検索ロジックを改善
4. **本格運用**: 全学生に展開

---

## 📚 参考資料

- `README_RAG.md` - 詳細な統合ガイド
- `test_rag.py` - テストスクリプト
- `rag_patch.py` - コードパッチ集

困ったときは、これらのファイルを参照してください。
