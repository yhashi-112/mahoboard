import streamlit as st
import os
from dotenv import load_dotenv
from openai import OpenAI
import google.generativeai as genai
from anthropic import Anthropic
import json
from datetime import datetime, timedelta
import glob
import pandas as pd
from io import BytesIO
from collections import Counter

# 環境変数の読み込み
load_dotenv()

# ページ設定
st.set_page_config(
    page_title="魔法の黒板 - 教員用",
    page_icon="👨‍🏫",
    layout="wide"
)

# APIクライアントの初期化
@st.cache_resource
def initialize_clients():
    openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    gemini_api_key = os.getenv('GEMINI_API_KEY') or st.secrets.get('GEMINI_API_KEY', '')
    if gemini_api_key:
        genai.configure(api_key=gemini_api_key)
    anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    return openai_client, anthropic_client

openai_client, anthropic_client = initialize_clients()

# カテゴリーの読み込み・保存
def load_categories():
    try:
        with open('categories.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        default_categories = [
            "情報",
            "情報源",
            "情報の収集・評価・加工・提供・管理",
            "EBM",
            "生物統計",
            "研究デザインと解析",
            "医薬品の採用・比較・評価",
            "患者情報とその収集・評価・管理",
            "その他"
        ]
        save_categories(default_categories)
        return default_categories

def save_categories(categories):
    with open('categories.json', 'w', encoding='utf-8') as f:
        json.dump(categories, f, ensure_ascii=False, indent=2)

# 知識ベースの読み込み・保存
def load_knowledge_base():
    try:
        with open('knowledge_base.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_knowledge_base(kb):
    with open('knowledge_base.json', 'w', encoding='utf-8') as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)

# ログファイルの読み込み
def load_logs():
    log_files = glob.glob("logs/*.json")
    logs = []
    for file in log_files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                log = json.load(f)
                logs.append(log)
        except:
            continue
    return sorted(logs, key=lambda x: x.get('timestamp', ''), reverse=True)

# ログをDataFrameに変換
def logs_to_dataframe(logs):
    """ログデータをDataFrameに変換"""
    if not logs:
        return pd.DataFrame()
    
    data = []
    for log in logs:
        row = {
            '日時': log.get('datetime', ''),
            'タイムスタンプ': log.get('timestamp', ''),
            'ニックネーム': log.get('nickname', '不明'),
            'モード': log.get('mode', ''),
            '学生選択カテゴリー': log.get('student_selected_category', log.get('category', 'なし')),  # 互換性維持
            'AI判定カテゴリー': ', '.join(log.get('ai_detected_categories', [])) if log.get('ai_detected_categories') else '',
            'カテゴリー不一致': '⚠️' if log.get('category_mismatch', False) else '',
            'ブロック': '🚫' if log.get('is_blocked', False) else '',
            'ブロック理由': log.get('block_reason', ''),
            'APIプロバイダー': log.get('api_provider', ''),
            'モデル': log.get('model', ''),
            '難易度': log.get('difficulty', ''),
            '問題数': log.get('num_problems', ''),
            '質問': log.get('question', ''),
            '回答': log.get('answer', '')
        }
        data.append(row)
    
    return pd.DataFrame(data)

