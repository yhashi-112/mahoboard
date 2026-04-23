import streamlit as st
import os
from dotenv import load_dotenv
from openai import OpenAI
from anthropic import Anthropic
import google.generativeai as genai
import json
from datetime import datetime
import hashlib
from supabase import create_client, Client

# 環境変数の読み込み
load_dotenv()

# ページ設定
st.set_page_config(
    page_title="魔法の黒板 - 学生用",
    page_icon="🎓",
    layout="centered"
)

# NGワード設定
BLOCK_WORDS_STRICT = [
    "氏名", "名前", "本名", "住所", "電話番号", "メールアドレス",
    "LINE", "クレジットカード", "マイナンバー",
    "自殺", "死にたい", "殺す", "殺したい",
    "犯罪", "逮捕", "暴力", "死ね", "殺害"
]
BLOCK_WORDS_SEX = [
    "セックス", "ポルノ", "アダルト", "性行為", "エロ"
]
BLOCK_WORDS_NON_MEDICAL = [
    "ギャンブル", "競馬", "パチンコ", "副業", "FX",
    "暗号資産", "占い", "霊", "オカルト"
]

# 不適切コンテンツチェック関数
def check_inappropriate_content(text):
    """
    入力テキストに不適切な内容が含まれているかチェック
    Returns: (category, detected_word) or (None, None)
    """
    if not text:
        return None, None
    
    text_check = text.lower()
    
    # 厳重ブロック（個人情報・危険な内容）
    for word in BLOCK_WORDS_STRICT:
        if word.lower() in text_check:
            return "strict", word
    
    # 性的コンテンツ
    for word in BLOCK_WORDS_SEX:
        if word.lower() in text_check:
            return "sexual", word
    
    # 医薬学無関係
    for word in BLOCK_WORDS_NON_MEDICAL:
        if word.lower() in text_check:
            return "off_topic", word
    
    return None, None

# 警告メッセージ生成関数
def get_warning_message(category):
    """カテゴリに応じた警告メッセージを返す"""
    messages = {
        "strict": """
⚠️ **不適切な内容が検出されました**

申し訳ございませんが、この質問には回答できません。

- 個人情報に関する質問
- 危険な内容を含む質問
- 暴力的な表現を含む質問

は、このシステムでは受け付けておりません。

**薬学の学習に関する質問**をお願いします。
        """,
        "sexual": """
⚠️ **不適切な内容が検出されました**

申し訳ございませんが、この質問には回答できません。

このシステムは**薬学教育**を目的としています。
性的な内容に関する質問は受け付けておりません。

**薬学の学習に関する質問**をお願いします。
        """,
        "off_topic": """
⚠️ **授業内容と関係のない質問です**

申し訳ございませんが、この質問には回答できません。

このシステムは以下の内容に特化しています：
- 生物統計学
- 臨床研究デザイン
- EBM（根拠に基づく医療）
- 医薬品情報評価
- 患者情報管理

**薬学情報学に関する質問**をお願いします。
        """
    }
    return messages.get(category, "不適切な内容が検出されました。")

# デフォルトAPIの読み込み（.envで設定）
DEFAULT_API = os.getenv('DEFAULT_API', 'Claude')  # デフォルトはClaude
DEFAULT_MODEL_OPENAI = os.getenv('DEFAULT_MODEL_OPENAI', 'gpt-5.4')
DEFAULT_MODEL_CLAUDE = os.getenv('DEFAULT_MODEL_CLAUDE', 'claude-sonnet-4-6')
DEFAULT_MODEL_GEMINI = os.getenv('DEFAULT_MODEL_GEMINI', 'gemini-3.1-pro-preview')

