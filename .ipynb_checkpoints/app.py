import streamlit as st
import os
from dotenv import load_dotenv
from openai import OpenAI
from anthropic import Anthropic
import json
from datetime import datetime

# 環境変数の読み込み
load_dotenv()

# ページ設定
st.set_page_config(
    page_title="魔法の黒板 - 学生用",
    page_icon="🎓",
    layout="centered"
)

# デフォルトAPIの読み込み（.envで設定）
DEFAULT_API = os.getenv('DEFAULT_API', 'OpenAI')  # デフォルトはOpenAI
DEFAULT_MODEL_OPENAI = os.getenv('DEFAULT_MODEL_OPENAI', 'gpt-4o')
DEFAULT_MODEL_CLAUDE = os.getenv('DEFAULT_MODEL_CLAUDE', 'claude-sonnet-4-20250514')

# APIクライアントの初期化
@st.cache_resource
def initialize_clients():
    openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    return openai_client, anthropic_client

openai_client, anthropic_client = initialize_clients()

# カテゴリーの読み込み
@st.cache_data
def load_categories():
    try:
        with open('categories.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # デフォルトカテゴリー
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
        # 保存
        with open('categories.json', 'w', encoding='utf-8') as f:
            json.dump(default_categories, f, ensure_ascii=False, indent=2)
        return default_categories

categories = load_categories()

# 知識ベースの読み込み
@st.cache_data
def load_knowledge_base():
    try:
        with open('knowledge_base.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

knowledge_base = load_knowledge_base()

# ログ保存関数
def save_log(nickname, mode, question, answer, category=None, difficulty=None, num_problems=None):
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_data = {
        "timestamp": timestamp,
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nickname": nickname,
        "mode": mode,
        "api_provider": DEFAULT_API,
        "model": DEFAULT_MODEL_OPENAI if DEFAULT_API == "OpenAI" else DEFAULT_MODEL_CLAUDE,
        "category": category,
        "difficulty": difficulty,
        "num_problems": num_problems,
        "question": question,
        "answer": answer
    }
    
    filename = f"{log_dir}/{nickname}_{timestamp}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

# 質問応答関数
def answer_question(question, category):
    # 関連するQ&Aを検索
    relevant_items = []
    question_lower = question.lower()
    
    # カテゴリー別キーワード
    category_keywords = {
        "情報": ["情報", "データ", "知識"],
        "情報源": ["情報源", "文献", "データベース", "添付文書", "インタビューフォーム", "審査報告書"],
        "情報の収集・評価・加工・提供・管理": ["収集", "評価", "加工", "提供", "管理", "検索"],
        "EBM": ["ebm", "エビデンス", "evidence", "システマティックレビュー", "メタアナリシス"],
        "生物統計": ["統計", "p値", "信頼区間", "検定", "有意差", "平均", "標準偏差", "回帰"],
        "研究デザインと解析": ["研究デザイン", "rct", "ランダム化", "コホート", "症例対照", "横断研究", "解析"],
        "医薬品の採用・比較・評価": ["採用", "比較", "評価", "医薬品", "薬剤"],
        "患者情報とその収集・評価・管理": ["患者", "カルテ", "診療録", "副作用"],
        "その他": []
    }
    
    for item in knowledge_base:
        # カテゴリーマッチング
        if category != "すべて" and category in category_keywords:
            keywords = category_keywords[category]
            if keywords:
                category_match = any(kw in item['question'].lower() or kw in item['answer'].lower() 
                                   for kw in keywords)
                if not category_match:
                    continue
        
        # キーワードマッチング
        if any(keyword in question_lower for keyword in item.get('keywords', [])):
            relevant_items.append(item)
    
    # コンテキストの構築
    context = ""
    if relevant_items:
        context = "以下の関連情報を参考にしてください:\n\n"
        for item in relevant_items[:3]:
            context += f"Q: {item['question']}\nA: {item['answer']}\n\n"
    
    system_prompt = f"""あなたは医薬品情報学の教育を支援するAIアシスタントです。
カテゴリー「{category}」に関する質問に答えています。
学生の質問に対して、わかりやすく丁寧に説明してください。
統計学や臨床研究の概念を説明する際は、具体例を交えて説明してください。"""

    user_prompt = f"""{context}

学生からの質問: {question}

上記の質問に対して、教育的な観点から丁寧に回答してください。"""

    # API選択
    if DEFAULT_API == "OpenAI":
        model = DEFAULT_MODEL_OPENAI
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        return response.choices[0].message.content
    else:  # Claude
        model = DEFAULT_MODEL_CLAUDE
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=2000,
            temperature=0.7,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.content[0].text

# 練習問題生成関数（5択2正解形式）
def generate_practice_problem(topic, difficulty, num_problems):
    # 難易度の説明
    difficulty_descriptions = {
        "優しい": "基本的な概念の理解を確認する入門レベルの問題",
        "普通": "標準的な理解度を確認する中級レベルの問題",
        "難しい": "応用力と深い理解を問う上級レベルの問題"
    }
    
    # トピック関連のコンテキスト構築
    context = ""
    topic_lower = topic.lower()
    
    relevant_items = []
    for item in knowledge_base:
        if any(keyword in topic_lower for keyword in item.get('keywords', [])):
            relevant_items.append(item)
    
    if relevant_items:
        context = "以下の内容を参考に問題を作成してください:\n\n"
        for item in relevant_items[:2]:
            context += f"Q: {item['question']}\nA: {item['answer']}\n\n"
    
    system_prompt = """あなたは医薬品情報学の教育を支援するAIアシスタントです。
学生の理解度を確認するための練習問題を作成してください。

【重要な制約】
1. 選択肢は必ず5つ作成
2. 正解は必ず2つ（3つ以上、1つ以下は絶対に作らない）
3. 正解の位置は偏らせず、様々なパターンにする（1,2 / 2,4 / 3,5など）
4. 問題文と選択肢の内容が矛盾しないよう細心の注意を払う
5. 「データの種類」と「統計手法」が一致するよう確認する
   - カテゴリカルデータ（あり/なし、有効/無効など）→ カイ二乗検定、Fisherの正確検定など
   - 数量データ（血圧、体重など）→ t検定、分散分析、回帰分析など
6. 誤った選択肢は明確に誤りであり、紛らわしくないこと"""

    user_prompt = f"""{context}

テーマ: {topic}
難易度: {difficulty}（{difficulty_descriptions[difficulty]}）
問題数: {num_problems}問

上記の条件で練習問題を{num_problems}問作成してください。

【必須の出力形式】

問題番号: 1
問題文: （問題文を記載）
選択肢1: （選択肢の内容）
選択肢2: （選択肢の内容）
選択肢3: （選択肢の内容）
選択肢4: （選択肢の内容）
選択肢5: （選択肢の内容）
正解: 2,4（正解の番号を2つカンマ区切りで。1,3のような偏った組み合わせを避ける）
解説: （なぜその2つが正解で、他の3つが誤りなのかを明確に説明）
---

【品質チェック項目】
✓ 選択肢は5つあるか
✓ 正解は2つか（1つでも3つでもない）
✓ 正解番号は偏っていないか（前回1,3なら今回は2,4や3,5など）
✓ 問題文と選択肢に矛盾はないか
✓ データの種類と統計手法は一致しているか"""

    # API選択
    if DEFAULT_API == "OpenAI":
        model = DEFAULT_MODEL_OPENAI
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.8,
            max_tokens=3000
        )
        return response.choices[0].message.content
    else:  # Claude
        model = DEFAULT_MODEL_CLAUDE
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=3000,
            temperature=0.8,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.content[0].text

# 問題テキストをパース
def parse_problem(problem_text):
    """生成された問題テキストを構造化データに変換"""
    problems = []
    
    # 問題ごとに分割
    problem_blocks = problem_text.split('---')
    
    for block in problem_blocks:
        if not block.strip():
            continue
            
        problem_data = {
            'question': '',
            'choices': [],
            'correct_answers': [],
            'explanation': ''
        }
        
        lines = block.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('問題文:'):
                problem_data['question'] = line.replace('問題文:', '').strip()
            elif line.startswith('選択肢'):
                # 選択肢から番号と内容を分離
                choice_text = line.split(':', 1)[1].strip() if ':' in line else line
                problem_data['choices'].append(choice_text)
            elif line.startswith('正解:'):
                answers = line.replace('正解:', '').strip()
                # カンマ区切りで分割して数値に変換
                try:
                    problem_data['correct_answers'] = [int(a.strip()) for a in answers.split(',')]
                except:
                    problem_data['correct_answers'] = []
            elif line.startswith('解説:'):
                problem_data['explanation'] = line.replace('解説:', '').strip()
        
        if problem_data['question'] and problem_data['choices']:
            problems.append(problem_data)
    
    return problems

# メインUI
st.title("🎓 魔法の黒板")
st.write("医薬品情報学の学習をサポートします")

# ニックネーム入力
nickname = st.text_input("📝 ニックネーム（仮名）を入力してください", placeholder="例：A姓 佐藤")

if not nickname:
    st.info("👆 まずはニックネームを入力してください")
    st.stop()

st.success(f"ようこそ、**{nickname}** さん！")

# タブ切り替え
tab1, tab2 = st.tabs(["💬 質問する", "📝 練習問題"])

# タブ1: 質問
with tab1:
    st.header("質問する")
    
    # カテゴリー選択
    col1, col2 = st.columns([2, 3])
    with col1:
        category = st.selectbox(
            "📂 カテゴリーを選択",
            ["すべて"] + categories,
            help="質問のカテゴリーを選択してください"
        )
    
    # 質問入力
    question = st.text_area(
        "❓ 質問を入力してください",
        height=150,
        placeholder="例：p値とは何ですか？信頼区間との違いを教えてください。"
    )
    
    if st.button("🔍 質問する", type="primary", use_container_width=True):
        if question:
            with st.spinner('回答を生成中...'):
                answer = answer_question(question, category)
                st.markdown("### 📖 回答")
                st.write(answer)
                
                # ログ保存
                save_log(nickname, "質問応答", question, answer, category=category)
                st.success("✅ 質問と回答を保存しました")
        else:
            st.warning("⚠️ 質問を入力してください")

# タブ2: 練習問題
with tab2:
    st.header("練習問題を生成")
    
    # トピック入力
    topic = st.text_input(
        "📚 学習したいトピックを入力してください",
        placeholder="例：p値、信頼区間、バイアス"
    )
    
    # 難易度と問題数
    col1, col2 = st.columns(2)
    with col1:
        difficulty = st.selectbox(
            "📊 難易度を選択",
            ["優しい", "普通", "難しい"],
            index=1
        )
    with col2:
        num_problems = st.selectbox(
            "🔢 問題数を選択",
            [1, 2, 3],
            index=0
        )
    
    if st.button("📝 練習問題を生成", type="primary", use_container_width=True):
        if topic:
            with st.spinner(f'{num_problems}問の練習問題を生成中...'):
                problem_text = generate_practice_problem(topic, difficulty, num_problems)
                problems = parse_problem(problem_text)
                
                # セッションステートを完全にリセット
                st.session_state.problems = problems
                st.session_state.user_answers = [[] for _ in problems]
                st.session_state.show_results = [False for _ in problems]
                st.session_state.show_explanation = [False for _ in problems]
                st.session_state.problem_version = st.session_state.get('problem_version', 0) + 1  # バージョンを更新
                
                # ログ保存
                save_log(nickname, "練習問題", topic, problem_text, 
                        difficulty=difficulty, num_problems=num_problems)
        else:
            st.warning("⚠️ トピックを入力してください")
    
    # 生成された問題を表示
    if 'problems' in st.session_state and st.session_state.problems:
        st.markdown("---")
        
        for idx, problem in enumerate(st.session_state.problems):
            st.markdown(f"### 📋 問題 {idx + 1}")
            st.write(problem['question'])
            
            # 選択肢（チェックボックス）- バージョンをキーに含めてリセット
            st.write("**選択肢（正解を2つ選んでください）**")
            
            selected = []
            version = st.session_state.get('problem_version', 0)
            for i, choice in enumerate(problem['choices']):
                # 番号を必ず付ける（既に番号がある場合は除去してから付け直す）
                choice_clean = choice
                # 既存の "1. " "2. " などを削除
                for num in range(1, 6):
                    if choice_clean.startswith(f"{num}. "):
                        choice_clean = choice_clean[3:].strip()
                        break
                
                # 新しい番号を付ける
                choice_text = f"{i+1}. {choice_clean}"
                
                if st.checkbox(choice_text, key=f"choice_v{version}_{idx}_{i}"):
                    selected.append(i + 1)
            
            # 選択した答えを保存
            st.session_state.user_answers[idx] = selected
            
            # 解答を確認ボタン
            col1, col2 = st.columns(2)
            version = st.session_state.get('problem_version', 0)
            with col1:
                if st.button(f"✓ 解答を確認", key=f"check_v{version}_{idx}"):
                    st.session_state.show_results[idx] = True
            
            # 正誤判定表示
            if st.session_state.show_results[idx]:
                user_ans = set(st.session_state.user_answers[idx])
                correct_ans = set(problem['correct_answers'])
                
                if user_ans == correct_ans:
                    st.success("✅ 正解です！")
                else:
                    st.error("❌ 不正解です")
                    st.write(f"あなたの解答: {sorted(list(user_ans))}")
                    st.write(f"正解: {sorted(list(correct_ans))}")
                
                # 解説表示ボタン
                with col2:
                    if st.button(f"📖 解答と解説を見る", key=f"explain_v{version}_{idx}"):
                        st.session_state.show_explanation[idx] = True
            
            # 解説表示
            if st.session_state.show_explanation[idx]:
                st.info(f"**解説**: {problem['explanation']}")
            
            st.markdown("---")

# フッター
st.markdown("---")
st.caption(f"💡 使用中のAI: {DEFAULT_API}")
