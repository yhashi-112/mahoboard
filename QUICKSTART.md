# 🚀 RAG機能統合 - クイックスタートガイド

## 今すぐ始める3ステップ

### ステップ1: ディレクトリ作成とファイル配置（2分）

```bash
# プロジェクトフォルダに移動
cd /path/to/your/project

# knowledge_baseディレクトリを作成
mkdir -p knowledge_base

# ダウンロードしたファイルを配置
# 1. qa_knowledge_base_all.json を knowledge_base/ に配置
# 2. app.py を既存のapp.pyと置き換え（バックアップ推奨）
```

### ステップ2: 動作確認（1分）

```bash
# テストスクリプト実行（オプション）
python test_rag.py

# 期待される出力:
# ✅ 読み込み成功: 93件のQ&A
# ✅ PASS: 3件以上
```

### ステップ3: アプリ起動（1分）

```bash
streamlit run app.py
```

ブラウザで http://localhost:8501 を開く

---

## ✅ 動作確認

学生UIで以下を試してください：

1. **質問**: 「RCTとは何ですか？」
   - 期待: 研究デザインの知識ベースを参照した回答

2. **サイドバー確認**:
   - 「📚 RAG知識ベース」セクションに
   - 「✅ 93件のQ&A読込済」が表示されているか

3. **コンソールログ確認**:
   ```
   [RAG] 知識ベース読み込み成功: 93件のQ&A
   [RAG] 質問「RCTとは...」→ 参照: ['Q042', ...]
   ```

---

## 📁 必要なファイル構成

```
your_project/
├── app.py                          # ← RAG統合版
├── knowledge_base/                 # ← 新規作成
│   └── qa_knowledge_base_all.json # ← 必須
├── .env                            # ← 既存
└── requirements.txt                # ← 既存
```

---

## ⚠️ トラブルシューティング

### エラー: 知識ベースが見つかりません

```bash
# 確認
ls -la knowledge_base/qa_knowledge_base_all.json

# なければ
mkdir -p knowledge_base
cp qa_knowledge_base_all.json knowledge_base/
```

### エラー: モジュールがありません

```bash
pip install -r requirements.txt
```

---

## 📖 詳細ガイド

詳しい説明は `README_RAG統合完了.md` を参照してください。

---

## 🎉 完了！

これで「魔法の黒板」のRAG機能統合は完了です。

**次のステップ:**
1. 少人数で動作確認
2. フィードバック収集
3. 必要に応じて知識ベース拡充

**作成日**: 2024年12月24日