# APIクライアントの初期化
@st.cache_resource
def initialize_clients():
    openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    gemini_api_key = os.getenv('GEMINI_API_KEY') or st.secrets.get('GEMINI_API_KEY', '')
    if gemini_api_key:
        genai.configure(api_key=gemini_api_key)
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
        with open('knowledge_base_complete_137items.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 辞書形式の場合はqa_pairsリストを返す
            if isinstance(data, dict):
                return data.get('qa_pairs', [])
            return data
    except FileNotFoundError:
        return []

knowledge_base = load_knowledge_base()

# AIによるカテゴリー自動判定関数
def detect_categories_ai(question, available_categories):
    """
    AIを使用して質問内容から該当カテゴリーを判定
    Returns: list of categories (複数の場合もあり)
    """
    if not question or len(question.strip()) < 5:
        return []
    
    categories_text = "\n".join([f"- {cat}" for cat in available_categories])
    
    system_prompt = """あなたは医薬品情報学の専門家です。
学生の質問内容を分析し、該当するカテゴリーを判定してください。
複数のカテゴリーにまたがる場合は、すべて列挙してください。
どのカテゴリーにも該当しない場合は「その他」を選択してください。"""

    user_prompt = f"""以下のカテゴリーから、この質問に該当するものをすべて選んでください。

【カテゴリー一覧】
{categories_text}

【学生の質問】
{question}

【回答形式】
該当するカテゴリー名をカンマ区切りで出力してください。
例1: 生物統計
例2: EBM, 研究デザインと解析
例3: その他

カテゴリー名のみを出力し、説明は不要です。"""

    try:
        # API選択
        if DEFAULT_API == "OpenAI":
            response = openai_client.chat.completions.create(
                model=DEFAULT_MODEL_OPENAI,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # 判定は保守的に
                max_tokens=100
            )
            result = response.choices[0].message.content.strip()
        elif DEFAULT_API == "Claude":
            response = anthropic_client.messages.create(
                model=DEFAULT_MODEL_CLAUDE,
                max_tokens=100,
                temperature=0.3,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            result = response.content[0].text.strip()
        
        else:  # Gemini
            model = genai.GenerativeModel(DEFAULT_MODEL_GEMINI)
            prompt = system_prompt + "\n\n" + user_prompt
            response = model.generate_content(prompt)
            result = response.text.strip()
        
        # カンマ区切りで分割してリスト化
        detected = [cat.strip() for cat in result.split(',')]
        # 有効なカテゴリーのみ返す
        valid_detected = [cat for cat in detected if cat in available_categories]
        return valid_detected if valid_detected else ["その他"]
        
    except Exception as e:
        # エラー時は空リストを返す
        print(f"カテゴリー判定エラー: {e}")
        return []

# ログ保存関数
def save_log(nickname, mode, question, answer, category=None, difficulty=None, num_problems=None, is_blocked=False, block_reason=None, ai_detected_categories=None):
    """
    学生とAIのやり取りをSupabaseのlogsテーブルに記録
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    category_mismatch = False if not ai_detected_categories or not category else (category not in ai_detected_categories and category != "すべて")
    
    log_data = {
        "timestamp": timestamp,
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nickname": nickname,
        "mode": mode,
        "api_provider": DEFAULT_API,
        "model": DEFAULT_MODEL_OPENAI if DEFAULT_API == "OpenAI" else DEFAULT_MODEL_CLAUDE,
        "student_selected_category": category or "",
        "ai_detected_categories": json.dumps(ai_detected_categories if ai_detected_categories else [], ensure_ascii=False),
        "category_mismatch": category_mismatch,
        "difficulty": difficulty or "",
        "num_problems": str(num_problems) if num_problems else "",
        "question": question or "",
        "answer": answer or "",
        "is_blocked": is_blocked,
        "block_reason": block_reason or ""
    }
    
    try:
        supabase.table('logs').insert(log_data).execute()
    except Exception as e:
        print(f"ログ保存エラー: {e}")

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
    elif DEFAULT_API == "Gemini":
        model = genai.GenerativeModel(DEFAULT_MODEL_GEMINI)
        prompt = system_prompt + "\n\n" + user_prompt
        response = model.generate_content(prompt)
        return response.text
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
5. **すべての選択肢は問題文のテーマに直接関連していること（最重要）**
   - 問題のテーマに含まれる概念や関連指標を選択肢に使用する（詳細は項目7参照）
   - ただし、全く無関係な分野や概念を選択肢に含めない
   - 例: 問題「スクリーニング検査の評価」であれば、感度・特異度・陽性反応的中度などの関連指標は選択肢に含めて良い
   - NG例: 「スクリーニング検査の評価」の問題で「プラセボ効果」など全く別の概念を選択肢にする
6. **計算式そのものを選択肢にしないこと（重要）**
   - NG: 「陽性反応的中度は200/(200+800)で計算される」
   - NG: 「感度は真陽性/(真陽性+偽陰性)である」
   - 理由: 計算式が正しい場合、その計算結果の数値と実質的に同じ内容となり、正解が複数になってしまう
   - 選択肢は具体的な数値、概念、定義、解釈のいずれかで構成し、計算過程や計算式は含めない
7. **項目内の関連概念を選択肢に組み入れること（重要）**
   - 検査関連（陽性反応的中度、感度、特異度など）の問題を作成する場合:
     * 正解: その項目の正しい値や解釈（2つ）
     * 誤答: 明確に誤った数値や解釈（3つ）
     * 同じ検査データ内の他の指標（感度、特異度、尤度比、陰性反応的中度など）も選択肢に含めて良い
     * **重要: 他の指標の値が計算上正しい場合、それを誤答にしてはいけない**
     * 例: 「感度と特異度を問う問題」で陽性反応的中度の正しい値を選択肢に入れる場合、その選択肢も正解として扱うか、または最初から含めない
   - 統計関連（NNT、RRR、ARRなど）の問題を作成する場合:
     * 正解: その指標の正しい値や解釈（2つ）
     * 誤答: 明確に誤った数値や解釈（3つ）
     * 同じ統計テーマ内の他の指標の値や解釈を選択肢に含めて良い
     * **重要: 他の指標の値が計算上正しい場合、それを誤答にしてはいけない**
   - その他すべての項目も同様: 計算や事実として正しい内容は、問題の主旨に含まれない場合は選択肢に入れない
8. 「データの種類」と「統計手法」が一致するよう確認する
   - カテゴリカルデータ（あり/なし、有効/無効など）→ カイ二乗検定、Fisherの正確検定など
   - 数量データ（血圧、体重など）→ t検定、分散分析、回帰分析など
9. 誤った選択肢は明確に誤りであり、紛らわしくないこと
   - **計算や事実として正しい内容を「問題の趣旨と違う」という理由で誤答にしてはいけない**
   - 誤答は数値が間違っている、定義が間違っている、解釈が間違っているなど、明確な誤りのみ
   - 例: NG「陽性反応的中度は60%である（計算は正しいが問題の趣旨と違うので不正解）」
   - 例: OK「陽性反応的中度は80%である（計算が間違っているので不正解）」
10. 問題文は必ず「〜正しいのはどれか。2つ選べ。」で終わること
11. 解説は以下の形式で記載すること：
   - 第1段落：「〜を問う問題です。」（問題の概要）
   - 第2段落：【正解の解説】正解の選択肢がなぜ正しいかを説明
   - 第3段落：【誤りの解説】誤りの選択肢がなぜ誤りかを説明"""

    user_prompt = f"""{context}

テーマ: {topic}
難易度: {difficulty}（{difficulty_descriptions[difficulty]}）
問題数: {num_problems}問

上記の条件で練習問題を{num_problems}問作成してください。

【必須の出力形式】

問題番号: 1
問題文: （問題文を記載。必ず「〜正しいのはどれか。2つ選べ。」で終わること）
選択肢1: （選択肢の内容）
選択肢2: （選択肢の内容）
選択肢3: （選択肢の内容）
選択肢4: （選択肢の内容）
選択肢5: （選択肢の内容）
正解: 2,4（正解の番号を2つカンマ区切りで。1,3のような偏った組み合わせを避ける）
解説: 〜を問う問題です。

【正解の解説】選択肢2は〜、選択肢4は〜が正しいため正解です。

【誤りの解説】選択肢1は〜、選択肢3は〜、選択肢5は〜が誤りです。
---

【品質チェック項目】
✓ 選択肢は5つあるか
✓ 正解は2つか（1つでも3つでもない）
✓ 正解番号は偏っていないか（前回1,3なら今回は2,4や3,5など）
✓ 問題文と選択肢に矛盾はないか
✓ **すべての選択肢が問題のテーマに直接関連しているか（最重要）**
✓ データの種類と統計手法は一致しているか
✓ 問題文は「〜正しいのはどれか。2つ選べ。」で終わっているか
✓ 解説は3段落構成になっているか"""

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
            max_tokens=3000
        )
        return response.choices[0].message.content
    elif DEFAULT_API == "Gemini":
        model = genai.GenerativeModel(DEFAULT_MODEL_GEMINI)
        prompt = system_prompt + "\n\n" + user_prompt
        response = model.generate_content(prompt)
        return response.text
    else:  # Claude
        model = DEFAULT_MODEL_CLAUDE
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=3000,
            temperature=0.7,
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
        current_section = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # セクション判定
            if line.startswith('問題番号:') or line.startswith('問題文:'):
                current_section = 'question'
                if line.startswith('問題文:'):
                    problem_data['question'] = line.replace('問題文:', '').strip()
            elif line.startswith('選択肢1:'):
                current_section = 'choices'
                problem_data['choices'].append(line.replace('選択肢1:', '').strip())
            elif line.startswith('選択肢2:'):
                problem_data['choices'].append(line.replace('選択肢2:', '').strip())
            elif line.startswith('選択肢3:'):
                problem_data['choices'].append(line.replace('選択肢3:', '').strip())
            elif line.startswith('選択肢4:'):
                problem_data['choices'].append(line.replace('選択肢4:', '').strip())
            elif line.startswith('選択肢5:'):
                problem_data['choices'].append(line.replace('選択肢5:', '').strip())
            elif line.startswith('正解:'):
                current_section = 'answers'
                answers = line.replace('正解:', '').strip()
                try:
                    # カンマまたはスペース区切りで分割
                    answer_parts = answers.replace(' ', ',').split(',')
                    problem_data['correct_answers'] = [int(a.strip()) for a in answer_parts if a.strip().isdigit()]
                except:
                    problem_data['correct_answers'] = []
            elif line.startswith('解説:'):
                current_section = 'explanation'
                problem_data['explanation'] = line.replace('解説:', '').strip()
            elif current_section == 'explanation':
                # 解説の続き
                problem_data['explanation'] += ' ' + line
        
        # 選択肢が5個で、正解が2個の場合のみ追加
        if (problem_data['question'] and 
            len(problem_data['choices']) == 5 and 
            len(problem_data['correct_answers']) == 2):
            problems.append(problem_data)
    
    return problems

# メインUI
# タイトルはタブ内で表示するため、ここでは表示しない

# ===== ユーザー管理関数 (Supabase対応) =====

@st.cache_resource
def init_supabase() -> Client:
    url = os.getenv('SUPABASE_URL') or st.secrets.get('SUPABASE_URL', '')
    key = os.getenv('SUPABASE_KEY') or st.secrets.get('SUPABASE_KEY', '')
    return create_client(url, key)

supabase = init_supabase()

def hash_password(password):
    """パスワードをSHA-256でハッシュ化"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def register_user(student_id, nickname, password):
    """新規ユーザー登録。成功時True、学籍番号重複時Falseを返す"""
    try:
        # 既存ユーザー確認
        existing = supabase.table('users').select('student_id').eq('student_id', student_id).execute()
        if existing.data:
            return False, "この学籍番号はすでに登録されています"
        # 新規登録
        supabase.table('users').insert({
            "student_id": student_id,
            "nickname": nickname,
            "password_hash": hash_password(password),
        }).execute()
        return True, "登録成功"
    except Exception as e:
        return False, f"登録エラー: {e}"

def login_user(student_id, password):
    """ログイン認証。成功時(True, nickname)、失敗時(False, エラーメッセージ)を返す"""
    try:
        result = supabase.table('users').select('nickname, password_hash').eq('student_id', student_id).execute()
        if not result.data:
            return False, "学籍番号が見つかりません。初めての方は「新規登録」タブから登録してください"
        user = result.data[0]
        if user['password_hash'] != hash_password(password):
            return False, "パスワードが正しくありません"
        return True, user['nickname']
    except Exception as e:
        return False, f"ログインエラー: {e}"

# ===== 認証UI =====

st.markdown("""
<div style='text-align: center; padding: 2rem 0;'>
    <h1 style='font-size: 2.5rem; margin-bottom: 1rem;'>🎓 ようこそ！魔法の黒板へ</h1>
    <p style='font-size: 1.2rem; color: #666;'>いつでもあなたの学習をサポートします</p>
</div>
""", unsafe_allow_html=True)

# 注意事項の表示
with st.expander("⚠️ 利用上の注意事項（必ずお読みください）"):
    st.markdown("""
    このシステムは**薬学教育**を目的としています。
    
    **以下の内容は質問できません：**
    - 個人情報に関する内容（氏名、住所、電話番号など）
    - 危険・暴力的な内容
    - 性的な内容
    - 授業と無関係な内容（ギャンブル、占いなど）
    
    **質問できる内容：**
    - 情報
    - 情報源
    - 情報の収集・評価・加工・提供・管理
    - EBM（根拠に基づく医療）
    - 生物統計
    - 研究デザインと解析
    - 医薬品の採用・比較・評価
    - 患者情報とその収集・評価・管理
    
    不適切な質問には回答できませんので、ご了承ください。
    """)

# セッション状態の初期化
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "nickname" not in st.session_state:
    st.session_state.nickname = ""
if "student_id" not in st.session_state:
    st.session_state.student_id = ""

# 未ログインの場合は認証画面を表示
if not st.session_state.authenticated:
    auth_tab1, auth_tab2 = st.tabs(["🔑 ログイン", "📝 新規登録"])

    with auth_tab1:
        st.subheader("ログイン")
        with st.form(key="login_form"):
            login_id = st.text_input("学籍番号", key="login_id", placeholder="例：24P001")
            login_pw = st.text_input("パスワード", type="password", key="login_pw")
            submitted = st.form_submit_button("ログイン", type="primary", use_container_width=True)
        if submitted:
            if login_id and login_pw:
                ok, result = login_user(login_id, login_pw)
                if ok:
                    st.session_state.authenticated = True
                    st.session_state.nickname = result
                    st.session_state.student_id = login_id
                    st.rerun()
                else:
                    st.error(f"❌ {result}")
            else:
                st.warning("学籍番号とパスワードを入力してください")

    with auth_tab2:
        st.subheader("新規登録")
        reg_id = st.text_input("学籍番号", key="reg_id", placeholder="例：24P001")
        reg_nickname = st.text_input("ニックネーム（仮名）", key="reg_nickname", placeholder="例：A姓 佐藤")
        reg_pw = st.text_input("パスワード（6文字以上）", type="password", key="reg_pw")
        reg_pw2 = st.text_input("パスワード（確認）", type="password", key="reg_pw2")
        if st.button("登録する", type="primary", use_container_width=True, key="btn_register"):
            if not reg_id or not reg_nickname or not reg_pw or not reg_pw2:
                st.warning("すべての項目を入力してください")
            elif len(reg_pw) < 6:
                st.error("❌ パスワードは6文字以上で設定してください")
            elif reg_pw != reg_pw2:
                st.error("❌ パスワードが一致しません")
            else:
                ok, msg = register_user(reg_id, reg_nickname, reg_pw)
                if ok:
                    st.success("✅ 登録が完了しました。ログインタブからログインしてください。")
                else:
                    st.error(f"❌ {msg}")
    st.stop()

# ログイン済みの場合
nickname = st.session_state.nickname

# ログアウトボタン（サイドバー）
with st.sidebar:
    st.write(f"👤 **{nickname}** さん")
    st.write(f"🎓 学籍番号: {st.session_state.student_id}")
    if st.button("ログアウト", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.nickname = ""
        st.session_state.student_id = ""
        st.rerun()

# タブ切り替え
tab1, tab2 = st.tabs(["💬 質問する", "📝 練習問題"])

# タブ1: 質問
with tab1:
    st.markdown("<h1 style='white-space: nowrap;'>🎓 魔法の黒板 - 質問してみよう！</h1>", unsafe_allow_html=True)
    st.write(f"ようこそ、**{nickname}** さん！わからないことを気軽に質問してください。")
    st.markdown("---")
    
    # カテゴリー選択
    st.subheader("📂 どのカテゴリーについて質問しますか？")
    category = st.selectbox(
        "カテゴリー",
        ["すべて"] + categories,
        help="質問のカテゴリーを選択してください",
        label_visibility="collapsed"
    )
    
    # 質問入力
    st.subheader("❓ どんなことが知りたいですか？")
    question = st.text_area(
        "質問内容",
        height=150,
        placeholder="例：「生物統計について教えてください」「データの種類について、特に量的データと質的データの違いを知りたい」など、具体的に質問してください",
        label_visibility="collapsed"
    )
    
    if st.button("🔍 質問する", type="primary", use_container_width=True):
        if question:
            # NGワードチェック
            block_category, detected_word = check_inappropriate_content(question)
            
            if block_category:
                # 不適切な内容が検出された場合
                warning_msg = get_warning_message(block_category)
                st.error(warning_msg)
                
                # ブロックされたことをログに記録
                save_log(
                    nickname, 
                    "質問応答（ブロック）", 
                    question, 
                    warning_msg, 
                    category=category,
                    is_blocked=True,
                    block_reason=block_category
                )
            else:
                # 適切な質問の場合、通常通り処理
                # トライアスロンアニメーション表示
                progress_text = st.empty()
                progress_bar = st.progress(0)
                
                import time
                triathlon_stages = [
                    "🏊 泳いでいます...",
                    "🚴 自転車で走っています...",
                    "🏃 ランニング中..."
                ]
                
                for i, stage in enumerate(triathlon_stages):
                    progress_text.text(stage)
                    progress_bar.progress((i + 1) * 33)
                    time.sleep(0.3)
                
                progress_text.text("💭 AIが回答を考えています...")
                progress_bar.progress(100)
                
                # AIによるカテゴリー自動判定
                ai_categories = detect_categories_ai(question, categories)
                
                answer = answer_question(question, category)
                
                # プログレス表示をクリア
                progress_text.empty()
                progress_bar.empty()
                
                st.markdown("---")
                st.markdown("### 💡 回答")
                st.write(answer)
                
                # ログ保存（AIが判定したカテゴリーも含める）
                save_log(nickname, "質問応答", question, answer, 
                        category=category, ai_detected_categories=ai_categories)
                st.success("✅ 質問と回答を記録しました")
                
                # デバッグ用（開発時のみ表示、本番では削除可能）
                if ai_categories:
                    with st.expander("📊 分析情報（教員向け）"):
                        st.write(f"**選択カテゴリー**: {category}")
                        st.write(f"**AI判定カテゴリー**: {', '.join(ai_categories)}")
                        if category != "すべて" and category not in ai_categories:
                            st.warning("⚠️ 選択カテゴリーとAI判定が異なります")
        else:
            st.warning("⚠️ 質問を入力してください")

# タブ2: 練習問題
with tab2:
    st.markdown("<h1 style='white-space: nowrap;'>✏️ 魔法の黒板 - 問題を解いてみよう！</h1>", unsafe_allow_html=True)
    st.write(f"ようこそ、**{nickname}** さん！練習問題で理解度をチェックしましょう。")
    st.markdown("---")
    
    # トピック入力
    st.subheader("📚 どんな問題を解きたいですか？")
    topic = st.text_input(
        "トピック",
        placeholder="例：p値に関する質問、信頼区間に関する質問、バイアスに関する質問",
        label_visibility="collapsed"
    )
    
    # 難易度と問題数
    st.subheader("⚙️ 設定を選んでください")
    difficulty = st.selectbox(
        "📊 難易度",
        ["優しい", "普通", "難しい"],
        index=1
    )
    num_problems = st.selectbox(
        "🔢 問題数",
        [1, 2, 3],
        index=0
    )
    
    if st.button("✨ 問題を作る", type="primary", use_container_width=True):
        if topic:
            # NGワードチェック
            block_category, detected_word = check_inappropriate_content(topic)
            
            if block_category:
                # 不適切な内容が検出された場合
                warning_msg = get_warning_message(block_category)
                st.error(warning_msg)
                
                # ブロックされたことをログに記録
                save_log(
                    nickname, 
                    "練習問題（ブロック）", 
                    topic, 
                    warning_msg,
                    difficulty=difficulty,
                    num_problems=num_problems,
                    is_blocked=True,
                    block_reason=block_category
                )
            else:
                # 適切なトピックの場合、通常通り処理
                # トライアスロンアニメーション表示
                progress_text = st.empty()
                progress_bar = st.progress(0)
                
                import time
                triathlon_stages = [
                    "🏊 泳いでいます...",
                    "🚴 自転車で走っています...",
                    "🏃 ランニング中..."
                ]
                
                for i, stage in enumerate(triathlon_stages):
                    progress_text.text(stage)
                    progress_bar.progress((i + 1) * 33)
                    time.sleep(0.3)
                
                progress_text.text("💭 問題を作っています...")
                progress_bar.progress(100)
                
                # AIによるカテゴリー自動判定
                ai_categories = detect_categories_ai(topic, categories)
                
                problem_text = generate_practice_problem(topic, difficulty, num_problems)
                problems = parse_problem(problem_text)
                
                # プログレス表示をクリア
                progress_text.empty()
                progress_bar.empty()
                
                # セッションステートを完全にリセット
                st.session_state.problems = problems
                st.session_state.user_answers = [[] for _ in problems]
                st.session_state.show_results = [False for _ in problems]
                st.session_state.show_explanation = [False for _ in problems]
                st.session_state.problem_version = st.session_state.get('problem_version', 0) + 1  # バージョンを更新
                
                # ログ保存（AIが判定したカテゴリーも含める）
                save_log(nickname, "練習問題", topic, problem_text, 
                        difficulty=difficulty, num_problems=num_problems,
                        ai_detected_categories=ai_categories)
        else:
            st.warning("⚠️ トピックを入力してください")
    
    # 生成された問題を表示
    if 'problems' in st.session_state and st.session_state.problems:
        st.markdown("---")
        
        for idx, problem in enumerate(st.session_state.problems):
            st.markdown(f"### 📋 問題 {idx + 1}")
            st.write(problem['question'])
            
            st.markdown("")  # 空行追加
            
            # 選択肢（チェックボックス）
            selected = []
            version = st.session_state.get('problem_version', 0)
            
            # 選択肢が5つ未満の場合はエラー表示
            if len(problem['choices']) != 5:
                st.error(f"⚠️ 選択肢が{len(problem['choices'])}個です。正しく生成されませんでした。")
                continue
            
            # 選択肢を表示（モバイル対応：シンプルな表示）
            for i in range(5):
                if i < len(problem['choices']):
                    # 番号と選択肢を1行で表示
                    choice_label = f"{i+1}. {problem['choices'][i]}"
                    if st.checkbox(choice_label, key=f"choice_v{version}_{idx}_{i}", label_visibility="visible"):
                        selected.append(i + 1)
            
            st.markdown("")  # 空行追加
            
            # 選択した答えを保存
            st.session_state.user_answers[idx] = selected
            
            # 解答を確認ボタン
            version = st.session_state.get('problem_version', 0)
            if st.button(f"✓ 解答を確認", key=f"check_v{version}_{idx}", use_container_width=True):
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
                
                # 解説表示ボタン（縦並び）
                if st.button(f"📖 解答と解説を見る", key=f"explain_v{version}_{idx}", use_container_width=True):
                    st.session_state.show_explanation[idx] = True
            
            # 解説表示
            if st.session_state.show_explanation[idx]:
                st.markdown("---")
                st.markdown("### 📖 解説")
                # 解説を改行を保持して表示
                explanation_text = problem['explanation']
                
                # 【正解の解説】と【誤りの解説】の前に改行を追加
                explanation_text = explanation_text.replace('【正解の解説】', '\n\n【正解の解説】')
                explanation_text = explanation_text.replace('【誤りの解説】', '\n\n【誤りの解説】')
                
                # 表示
                st.markdown(explanation_text)
            
            st.markdown("---")

# フッター
st.markdown("---")
st.caption(f"💡 使用中のAI: {DEFAULT_API}")
st.caption("⚠️ 不適切な質問や授業と無関係な質問には回答できません")
