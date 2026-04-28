import streamlit as st
import os
from dotenv import load_dotenv
from openai import OpenAI
import google.generativeai as genai
from anthropic import Anthropic
import json
import hashlib
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
from collections import Counter
from supabase import create_client, Client

# 環境変数の読み込み
load_dotenv()

# ページ設定
st.set_page_config(
    page_title="魔法の黒板 - 教員用",
    page_icon="👨‍🏫",
    layout="wide"
)

# Supabaseクライアント初期化
@st.cache_resource
def init_supabase() -> Client:
    url = os.getenv('SUPABASE_URL') or st.secrets.get('SUPABASE_URL', '')
    key = os.getenv('SUPABASE_KEY') or st.secrets.get('SUPABASE_KEY', '')
    return create_client(url, key)

supabase = init_supabase()

# APIクライアントの初期化
@st.cache_resource
def initialize_clients():
    openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY') or st.secrets.get('OPENAI_API_KEY', ''))
    gemini_api_key = os.getenv('GEMINI_API_KEY') or st.secrets.get('GEMINI_API_KEY', '')
    if gemini_api_key:
        genai.configure(api_key=gemini_api_key)
    anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY') or st.secrets.get('ANTHROPIC_API_KEY', ''))
    return openai_client, anthropic_client

openai_client, anthropic_client = initialize_clients()