# Excelファイルの生成
def create_excel(df):
    """DataFrameからExcelファイルを生成"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='学習ログ')
        
        # 列幅の自動調整
        worksheet = writer.sheets['学習ログ']
        for idx, col in enumerate(df.columns):
            max_length = max(
                df[col].astype(str).apply(len).max(),
                len(col)
            )
            # 日本語文字を考慮して幅を調整
            adjusted_width = min(max_length * 1.2 + 2, 50)
            worksheet.column_dimensions[chr(65 + idx)].width = adjusted_width
    
    output.seek(0)
    return output

# FAQ分析
def analyze_faq(logs, top_n=10):
    """よく聞かれる質問を抽出"""
    questions = [log.get('question', '') for log in logs if log.get('mode') == '質問応答']
    question_counts = Counter(questions)
    # 空文字列を除外
    filtered_counts = {q: c for q, c in question_counts.items() if q.strip()}
    # Counterオブジェクトに戻す
    filtered_counter = Counter(filtered_counts)
    return filtered_counter.most_common(top_n)

# つまずきポイント分析
def analyze_stumbling_points(logs):
    """カテゴリー別の質問集中度を分析（AI判定カテゴリーを優先使用）"""
    category_counts = {}
    for log in logs:
        # AI判定カテゴリーがあればそれを使用、なければ学生選択カテゴリーを使用
        ai_cats = log.get('ai_detected_categories', [])
        if ai_cats:
            # 複数カテゴリーの場合、すべてカウント
            for cat in ai_cats:
                if cat and cat != 'なし':
                    category_counts[cat] = category_counts.get(cat, 0) + 1
        else:
            # 後方互換性のため、従来のcategoryフィールドも確認
            cat = log.get('student_selected_category', log.get('category', 'なし'))
            if cat and cat != 'なし':
                category_counts[cat] = category_counts.get(cat, 0) + 1
    
    # 質問数でソート
    sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
    return sorted_categories

# デフォルトAPIの読み込み（.envで設定）
DEFAULT_API = os.getenv('DEFAULT_API', 'Claude')  # デフォルトはClaude
DEFAULT_MODEL_OPENAI = os.getenv('DEFAULT_MODEL_OPENAI', 'gpt-4o')
DEFAULT_MODEL_CLAUDE = os.getenv('DEFAULT_MODEL_CLAUDE', 'claude-sonnet-4-20250514')

# サイドバー
st.sidebar.title("⚙️ 教員用設定")

# APIプロバイダー選択（デフォルト値を.envから取得）
default_index = 0 if DEFAULT_API == "OpenAI" else (1 if DEFAULT_API == "Claude" else 2)
api_provider = st.sidebar.selectbox(
    "APIプロバイダー",
    ["OpenAI", "Claude", "Gemini"],
    index=default_index,
    help="使用するAIサービスを選択"
)

# モデル選択
if api_provider == "OpenAI":
    available_models = ["gpt-5.4", "gpt-5.4-mini", "gpt-4o"]
    default_model_index = available_models.index(DEFAULT_MODEL_OPENAI) if DEFAULT_MODEL_OPENAI in available_models else 0
    model = st.sidebar.selectbox("モデル", available_models, index=default_model_index)
elif api_provider == "Claude":
    available_models = ["claude-sonnet-4-6", "claude-opus-4-6", "claude-sonnet-4-20250514"]
    default_model_index = available_models.index(DEFAULT_MODEL_CLAUDE) if DEFAULT_MODEL_CLAUDE in available_models else 0
    model = st.sidebar.selectbox("モデル", available_models, index=default_model_index)
else:  # Gemini
    available_models = ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-flash"]
    model = st.sidebar.selectbox("モデル", available_models, index=0)

st.sidebar.markdown("---")

# デフォルトAPI設定の保存
if st.sidebar.button("📌 デフォルトAPIとして保存"):
    # .envファイルを更新
    env_path = '.env'
    env_lines = []
    
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            env_lines = f.readlines()
    
    # 既存の設定を更新または追加
    updated = {
        'DEFAULT_API': False,
        f'DEFAULT_MODEL_{api_provider.upper()}': False
    }
    
    new_lines = []
    for line in env_lines:
        if line.startswith('DEFAULT_API='):
            new_lines.append(f'DEFAULT_API={api_provider}\n')
            updated['DEFAULT_API'] = True
        elif line.startswith(f'DEFAULT_MODEL_OPENAI='):
            if api_provider == 'Gemini':
                new_lines.append(f'DEFAULT_MODEL_GEMINI=gemini-1.5-pro\n')
                updated['DEFAULT_MODEL_GEMINI'] = True
            elif api_provider == 'OpenAI':
                new_lines.append(f'DEFAULT_MODEL_OPENAI={model}\n')
                updated['DEFAULT_MODEL_OPENAI'] = True
            else:
                new_lines.append(line)
        elif line.startswith(f'DEFAULT_MODEL_CLAUDE='):
            if api_provider == 'Claude':
                new_lines.append(f'DEFAULT_MODEL_CLAUDE={model}\n')
                updated['DEFAULT_MODEL_CLAUDE'] = True
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    # 未追加の設定を追加
    if not updated['DEFAULT_API']:
        new_lines.append(f'DEFAULT_API={api_provider}\n')
    if api_provider == 'Gemini' and not updated.get('DEFAULT_MODEL_GEMINI'):
        new_lines.append('DEFAULT_MODEL_GEMINI=gemini-1.5-pro\n')
    if api_provider == 'OpenAI' and not updated.get('DEFAULT_MODEL_OPENAI'):
        new_lines.append(f'DEFAULT_MODEL_OPENAI={model}\n')
    if api_provider == 'Claude' and not updated.get('DEFAULT_MODEL_CLAUDE'):
        new_lines.append(f'DEFAULT_MODEL_CLAUDE={model}\n')
    
    with open(env_path, 'w') as f:
        f.writelines(new_lines)
    
    st.sidebar.success(f"✅ {api_provider} ({model}) をデフォルトに設定しました")

# メインコンテンツ
st.title("👨‍🏫 魔法の黒板 - 教員用インターフェース")

# タブ
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 ログ閲覧・集計", "📂 カテゴリー管理", "📚 知識ベース管理", "🎯 分析ダッシュボード", "📋 システム概要"])

# タブ1: ログ閲覧・集計
with tab1:
    st.header("学生の学習ログ")
    
    logs = load_logs()
    
    if not logs:
        st.info("まだログがありません")
    else:
        st.write(f"総ログ数: **{len(logs)}件**")
        
        # 日付フィルター
        st.subheader("🗓️ 期間指定")
        col_date1, col_date2 = st.columns(2)
        
        with col_date1:
            start_date = st.date_input(
                "開始日",
                value=None,
                help="この日以降のログを表示"
            )
        
        with col_date2:
            end_date = st.date_input(
                "終了日",
                value=None,
                help="この日以前のログを表示"
            )
        
        # フィルター
        st.subheader("🔍 フィルター")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            filter_nickname = st.multiselect(
                "ニックネームで絞り込み",
                options=list(set([log.get('nickname', '不明') for log in logs]))
            )
        with col2:
            # 学生選択カテゴリーとAI判定カテゴリーの両方から一覧を作成
            all_categories = set()
            for log in logs:
                # 学生選択カテゴリー
                student_cat = log.get('student_selected_category', log.get('category'))
                if student_cat:
                    all_categories.add(student_cat)
                # AI判定カテゴリー
                ai_cats = log.get('ai_detected_categories', [])
                all_categories.update(ai_cats)
            
            filter_category = st.multiselect(
                "カテゴリーで絞り込み",
                options=sorted(list(all_categories))
            )
        with col3:
            filter_mode = st.multiselect(
                "モードで絞り込み",
                options=list(set([log.get('mode', '不明') for log in logs]))
            )
        with col4:
            filter_blocked = st.checkbox("ブロックされた質問のみ表示")
            filter_mismatch = st.checkbox("カテゴリー不一致のみ表示")
        
        # フィルタリング
        filtered_logs = logs
        
        # 日付フィルター適用
        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            filtered_logs = [
                log for log in filtered_logs 
                if datetime.fromisoformat(log.get('timestamp', '1970-01-01T00:00:00')) >= start_datetime
            ]
        
        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())
            filtered_logs = [
                log for log in filtered_logs 
                if datetime.fromisoformat(log.get('timestamp', '9999-12-31T23:59:59')) <= end_datetime
            ]
        
        # その他のフィルター
        if filter_nickname:
            filtered_logs = [log for log in filtered_logs if log.get('nickname') in filter_nickname]
        if filter_category:
            filtered_logs = [
                log for log in filtered_logs 
                if (log.get('student_selected_category', log.get('category')) in filter_category or 
                    any(cat in filter_category for cat in log.get('ai_detected_categories', [])))
            ]
        if filter_mode:
            filtered_logs = [log for log in filtered_logs if log.get('mode') in filter_mode]
        if filter_blocked:
            filtered_logs = [log for log in filtered_logs if log.get('is_blocked', False)]
        if filter_mismatch:
            filtered_logs = [log for log in filtered_logs if log.get('category_mismatch', False)]
        
        st.write(f"絞り込み後: **{len(filtered_logs)}件**")
        
        # ダウンロードセクション
        st.markdown("---")
        st.subheader("📥 ログのダウンロード")
        
        col_dl1, col_dl2 = st.columns(2)
        
        # DataFrameの作成
        df_logs = logs_to_dataframe(filtered_logs)
        
        with col_dl1:
            # CSV形式でダウンロード（BOM付きUTF-8でExcelでも文字化けしない）
            if not df_logs.empty:
                # BOM付きUTF-8でエンコード
                csv = '\ufeff' + df_logs.to_csv(index=False, encoding='utf-8')
                st.download_button(
                    label="📄 CSVファイルをダウンロード",
                    data=csv.encode('utf-8'),
                    file_name=f"学習ログ_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        with col_dl2:
            # Excel形式でダウンロード
            if not df_logs.empty:
                excel_file = create_excel(df_logs)
                st.download_button(
                    label="📊 Excelファイルをダウンロード",
                    data=excel_file,
                    file_name=f"学習ログ_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        
        st.markdown("---")
        
        # カテゴリー別集計
        if filter_category or not filter_nickname:
            st.subheader("📈 カテゴリー別集計")
            category_counts = {}
            for log in filtered_logs:
                cat = log.get('category', 'なし')
                category_counts[cat] = category_counts.get(cat, 0) + 1
            
            if category_counts:
                df_cat = pd.DataFrame(list(category_counts.items()), columns=['カテゴリー', '質問数'])
                df_cat = df_cat.sort_values('質問数', ascending=False)
                st.bar_chart(df_cat.set_index('カテゴリー'))
                st.dataframe(df_cat, use_container_width=True)
        
        # 学生別集計
        if filter_nickname or len(filter_nickname) == 0:
            st.subheader("👥 学生別集計")
            student_counts = {}
            for log in filtered_logs:
                nick = log.get('nickname', '不明')
                student_counts[nick] = student_counts.get(nick, 0) + 1
            
            if student_counts:
                df_student = pd.DataFrame(list(student_counts.items()), columns=['ニックネーム', '質問数'])
                df_student = df_student.sort_values('質問数', ascending=False)
                st.dataframe(df_student, use_container_width=True)
        
        # 詳細ログ表示
        st.subheader("📋 詳細ログ")
        for i, log in enumerate(filtered_logs[:50]):  # 最新50件
            with st.expander(f"{log.get('datetime', 'N/A')} - {log.get('nickname', '不明')} - {log.get('mode', 'N/A')}"):
                st.write(f"**カテゴリー**: {log.get('category', 'なし')}")
                st.write(f"**API**: {log.get('api_provider', 'N/A')} / {log.get('model', 'N/A')}")
                if log.get('difficulty'):
                    st.write(f"**難易度**: {log.get('difficulty')} / **問題数**: {log.get('num_problems')}")
                st.write(f"**質問**: {log.get('question', 'N/A')}")
                st.write(f"**回答**:")
                st.text_area("", value=log.get('answer', 'N/A'), height=200, key=f"answer_{i}", disabled=True)

# タブ2: カテゴリー管理
with tab2:
    st.header("カテゴリー管理")
    
    categories = load_categories()
    
    st.subheader("現在のカテゴリー")
    st.write(categories)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📝 カテゴリーを追加")
        new_category = st.text_input("新しいカテゴリー名")
        if st.button("追加"):
            if new_category and new_category not in categories:
                categories.append(new_category)
                save_categories(categories)
                st.success(f"✅ 「{new_category}」を追加しました")
                st.rerun()
            elif new_category in categories:
                st.warning("⚠️ すでに存在するカテゴリーです")
            else:
                st.warning("⚠️ カテゴリー名を入力してください")
    
    with col2:
        st.subheader("🗑️ カテゴリーを削除")
        delete_category = st.selectbox("削除するカテゴリー", categories)
        if st.button("削除"):
            if delete_category in categories:
                categories.remove(delete_category)
                save_categories(categories)
                st.success(f"✅ 「{delete_category}」を削除しました")
                st.rerun()

# タブ3: 知識ベース管理
with tab3:
    st.header("知識ベース管理")
    
    st.info("""
    **📌 練習問題生成のルール**
    
    練習問題を生成する際は、以下のルールに従います:
    - ✅ すべての選択肢が問題文のテーマに直接関連している
    - ❌ 計算が正しくても、問題の主旨と無関係な選択肢は作成しない
    
    **例:**
    - 問題: 「NNTの解釈として正しいのは?」
    - NG選択肢: 「RRRは約67%である」(計算は正しいがNNTとは無関係)
    - OK選択肢: 「NNTは5である」「10人治療すれば1人の血栓症を予防できる」
    """)
    
    knowledge_base = load_knowledge_base()
    
    st.write(f"現在の知識項目数: **{len(knowledge_base)}件**")
    
    # 検索・絞り込み
    st.subheader("🔍 検索・絞り込み")
    search_query = st.text_input("キーワードで検索", placeholder="例: p値, EBM, 統計")
    
    # 検索処理
    if search_query:
        filtered_kb = [
            item for item in knowledge_base
            if search_query.lower() in item.get('question', '').lower() or
               search_query.lower() in item.get('answer', '').lower() or
               any(search_query.lower() in kw.lower() for kw in item.get('keywords', []))
        ]
        st.write(f"検索結果: **{len(filtered_kb)}件**")
    else:
        filtered_kb = knowledge_base
    
    # 新規追加
    st.subheader("➕ 新しい知識を追加")
    
    with st.form("add_knowledge"):
        question = st.text_area("質問", height=100)
        answer = st.text_area("回答", height=200)
        keywords = st.text_input("キーワード（カンマ区切り）", placeholder="例: p値,統計,検定")
        
        submitted = st.form_submit_button("追加")
        if submitted:
            if question and answer and keywords:
                new_item = {
                    "question": question,
                    "answer": answer,
                    "keywords": [k.strip() for k in keywords.split(',')]
                }
                knowledge_base.append(new_item)
                save_knowledge_base(knowledge_base)
                st.success("✅ 知識を追加しました")
                st.rerun()
            else:
                st.warning("⚠️ すべての項目を入力してください")
    
    # 既存の知識表示・編集
    st.subheader("📚 既存の知識")
    
    if filtered_kb:
        for i, item in enumerate(filtered_kb):
            # オリジナルのインデックスを取得
            original_index = knowledge_base.index(item)
            
            with st.expander(f"Q: {item.get('question', 'N/A')[:50]}..."):
                # 編集モード切り替え
                edit_mode = st.checkbox(f"編集モード", key=f"edit_mode_{original_index}")
                
                if edit_mode:
                    # 編集フォーム
                    with st.form(f"edit_form_{original_index}"):
                        edited_question = st.text_area("質問", value=item.get('question', ''), height=100, key=f"q_{original_index}")
                        edited_answer = st.text_area("回答", value=item.get('answer', ''), height=200, key=f"a_{original_index}")
                        edited_keywords = st.text_input(
                            "キーワード（カンマ区切り）",
                            value=', '.join(item.get('keywords', [])),
                            key=f"k_{original_index}"
                        )
                        
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            save_button = st.form_submit_button("💾 保存")
                        with col_btn2:
                            cancel_button = st.form_submit_button("❌ キャンセル")
                        
                        if save_button:
                            knowledge_base[original_index] = {
                                "question": edited_question,
                                "answer": edited_answer,
                                "keywords": [k.strip() for k in edited_keywords.split(',')]
                            }
                            save_knowledge_base(knowledge_base)
                            st.success("✅ 保存しました")
                            st.rerun()
                else:
                    # 表示モード
                    st.write(f"**質問**: {item.get('question', 'N/A')}")
                    st.write(f"**回答**: {item.get('answer', 'N/A')}")
                    st.write(f"**キーワード**: {', '.join(item.get('keywords', []))}")
                
                # 削除ボタン（編集モード外）
                if not edit_mode:
                    if st.button(f"🗑️ 削除", key=f"delete_{original_index}"):
                        knowledge_base.pop(original_index)
                        save_knowledge_base(knowledge_base)
                        st.success("✅ 削除しました")
                        st.rerun()
    else:
        st.info("該当する知識がありません")

# タブ4: 分析ダッシュボード
with tab4:
    st.header("🎯 分析ダッシュボード")
    
    logs = load_logs()
    
    if not logs:
        st.info("まだログがありません")
    else:
        # 基本統計
        st.subheader("📊 基本統計")
        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
        
        with col_stat1:
            st.metric("総ログ数", f"{len(logs)}件")
        
        with col_stat2:
            unique_students = len(set([log.get('nickname', '不明') for log in logs]))
            st.metric("利用学生数", f"{unique_students}名")
        
        with col_stat3:
            blocked_count = len([log for log in logs if log.get('is_blocked', False)])
            st.metric("ブロックされた質問", f"{blocked_count}件", 
                     delta=f"{blocked_count/len(logs)*100:.1f}%" if len(logs) > 0 else "0%")
        
        with col_stat4:
            mismatch_count = len([log for log in logs if log.get('category_mismatch', False)])
            st.metric("カテゴリー不一致", f"{mismatch_count}件",
                     delta=f"{mismatch_count/len(logs)*100:.1f}%" if len(logs) > 0 else "0%")
        
        st.markdown("---")
        
        # NGワード検出分析
        if blocked_count > 0:
            st.subheader("🚫 ブロックされた質問の分析")
            blocked_logs = [log for log in logs if log.get('is_blocked', False)]
            
            # ブロック理由の集計
            block_reasons = Counter([log.get('block_reason', '不明') for log in blocked_logs])
            
            reason_labels = {
                'strict': '個人情報・危険',
                'sexual': '性的コンテンツ',
                'off_topic': '授業外トピック'
            }
            
            block_df = pd.DataFrame([
                (reason_labels.get(reason, reason), count) 
                for reason, count in block_reasons.items()
            ], columns=['理由', '件数'])
            
            col_block1, col_block2 = st.columns([2, 1])
            
            with col_block1:
                st.dataframe(block_df, use_container_width=True)
            
            with col_block2:
                st.bar_chart(block_df.set_index('理由'))
            
            # 最近のブロック事例（質問内容は表示しない）
            with st.expander("最近のブロック事例（最新5件）"):
                for log in blocked_logs[:5]:
                    st.warning(f"""
                    - **日時**: {log.get('datetime', '不明')}
                    - **ニックネーム**: {log.get('nickname', '不明')}
                    - **理由**: {reason_labels.get(log.get('block_reason', ''), '不明')}
                    """)
            
            st.markdown("---")
        
        # カテゴリー不一致分析
        if mismatch_count > 0:
            st.subheader("⚠️ カテゴリー選択ミス分析")
            st.write("学生が選択したカテゴリーとAIが判定したカテゴリーが異なる質問")
            
            mismatch_logs = [log for log in logs if log.get('category_mismatch', False)]
            
            # 不一致事例をテーブル表示
            mismatch_data = []
            for log in mismatch_logs[:10]:  # 最新10件
                mismatch_data.append({
                    '日時': log.get('datetime', '不明')[:16],  # 分まで表示
                    '学生選択': log.get('student_selected_category', '不明'),
                    'AI判定': ', '.join(log.get('ai_detected_categories', [])),
                    '質問（抜粋）': log.get('question', '')[:30] + '...'
                })
            
            mismatch_df = pd.DataFrame(mismatch_data)
            st.dataframe(mismatch_df, use_container_width=True)
            
            st.info("💡 カテゴリー不一致が多い場合、カテゴリー名の見直しや学生への説明が必要かもしれません")
            
            st.markdown("---")
        
        # 複数カテゴリーにまたがる質問の分析
        st.subheader("🔀 複数カテゴリーにまたがる質問")
        multi_category_logs = [
            log for log in logs 
            if len(log.get('ai_detected_categories', [])) >= 2
        ]
        
        if multi_category_logs:
            st.write(f"複数カテゴリーに該当する質問: **{len(multi_category_logs)}件** ({len(multi_category_logs)/len(logs)*100:.1f}%)")
            
            # カテゴリーの組み合わせを分析
            category_combinations = Counter([
                tuple(sorted(log.get('ai_detected_categories', [])))
                for log in multi_category_logs
            ])
            
            combo_df = pd.DataFrame([
                (' + '.join(combo), count)
                for combo, count in category_combinations.most_common(5)
            ], columns=['カテゴリー組み合わせ', '件数'])
            
            st.dataframe(combo_df, use_container_width=True)
            st.info("💡 特定のカテゴリー組み合わせが多い場合、統合カテゴリーの追加を検討できます")
        else:
            st.info("複数カテゴリーにまたがる質問はまだありません")
        
        st.markdown("---")
        
        # FAQ分析
        st.subheader("❓ よく聞かれる質問（FAQ）")
        # ブロックされていない質問応答のみを対象
        qa_logs = [log for log in logs if log.get('mode') == '質問応答' and not log.get('is_blocked', False)]
        faq_data = analyze_faq(qa_logs, top_n=10)
        
        if faq_data:
            faq_df = pd.DataFrame(faq_data, columns=['質問', '回数'])
            st.dataframe(faq_df, use_container_width=True)
            
            # グラフ表示
            st.bar_chart(faq_df.set_index('質問'))
        else:
            st.info("質問応答のログがまだありません")
        
        st.markdown("---")
        
        # つまずきポイント分析
        st.subheader("⚠️ つまずきポイント分析")
        st.write("質問が多く集中しているカテゴリーは、学生がつまずきやすいポイントです")
        st.info("💡 AI判定カテゴリーを基準に分析しています（複数カテゴリーの場合はすべてカウント）")
        
        stumbling_points = analyze_stumbling_points(logs)
        
        if stumbling_points:
            sp_df = pd.DataFrame(stumbling_points, columns=['カテゴリー', '質問数'])
            
            # 色分け（質問数が多いほど濃い色）
            st.dataframe(
                sp_df.style.background_gradient(subset=['質問数'], cmap='YlOrRd'),
                use_container_width=True
            )
            
            # 上位3つを強調表示
            st.write("### 特に注意が必要なカテゴリー（Top 3）")
            for i, (category, count) in enumerate(stumbling_points[:3], 1):
                st.warning(f"**{i}位**: {category} - {count}件の質問")
        else:
            st.info("カテゴリー付きのログがまだありません")

# タブ5: システム概要
with tab5:
    st.header("📋 魔法の黒板 - システム概要")
    
    # 知識ベース情報
    knowledge_base = load_knowledge_base()
    categories = load_categories()
    
    st.markdown("---")
    
    # 3カラムレイアウト
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="📚 知識ベース項目数",
            value=f"{len(knowledge_base)}項目",
            help="教員が作成したオリジナル講義資料に基づくQ&A"
        )
    
    with col2:
        st.metric(
            label="📂 対応カテゴリー数",
            value=f"{len(categories)}種類",
            help="医薬品情報学の主要分野をカバー"
        )
    
    with col3:
        st.metric(
            label="📖 カバー範囲",
            value="全8セッション",
            help="医薬品情報学の講義全体をカバー"
        )
    
    st.markdown("---")
    
    # システムの主要機能
    st.subheader("🎯 主要機能")
    
    col_func1, col_func2 = st.columns(2)
    
    with col_func1:
        st.markdown("""
        **学生向け機能**
        - ✅ 24時間質問応答システム
        - ✅ カテゴリー別質問対応
        - ✅ 練習問題自動生成(5択2正解形式)
          - すべての選択肢が問題のテーマに直接関連
          - 無関係な指標や概念を選択肢に含めない
        - ✅ 難易度選択機能
        """)
    
    with col_func2:
        st.markdown("""
        **教員向け機能**
        - ✅ 学習履歴の詳細記録
        - ✅ つまずきポイント可視化
        - ✅ FAQ自動抽出
        - ✅ CSV/Excel形式でデータ出力
        """)
    
    st.markdown("---")
    
    # 技術仕様
    st.subheader("⚙️ 技術仕様")
    
    tech_col1, tech_col2 = st.columns(2)
    
    with tech_col1:
        st.markdown("""
        **AI技術**
        - 🤖 OpenAI GPT-4o / GPT-4o-mini
        - 🤖 Anthropic Claude Sonnet 4 / Opus 4
        - 🤖 Google Gemini 1.5 Pro
        - 🔍 RAG (Retrieval-Augmented Generation)
        """)
    
    with tech_col2:
        st.markdown("""
        **データ基盤**
        - 📝 オリジナル講義資料ベース
        - ⚖️ 著作権完全クリア
        - 🔒 学習ログの安全な管理
        """)
    
    st.markdown("---")
    
    # カテゴリー一覧
    st.subheader("📂 対応カテゴリー一覧")
    
    # カテゴリーを2列で表示
    cat_col1, cat_col2 = st.columns(2)
    mid_point = (len(categories) + 1) // 2
    
    with cat_col1:
        for i, cat in enumerate(categories[:mid_point], 1):
            st.write(f"{i}. {cat}")
    
    with cat_col2:
        for i, cat in enumerate(categories[mid_point:], mid_point + 1):
            st.write(f"{i}. {cat}")
    
    st.markdown("---")
    
    # 研究計画
    st.subheader("🔬 研究計画")
    
    research_col1, research_col2 = st.columns(2)
    
    with research_col1:
        st.markdown("""
        **実証実験スケジュール**
        - 📅 プレ実験：2026年9月
          - 対象：約30名
          - 目的：システム動作検証
        
        - 📅 本実験：2026年10-12月
          - 対象：約200名（薬学部3年生全体）
          - 目的：教育効果の検証
        """)
    
    with research_col2:
        st.markdown("""
        **評価方法**
        - 📊 学習ログ分析
        - 📝 アンケート調査
        - 📈 試験成績との相関分析
        - 🎯 10年分の試験データによる客観評価
        
        **期待される効果**
        - 学習効率の向上
        - つまずきポイントの早期発見
        - 個別最適化学習の実現
        """)
    
    st.markdown("---")
    
    # システムの特徴・独創性
    st.subheader("💡 システムの特徴・独創性")
    
    st.info("""
    **薬学教育特化型AIシステム**
    
    本システムは、既存の汎用AIチャットボットとは異なり、薬学部「医薬品情報学」に特化した専門的な学習支援を実現します。
    
    - **オリジナル教材ベース**: 教員が作成した137項目のQ&A知識ベースにより、講義内容に完全に沿った回答を提供
    - **著作権クリア**: 教科書ではなく自作教材を使用することで、法的リスクを完全に排除
    - **つまずき可視化**: 学生の質問パターンを分析し、理解困難点を教員にフィードバック
    - **実証研究**: 10年分の試験データを用いた客観的な教育効果の検証
    """)
    
    st.markdown("---")
    
    # 現在の設定情報
    st.subheader("🔧 現在の設定")
    
    info_text = f"""
    - **デフォルトAPI**: {api_provider}
    - **使用モデル**: {model}
    - **知識ベース**: {len(knowledge_base)}項目
    - **カテゴリー**: {len(categories)}種類
    """
    
    st.code(info_text, language="text")

# フッター
st.sidebar.markdown("---")
st.sidebar.info(f"""
📌 現在の設定:
- API: {api_provider}
- モデル: {model}
""")
