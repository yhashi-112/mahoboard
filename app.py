# ================= 魔法の黒板（通常UI＋ログ保存＋教師モード） =================
import os
import uuid
import sqlite3
from pathlib import Path
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
import pandas as pd
import matplotlib.pyplot as plt

# ---------- .env 読み込み ----------
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TEACHER_PASSWORD = os.getenv("TEACHER_PASSWORD", "")  # 任意。なければ空

client = OpenAI(api_key=OPENAI_API_KEY)

# ---------- DB（SQLite） ----------
DB_PATH = Path(__file__).parent / "mahoboard.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            user_name TEXT,
            question TEXT,
            answer TEXT,
            model TEXT,
            created_at TEXT
        )
        """)
        conn.commit()

def insert_log(session_id: str, user_name: str, question: str, answer: str, model: str):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO logs (session_id, user_name, question, answer, model, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, user_name, question, answer, model, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()

def read_logs_df():
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query("SELECT * FROM logs ORDER BY id DESC", conn)
    return df

init_db()

# ---------- Streamlit 設定 ----------
st.set_page_config(page_title="魔法の黒板", page_icon="🧙‍♂️", layout="centered")

# セッションID（匿名・授業ごとに使い回し可）
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]  # 8文字の簡易ID
if "messages" not in st.session_state:
    st.session_state.messages = []  # [{"role": "user"/"assistant", "content": "..."}]
if "user_name" not in st.session_state:
    st.session_state.user_name = ""

# ---------- ヘッダー（昨日風のシンプルUI） ----------
st.title("🧙‍♂️ 魔法の黒板")
st.caption("授業中に質問して、その場で解決。ログは自動保存。")

# ---------- サイドバー ----------
with st.sidebar:
    st.subheader("設定")
    st.text_input("ニックネーム（任意）", key="user_name", placeholder="例：A班 佐藤")
    model = st.selectbox("モデル", ["gpt-4o-mini", "gpt-4o"], index=0)
    st.write("---")
    teacher_try = st.toggle("教師モード")
    teacher_ok = False
    if teacher_try:
        pwd = st.text_input("教師パスワード", type="password")
        if TEACHER_PASSWORD and pwd == TEACHER_PASSWORD:
            teacher_ok = True
            st.success("教師モードON")
        elif TEACHER_PASSWORD == "":
            teacher_ok = True
            st.info("（.env に TEACHER_PASSWORD 未設定のため、誰でも教師モードに入れます）")
        else:
            st.error("パスワードが違います")

# ---------- 教師モード（分析UI） ----------
def teacher_view():
    st.header("📊 教師モード：分析ダッシュボード")
    df = read_logs_df()
    if df.empty:
        st.info("まだログがありません。")
        return

    # フィルター
    c1, c2, c3 = st.columns(3)
    with c1:
        model_f = st.multiselect("モデルで絞り込み", sorted(df["model"].dropna().unique().tolist()))
    with c2:
        user_f = st.text_input("ニックネームに含む語", "")
    with c3:
        kw = st.text_input("質問/回答に含む語", "")

    dfv = df.copy()
    if model_f:
        dfv = dfv[dfv["model"].isin(model_f)]
    if user_f:
        dfv = dfv[dfv["user_name"].fillna("").str.contains(user_f, case=False)]
    if kw:
        dfv = dfv[dfv["question"].fillna("").str.contains(kw, case=False) | dfv["answer"].fillna("").str.contains(kw, case=False)]

    st.write(f"件数: {len(dfv)}")
    st.dataframe(dfv[["id","created_at","user_name","model","question","answer"]], use_container_width=True)

    # 時系列集計（1日あたりの質問数）
    dfv["date"] = pd.to_datetime(dfv["created_at"]).dt.date
    count_by_date = dfv.groupby("date")["id"].count().reset_index().rename(columns={"id":"count"})

    fig = plt.figure()
    plt.plot(count_by_date["date"], count_by_date["count"])
    plt.title("日別質問件数")
    plt.xlabel("日付")
    plt.ylabel("件数")
    st.pyplot(fig)

    # CSV出力
    csv = dfv.to_csv(index=False).encode("utf-8-sig")
    st.download_button("CSV をダウンロード", data=csv, file_name="mahoboard_logs_filtered.csv", mime="text/csv")

# ---------- 学生UI（チャット風・昨日の見た目に近い） ----------
def student_view():
    # 既存メッセージ表示（簡易バブル）
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(f"""
<div style="background:#eef6ff;border:1px solid #cfe1ff;padding:10px;border-radius:12px;margin:6px 0;text-align:left;">
<b>学生</b><br>{msg["content"]}
</div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""
<div style="background:#f7f7f7;border:1px solid #e6e6e6;padding:10px;border-radius:12px;margin:6px 0;">
<b>AI</b><br>{msg["content"]}
</div>""", unsafe_allow_html=True)

    # 入力欄
    prompt = st.text_area("質問を入力", "", height=100, placeholder="例：ベンゾジアゼピン系睡眠薬の特徴は？")

    c1, c2 = st.columns([1,1])
    with c1:
        send = st.button("送信")
    with c2:
        clear = st.button("履歴クリア")

    if clear:
        st.session_state.messages = []
        st.success("履歴をクリアしました")
        st.stop()

    if send:
        q = prompt.strip()
        if not q:
            st.warning("質問を入力してください。")
            st.stop()

        # 画面に先に表示
        st.session_state.messages.append({"role": "user", "content": q})

        # 推論
        with st.spinner("考え中..."):
            try:
                res = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": q}],
                    max_tokens=600,
                )
                ans = res.choices[0].message.content
            except Exception as e:
                ans = f"エラー: {e}"

        # 表示＆保存
        st.session_state.messages.append({"role": "assistant", "content": ans})
        insert_log(st.session_state.session_id, st.session_state.user_name, q, ans, model)
        st.rerun()

# ---------- 画面出し分け ----------
if teacher_try and teacher_ok:
    teacher_view()
else:
    student_view()

st.markdown("---")
st.caption("© 2025 魔法の黒板 / セッションID: " + st.session_state.session_id)
# =======================================================================
