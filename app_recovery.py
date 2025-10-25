# ===== Minimal Known-Good app.py for "魔法の黒板" =====

# app.py 冒頭だけをこの形にしておくのがベストです
import os
from pathlib import Path
from dotenv import load_dotenv

# --- .env を明示パスで読み込む（確実に動作）---
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

# --- OpenAI の初期化 ---
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

import os
from pathlib import Path
import streamlit as st

# --- .env を明示パスで読み込む（最優先） ---
def force_load_dotenv():
    try:
        from dotenv import load_dotenv
    except Exception as e:
        return False, f"python-dotenv 未インストールかも: {e}"

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        try:
            load_dotenv(dotenv_path=env_path, override=True)
            return True, f".env loaded from: {env_path}"
        except Exception as e:
            return False, f".env 読み込みエラー: {e}"
    else:
        return False, f".env not found at: {env_path}"

loaded, load_msg = force_load_dotenv()

# --- 確認表示（キー本体は表示しない） ---
st.caption(load_msg)

key = os.getenv("OPENAI_API_KEY")
cwd = Path.cwd()
here = Path(__file__).parent
env_here = here / ".env"
st.write(f"**cwd:** {cwd}")
st.write(f"**__file__ の親:** {here}")
st.write(f"**.env (同階層) 存在:** {env_here.exists()}")

if not key:
    st.error("OPENAI_API_KEY を読み込めていません ❌（.env の場所/記法/作業ディレクトリを確認）")
    st.info("応急処置: ターミナルで `export OPENAI_API_KEY=\"sk-...\"` を実行してから再起動すると切り分けできます。")
    st.stop()
else:
    st.success("OPENAI_API_KEY を読み込みました ✅")

# --- OpenAI SDK 検出（新旧どちらでも動く） ---
client_type = None
client_obj = None
error_init = None
try:
    # 新SDK
    from openai import OpenAI
    client_obj = OpenAI(api_key=key)  # env でも可
    client_type = "new"
except Exception as e_new:
    try:
        # 旧SDK
        import openai
        openai.api_key = key
        client_obj = openai
        client_type = "legacy"
    except Exception as e_old:
        error_init = f"OpenAI SDK 初期化に失敗: new={e_new} / legacy={e_old}"

if error_init:
    st.error(error_init)
    st.stop()
else:
    st.caption(f"OpenAI SDK モード: {client_type}")

# --- 動作テスト（キーが読めていれば1トークン返答を出せるはず） ---
prompt = st.text_input("質問を入力してください", "ベンゾジアゼピン系睡眠薬の特徴は？")
if st.button("送信"):
    try:
        if client_type == "new":
            resp = client_obj.chat.completions.create(
                model="gpt-4o-mini",  # 利用可能な軽量モデル例。契約に合わせて変更可
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            reply = resp.choices[0].message.content
        else:
            resp = client_obj.ChatCompletion.create(
                model="gpt-3.5-turbo",  # 旧SDK例。契約に合わせて変更可
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            reply = resp.choices[0].message.content

        st.markdown("**回答:**")
        st.write(reply)
    except Exception as e:
        st.error(f"API 呼び出しでエラー: {e}")
# ===== end =====