# カテゴリーの読み込み・保存
def load_categories():
    try:
        with open('categories.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        default_categories = [
            "情報", "情報源", "情報の収集・評価・加工・提供・管理",
            "EBM", "生物統計", "研究デザインと解析",
            "医薬品の採用・比較・評価", "患者情報とその収集・評価・管理", "その他"
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

# ログ読み込み（Supabase対応）
def load_logs():
    try:
        result = supabase.table('logs').select('*').order('timestamp', desc=True).execute()
        logs = []
        for row in result.data:
            if isinstance(row.get('ai_detected_categories'), str):
                try:
                    row['ai_detected_categories'] = json.loads(row['ai_detected_categories'])
                except:
                    row['ai_detected_categories'] = []
            logs.append(row)
        return logs
    except Exception as e:
        print(f"ログ読み込みエラー: {e}")
        return []

# ログをDataFrameに変換
def logs_to_dataframe(logs):
    if not logs:
        return pd.DataFrame()
    data = []
    for log in logs:
        row = {
            '日時': log.get('datetime', ''),
            'タイムスタンプ': log.get('timestamp', ''),
            'ニックネーム': log.get('nickname', '不明'),
            'モード': log.get('mode', ''),
            '学生選択カテゴリー': log.get('student_selected_category', 'なし'),
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
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='学習ログ')
        worksheet = writer.sheets['学習ログ']
        for idx, col in enumerate(df.columns):
            max_length = max(df[col].astype(str).apply(len).max(), len(col))
            adjusted_width = min(max_length * 1.2 + 2, 50)
            worksheet.column_dimensions[chr(65 + idx)].width = adjusted_width
    output.seek(0)
    return output

# FAQ分析
def analyze_faq(logs, top_n=10):
    questions = [log.get('question', '') for log in logs if log.get('mode') == '質問応答']
    question_counts = Counter(questions)
    filtered_counts = {q: c for q, c in question_counts.items() if q.strip()}
    return Counter(filtered_counts).most_common(top_n)

# つまずきポイント分析
def analyze_stumbling_points(logs):
    category_counts = {}
    for log in logs:
        ai_cats = log.get('ai_detected_categories', [])
        if ai_cats:
            for cat in ai_cats:
                if cat and cat != 'なし':
                    category_counts[cat] = category_counts.get(cat, 0) + 1
        else:
            cat = log.get('student_selected_category', 'なし')
            if cat and cat != 'なし':
                category_counts[cat] = category_counts.get(cat, 0) + 1
    return sorted(category_counts.items(), key=lambda x: x[1], reverse=True)

# デフォルトAPI
DEFAULT_API = os.getenv('DEFAULT_API') or st.secrets.get('DEFAULT_API', 'Claude')
DEFAULT_MODEL_OPENAI = os.getenv('DEFAULT_MODEL_OPENAI') or st.secrets.get('DEFAULT_MODEL_OPENAI', 'gpt-4o')
DEFAULT_MODEL_CLAUDE = os.getenv('DEFAULT_MODEL_CLAUDE') or st.secrets.get('DEFAULT_MODEL_CLAUDE', 'claude-sonnet-4-20250514')

# サイドバー
st.sidebar.title("⚙️ 教員用設定")
default_index = 0 if DEFAULT_API == "OpenAI" else (1 if DEFAULT_API == "Claude" else 2)
api_provider = st.sidebar.selectbox("APIプロバイダー", ["OpenAI", "Claude", "Gemini"], index=default_index)

if api_provider == "OpenAI":
    available_models = ["gpt-4o", "gpt-4o-mini"]
    model = st.sidebar.selectbox("モデル", available_models)
elif api_provider == "Claude":
    available_models = ["claude-sonnet-4-20250514", "claude-opus-4-6"]
    default_model_index = available_models.index(DEFAULT_MODEL_CLAUDE) if DEFAULT_MODEL_CLAUDE in available_models else 0
    model = st.sidebar.selectbox("モデル", available_models, index=default_model_index)
else:
    available_models = ["gemini-1.5-pro", "gemini-1.5-flash"]
    model = st.sidebar.selectbox("モデル", available_models)

st.sidebar.markdown("---")

# ===== 教員認証 =====
TEACHERS_FILE = "teachers.json"

def load_teachers():
    try:
        with open(TEACHERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def hash_teacher_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def login_teacher(teacher_id, password):
    teachers = load_teachers()
    if teacher_id not in teachers:
        return False, "IDが見つかりません"
    if teachers[teacher_id]["password_hash"] != hash_teacher_password(password):
        return False, "パスワードが正しくありません"
    return True, teachers[teacher_id]

def add_teacher(teacher_id, name, password, role="teacher"):
    teachers = load_teachers()
    if teacher_id in teachers:
        return False, "このIDはすでに登録されています"
    teachers[teacher_id] = {
        "name": name,
        "role": role,
        "password_hash": hash_teacher_password(password),
        "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(TEACHERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(teachers, f, ensure_ascii=False, indent=2)
    return True, "登録完了"

def delete_teacher(teacher_id):
    teachers = load_teachers()
    if teacher_id not in teachers:
        return False, "IDが見つかりません"
    del teachers[teacher_id]
    with open(TEACHERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(teachers, f, ensure_ascii=False, indent=2)
    return True, "削除完了"

def change_password(teacher_id, old_password, new_password):
    teachers = load_teachers()
    if teachers[teacher_id]["password_hash"] != hash_teacher_password(old_password):
        return False, "現在のパスワードが正しくありません"
    teachers[teacher_id]["password_hash"] = hash_teacher_password(new_password)
    with open(TEACHERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(teachers, f, ensure_ascii=False, indent=2)
    return True, "パスワードを変更しました"

# ===== 認証UI =====
if "teacher_authenticated" not in st.session_state:
    st.session_state.teacher_authenticated = False
if "teacher_info" not in st.session_state:
    st.session_state.teacher_info = {}

# クエリパラメータでリロード後もログイン状態を維持
params = st.query_params
if not st.session_state.teacher_authenticated and params.get("auth") == "ok":
    st.session_state.teacher_authenticated = True
    st.session_state.teacher_info = {
        "name": params.get("name", "教員"),
        "role": params.get("role", "teacher")
    }
    st.session_state.teacher_id = params.get("tid", "")

if not st.session_state.teacher_authenticated:
    st.markdown("""
    <div style='text-align: center; padding: 2rem 0;'>
        <h1 style='font-size: 2.5rem;'>👨‍🏫 魔法の黒板 - 教員用</h1>
        <p style='font-size: 1.2rem; color: #666;'>教員IDとパスワードでログインしてください</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form(key="teacher_login_form"):
        t_id = st.text_input("教員ID", placeholder="例：admin")
        t_pw = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン", type="primary", use_container_width=True)

    if submitted:
        if t_id and t_pw:
            ok, result = login_teacher(t_id, t_pw)
            if ok:
                st.session_state.teacher_authenticated = True
                st.session_state.teacher_info = result
                st.session_state.teacher_id = t_id
                st.query_params["auth"] = "ok"
                st.query_params["name"] = result.get("name", "教員")
                st.query_params["role"] = result.get("role", "teacher")
                st.query_params["tid"] = t_id
                st.rerun()
            else:
                st.error(f"❌ {result}")
        else:
            st.warning("IDとパスワードを入力してください")
    st.stop()

# ログイン済み
teacher_info = st.session_state.teacher_info
teacher_id = st.session_state.get("teacher_id", "")

with st.sidebar:
    st.write(f"👤 **{teacher_info.get('name', '')}** さん")
    st.write(f"🔑 役割: {'管理者' if teacher_info.get('role') == 'admin' else '教員'}")
    if st.button("ログアウト", use_container_width=True, key="teacher_logout"):
        st.session_state.teacher_authenticated = False
        st.session_state.teacher_info = {}
        st.query_params.clear()
        st.rerun()

    st.markdown("---")

    with st.expander("🔒 パスワード変更"):
        with st.form(key="change_pw_form"):
            old_pw = st.text_input("現在のパスワード", type="password")
            new_pw = st.text_input("新しいパスワード（6文字以上）", type="password")
            new_pw2 = st.text_input("新しいパスワード（確認）", type="password")
            if st.form_submit_button("変更する"):
                if len(new_pw) < 6:
                    st.error("6文字以上で設定してください")
                elif new_pw != new_pw2:
                    st.error("パスワードが一致しません")
                else:
                    ok, msg = change_password(teacher_id, old_pw, new_pw)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)

    if teacher_info.get("role") == "admin":
        with st.expander("👥 教員管理"):
            st.markdown("**新しい教員を追加**")
            with st.form(key="add_teacher_form"):
                new_id = st.text_input("教員ID")
                new_name = st.text_input("氏名")
                new_pw_add = st.text_input("初期パスワード", type="password")
                new_role = st.selectbox("役割", ["teacher", "admin"])
                if st.form_submit_button("追加する"):
                    if new_id and new_name and new_pw_add:
                        ok, msg = add_teacher(new_id, new_name, new_pw_add, new_role)
                        if ok:
                            st.success(f"✅ {new_name}さんを追加しました")
                        else:
                            st.error(f"❌ {msg}")
                    else:
                        st.warning("すべて入力してください")

            st.markdown("**教員一覧・削除**")
            teachers = load_teachers()
            for tid, tinfo in teachers.items():
                col1, col2 = st.columns([3, 1])
                col1.write(f"{tinfo['name']} ({tid})")
                if tid != teacher_id:
                    if col2.button("削除", key=f"del_{tid}"):
                        ok, msg = delete_teacher(tid)
                        if ok:
                            st.success("削除しました")
                            st.rerun()

st.title("👨‍🏫 魔法の黒板 - 教員用インターフェース")
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 ログ閲覧・集計", "📂 カテゴリー管理", "📚 知識ベース管理", "🎯 分析ダッシュボード", "📋 システム概要", "👥 学生管理"])

# タブ1: ログ閲覧・集計
with tab1:
    st.header("学生の学習ログ")
    logs = load_logs()

    if not logs:
        st.info("まだログがありません")
    else:
        st.write(f"総ログ数: **{len(logs)}件**")

        st.subheader("🗓️ 期間指定")
        col_date1, col_date2 = st.columns(2)
        with col_date1:
            start_date = st.date_input("開始日", value=None)
        with col_date2:
            end_date = st.date_input("終了日", value=None)

        st.subheader("🔍 フィルター")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            filter_nickname = st.multiselect("ニックネームで絞り込み", options=list(set([log.get('nickname', '不明') for log in logs])))
        with col2:
            all_categories = set()
            for log in logs:
                cat = log.get('student_selected_category')
                if cat:
                    all_categories.add(cat)
                for c in log.get('ai_detected_categories', []):
                    all_categories.add(c)
            filter_category = st.multiselect("カテゴリーで絞り込み", options=sorted(list(all_categories)))
        with col3:
            filter_mode = st.multiselect("モードで絞り込み", options=list(set([log.get('mode', '不明') for log in logs])))
        with col4:
            filter_blocked = st.checkbox("ブロックされた質問のみ表示")
            filter_mismatch = st.checkbox("カテゴリー不一致のみ表示")

        filtered_logs = logs
        if start_date:
            start_str = start_date.strftime("%Y%m%d")
            filtered_logs = [log for log in filtered_logs if log.get('timestamp', '') >= start_str]
        if end_date:
            end_str = end_date.strftime("%Y%m%d") + "999999"
            filtered_logs = [log for log in filtered_logs if log.get('timestamp', '') <= end_str]
        if filter_nickname:
            filtered_logs = [log for log in filtered_logs if log.get('nickname') in filter_nickname]
        if filter_category:
            filtered_logs = [
                log for log in filtered_logs
                if (log.get('student_selected_category') in filter_category or
                    any(cat in filter_category for cat in log.get('ai_detected_categories', [])))
            ]
        if filter_mode:
            filtered_logs = [log for log in filtered_logs if log.get('mode') in filter_mode]
        if filter_blocked:
            filtered_logs = [log for log in filtered_logs if log.get('is_blocked', False)]
        if filter_mismatch:
            filtered_logs = [log for log in filtered_logs if log.get('category_mismatch', False)]

        st.write(f"絞り込み後: **{len(filtered_logs)}件**")

        st.markdown("---")
        st.subheader("📥 ログのダウンロード")
        col_dl1, col_dl2 = st.columns(2)
        df_logs = logs_to_dataframe(filtered_logs)

        with col_dl1:
            if not df_logs.empty:
                csv = '\ufeff' + df_logs.to_csv(index=False, encoding='utf-8')
                st.download_button(
                    label="📄 CSVファイルをダウンロード",
                    data=csv.encode('utf-8'),
                    file_name=f"学習ログ_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        with col_dl2:
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
        st.subheader("📈 カテゴリー別集計")
        category_counts = {}
        for log in filtered_logs:
            cat = log.get('student_selected_category', 'なし')
            category_counts[cat] = category_counts.get(cat, 0) + 1
        if category_counts:
            df_cat = pd.DataFrame(list(category_counts.items()), columns=['カテゴリー', '質問数'])
            df_cat = df_cat.sort_values('質問数', ascending=False)
            st.bar_chart(df_cat.set_index('カテゴリー'))
            st.dataframe(df_cat, use_container_width=True)

        st.subheader("👥 学生別集計")
        student_counts = {}
        for log in filtered_logs:
            nick = log.get('nickname', '不明')
            student_counts[nick] = student_counts.get(nick, 0) + 1
        if student_counts:
            df_student = pd.DataFrame(list(student_counts.items()), columns=['ニックネーム', '質問数'])
            df_student = df_student.sort_values('質問数', ascending=False)
            st.dataframe(df_student, use_container_width=True)

        st.subheader("📋 詳細ログ")
        for i, log in enumerate(filtered_logs[:50]):
            with st.expander(f"{log.get('datetime', 'N/A')} - {log.get('nickname', '不明')} - {log.get('mode', 'N/A')}"):
                st.write(f"**カテゴリー**: {log.get('student_selected_category', 'なし')}")
                st.write(f"**API**: {log.get('api_provider', 'N/A')} / {log.get('model', 'N/A')}")
                if log.get('difficulty'):
                    st.write(f"**難易度**: {log.get('difficulty')} / **問題数**: {log.get('num_problems')}")
                st.write(f"**質問**: {log.get('question', 'N/A')}")
                st.write("**回答**:")
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
    knowledge_base = load_knowledge_base()
    st.write(f"現在の知識項目数: **{len(knowledge_base)}件**")

    st.subheader("🔍 検索")
    search_query = st.text_input("キーワードで検索", placeholder="例: p値, EBM, 統計")
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

    st.subheader("➕ 新しい知識を追加")
    with st.form("add_knowledge"):
        question = st.text_area("質問", height=100)
        answer = st.text_area("回答", height=200)
        keywords = st.text_input("キーワード（カンマ区切り）")
        if st.form_submit_button("追加"):
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

    st.subheader("📚 既存の知識")
    for i, item in enumerate(filtered_kb):
        original_index = knowledge_base.index(item)
        with st.expander(f"Q: {item.get('question', 'N/A')[:50]}..."):
            edit_mode = st.checkbox("編集モード", key=f"edit_mode_{original_index}")
            if edit_mode:
                with st.form(f"edit_form_{original_index}"):
                    edited_question = st.text_area("質問", value=item.get('question', ''), height=100)
                    edited_answer = st.text_area("回答", value=item.get('answer', ''), height=200)
                    edited_keywords = st.text_input("キーワード", value=', '.join(item.get('keywords', [])))
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        save_button = st.form_submit_button("💾 保存")
                    with col_btn2:
                        delete_button = st.form_submit_button("🗑️ 削除")
                    if save_button:
                        knowledge_base[original_index] = {
                            "question": edited_question,
                            "answer": edited_answer,
                            "keywords": [k.strip() for k in edited_keywords.split(',')]
                        }
                        save_knowledge_base(knowledge_base)
                        st.success("✅ 保存しました")
                        st.rerun()
                    if delete_button:
                        knowledge_base.pop(original_index)
                        save_knowledge_base(knowledge_base)
                        st.success("✅ 削除しました")
                        st.rerun()
            else:
                st.write(f"**Q**: {item.get('question', '')}")
                st.write(f"**A**: {item.get('answer', '')}")
                st.write(f"**キーワード**: {', '.join(item.get('keywords', []))}")

# タブ4: 分析ダッシュボード
with tab4:
    st.header("🎯 分析ダッシュボード")
    logs = load_logs()

    if not logs:
        st.info("まだログがありません")
    else:
        mismatch_count = sum(1 for log in logs if log.get('category_mismatch', False))
        if mismatch_count > 0:
            st.subheader("⚠️ カテゴリー選択ミス分析")
            mismatch_logs = [log for log in logs if log.get('category_mismatch', False)]
            mismatch_data = []
            for log in mismatch_logs[:10]:
                mismatch_data.append({
                    '日時': log.get('datetime', '不明')[:16],
                    '学生選択': log.get('student_selected_category', '不明'),
                    'AI判定': ', '.join(log.get('ai_detected_categories', [])),
                    '質問（抜粋）': log.get('question', '')[:30] + '...'
                })
            st.dataframe(pd.DataFrame(mismatch_data), use_container_width=True)
            st.info("💡 カテゴリー不一致が多い場合、カテゴリー名の見直しや学生への説明が必要かもしれません")
            st.markdown("---")

        st.subheader("🔀 複数カテゴリーにまたがる質問")
        multi_category_logs = [log for log in logs if len(log.get('ai_detected_categories', [])) >= 2]
        if multi_category_logs:
            st.write(f"複数カテゴリーに該当する質問: **{len(multi_category_logs)}件**")
            category_combinations = Counter([
                tuple(sorted(log.get('ai_detected_categories', [])))
                for log in multi_category_logs
            ])
            combo_df = pd.DataFrame([
                (' + '.join(combo), count)
                for combo, count in category_combinations.most_common(5)
            ], columns=['カテゴリー組み合わせ', '件数'])
            st.dataframe(combo_df, use_container_width=True)
        else:
            st.info("複数カテゴリーにまたがる質問はまだありません")

        st.markdown("---")
        st.subheader("❓ よく聞かれる質問（FAQ）")
        qa_logs = [log for log in logs if log.get('mode') == '質問応答' and not log.get('is_blocked', False)]
        faq_data = analyze_faq(qa_logs, top_n=10)
        if faq_data:
            faq_df = pd.DataFrame(faq_data, columns=['質問', '回数'])
            st.dataframe(faq_df, use_container_width=True)
            st.bar_chart(faq_df.set_index('質問'))
        else:
            st.info("質問応答のログがまだありません")

        st.markdown("---")
        st.subheader("⚠️ つまずきポイント分析")
        stumbling_points = analyze_stumbling_points(logs)
        if stumbling_points:
            sp_df = pd.DataFrame(stumbling_points, columns=['カテゴリー', '質問数'])
            st.dataframe(sp_df, use_container_width=True)
            st.write("### 特に注意が必要なカテゴリー（Top 3）")
            for i, (category, count) in enumerate(stumbling_points[:3], 1):
                st.warning(f"**{i}位**: {category} - {count}件の質問")
        else:
            st.info("カテゴリー付きのログがまだありません")

# タブ5: システム概要
with tab5:
    st.header("📋 魔法の黒板 - システム概要")
    knowledge_base = load_knowledge_base()
    categories = load_categories()
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="📚 知識ベース項目数", value=f"{len(knowledge_base)}項目")
    with col2:
        st.metric(label="📂 対応カテゴリー数", value=f"{len(categories)}種類")
    with col3:
        st.metric(label="📖 カバー範囲", value="全8セッション")
    st.markdown("---")
    st.subheader("🎯 主要機能")
    col_func1, col_func2 = st.columns(2)
    with col_func1:
        st.markdown("""
        **学生向け機能**
        - ✅ 24時間質問応答システム
        - ✅ カテゴリー別質問対応
        - ✅ 練習問題自動生成(5択2正解形式)
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

# フッター
st.sidebar.markdown("---")
st.sidebar.info(f"""
📌 現在の設定:
- API: {api_provider}
- モデル: {model}
""")

# タブ6: 学生管理
with tab6:
    st.header("👥 学生管理")
    st.info("警告回数の確認・リセット、アカウントのBAN/解除ができます。")

    try:
        users_result = supabase.table('users').select('student_id, nickname, warning_count, is_banned').order('warning_count', desc=True).execute()
        users_data = users_result.data
    except Exception as e:
        st.error(f"学生データ取得エラー: {e}")
        users_data = []

    if not users_data:
        st.info("登録済み学生がいません")
    else:
        # サマリー
        col_s1, col_s2, col_s3 = st.columns(3)
        total = len(users_data)
        banned = sum(1 for u in users_data if u.get('is_banned', False))
        warned = sum(1 for u in users_data if (u.get('warning_count') or 0) >= 1)
        col_s1.metric("登録学生数", f"{total}名")
        col_s2.metric("警告あり", f"{warned}名")
        col_s3.metric("使用停止中", f"{banned}名")

        st.markdown("---")
        st.subheader("学生一覧")

        for u in users_data:
            wc = u.get('warning_count') or 0
            is_banned = u.get('is_banned', False)

            # 警告レベルに応じた表示色
            if is_banned:
                label = f"🚫 {u['nickname']}（{u['student_id']}）　警告: {wc}回　**【使用停止中】**"
            elif wc >= 4:
                label = f"⛔ {u['nickname']}（{u['student_id']}）　警告: {wc}回"
            elif wc >= 3:
                label = f"⚠️ {u['nickname']}（{u['student_id']}）　警告: {wc}回"
            elif wc >= 1:
                label = f"📢 {u['nickname']}（{u['student_id']}）　警告: {wc}回"
            else:
                label = f"✅ {u['nickname']}（{u['student_id']}）　警告: {wc}回"

            with st.expander(label):
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    if st.button("🔄 警告リセット", key=f"reset_{u['student_id']}"):
                        try:
                            supabase.table('users').update({'warning_count': 0}).eq('student_id', u['student_id']).execute()
                            st.success("✅ 警告カウントをリセットしました")
                            st.rerun()
                        except Exception as e:
                            st.error(f"エラー: {e}")
                with col_b:
                    if is_banned:
                        if st.button("✅ BAN解除", key=f"unban_{u['student_id']}"):
                            try:
                                supabase.table('users').update({'is_banned': False, 'warning_count': 0}).eq('student_id', u['student_id']).execute()
                                st.success("✅ BAN解除・警告リセットしました")
                                st.rerun()
                            except Exception as e:
                                st.error(f"エラー: {e}")
                    else:
                        if st.button("🚫 BAN", key=f"ban_{u['student_id']}"):
                            try:
                                supabase.table('users').update({'is_banned': True}).eq('student_id', u['student_id']).execute()
                                st.success("✅ 使用停止にしました")
                                st.rerun()
                            except Exception as e:
                                st.error(f"エラー: {e}")
