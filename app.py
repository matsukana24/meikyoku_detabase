
import json
import os
import re
import sqlite3
import hashlib
import hmac
import secrets
import streamlit as st

st.set_page_config(
    page_title="メイキョク就活・進路データベース",
    layout="wide"
)

# ==========================================
# 0. 設定
# ==========================================

DB_FILE = os.environ.get("DB_FILE", "database.db")
PRIMARY_ADMIN = "lil_3316"

GENERATIONS = [
    "1〜2期生", "3期生", "4期生", "5期生",
    "6期生", "7期生", "8期生", "9期生", "10期生+"
]

GRAD_YEARS = [
    f"{year}年" for year in range(2020, 2033)
] + ["その他 / 既卒"]

ROLE_OPTIONS = [
    "代表", "副代表", "営業", "イベント企画",
    "SNS", "開発", "記事"
]

CAREER_PATHS = ["就職", "進学", "起業"]

CAREER_FIELDS = {
    "就職": {
        "company_joined": "入社先",
        "offers": "内定先",
        "internships": "インターン先",
        "target_industry": "志望業界",
        "target_occupation": "志望職種",
        "axis_real": "就活の軸（本音）",
        "axis_official": "就活の軸（建前）",
        "decision_reason": "入社先決定理由",
        "tips_self": "自己分析Tips",
        "tips_es": "ES Tips",
        "tips_interview": "面接Tips",
        "pr_text": "自己PR",
        "motivation_text": "志望動機",
        "gakuchika": "メイキョクでのガクチカ",
    },
    "進学": {
        "grad_school": "進学先",
        "grad_choice_reason": "進学先選びで留意したこと",
        "grad_advice": "進学のアドバイス",
    },
    "起業": {
        "startup_name": "起業企業名",
        "startup_industry": "起業の業界",
        "startup_reason": "起業理由",
    },
}


def load_css(filename):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            st.markdown(
                f"<style>{file.read()}</style>",
                unsafe_allow_html=True
            )
    except FileNotFoundError:
        pass


load_css("style.css")


def get_connection():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


# ==========================================
# 1. パスワード処理
# ==========================================

def hash_password(password):
    salt = secrets.token_bytes(16)
    iterations = 600000

    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations
    )

    return (
        f"pbkdf2_sha256${iterations}$"
        f"{salt.hex()}${hashed.hex()}"
    )


def verify_password(password, stored):
    if not stored:
        return False

    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt, hashed = stored.split("$")

            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(salt),
                int(iterations)
            )

            return hmac.compare_digest(
                actual,
                bytes.fromhex(hashed)
            )
        except (ValueError, TypeError):
            return False

    # 旧バージョンの平文パスワードにも対応
    return hmac.compare_digest(password, stored)


# ==========================================
# 2. データベース初期化
# ==========================================

def init_db():
    with get_connection() as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                name TEXT NOT NULL,
                penname TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS records (
                owner_username TEXT PRIMARY KEY,
                name TEXT,
                penname TEXT,
                discord TEXT,
                generation TEXT,
                phone TEXT,
                instagram TEXT,
                grad_year TEXT,
                meikyoku_roles TEXT,
                career_path TEXT,
                status TEXT,
                data_json TEXT,
                FOREIGN KEY(owner_username)
                    REFERENCES users(username)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asker_name TEXT,
                content TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER,
                username TEXT,
                name TEXT,
                is_anonymous INTEGER,
                content TEXT,
                FOREIGN KEY(question_id)
                    REFERENCES questions(id)
            )
        """)

        # 古いデータベースへの対応
        columns = [
            row["name"]
            for row in c.execute(
                "PRAGMA table_info(records)"
            ).fetchall()
        ]

        if "generation" not in columns:
            c.execute(
                "ALTER TABLE records ADD COLUMN generation TEXT"
            )

        # 既存の管理者アカウントに権限を付与
        # パスワードは変更しない
        c.execute("""
            UPDATE users
            SET role = 'admin', status = 'active'
            WHERE username = ?
        """, (PRIMARY_ADMIN,))

        # 初期管理者が存在しない場合のみ新規作成
        # パスワードはRenderの環境変数から取得
        existing = c.execute(
            "SELECT username FROM users WHERE username = ?",
            (PRIMARY_ADMIN,)
        ).fetchone()

        initial_password = os.environ.get(
            "ADMIN_INITIAL_PASSWORD", ""
        )

        if existing is None and initial_password:
            c.execute("""
                INSERT INTO users
                (username, password, name, penname, role, status)
                VALUES (?, ?, ?, ?, 'admin', 'active')
            """, (
                PRIMARY_ADMIN,
                hash_password(initial_password),
                "松田夏奈",
                "まつかな"
            ))

        conn.commit()


init_db()


# ==========================================
# 3. データベース操作
# ==========================================

def get_user(username):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        return dict(row) if row else None


def get_all_users():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY username"
        ).fetchall()

        return [dict(row) for row in rows]


def add_user(username, password, name, penname):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO users
            (username, password, name, penname, role, status)
            VALUES (?, ?, ?, ?, 'member', 'active')
        """, (
            username,
            hash_password(password),
            name,
            penname
        ))
        conn.commit()


def update_user_password(username, password):
    with get_connection() as conn:
        conn.execute("""
            UPDATE users
            SET password = ?
            WHERE username = ?
        """, (
            hash_password(password),
            username
        ))
        conn.commit()


def update_user_role(username, role):
    if username == PRIMARY_ADMIN:
        return

    if role not in ("admin", "member"):
        return

    with get_connection() as conn:
        conn.execute("""
            UPDATE users SET role = ?
            WHERE username = ?
        """, (role, username))
        conn.commit()


def update_user_status(username, status):
    if username == PRIMARY_ADMIN:
        return

    if status not in ("active", "banned"):
        return

    with get_connection() as conn:
        conn.execute("""
            UPDATE users SET status = ?
            WHERE username = ?
        """, (status, username))
        conn.commit()


def update_user_basic(username, name, penname):
    with get_connection() as conn:
        conn.execute("""
            UPDATE users
            SET name = ?, penname = ?
            WHERE username = ?
        """, (name, penname, username))
        conn.commit()


def save_user_record(username, record):
    data_json = json.dumps(
        record,
        ensure_ascii=False
    )

    roles = ",".join(
        record.get("meikyoku_roles", [])
    )

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO records (
                owner_username, name, penname,
                discord, generation, phone, instagram,
                grad_year, meikyoku_roles,
                career_path, status, data_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_username) DO UPDATE SET
                name = excluded.name,
                penname = excluded.penname,
                discord = excluded.discord,
                generation = excluded.generation,
                phone = excluded.phone,
                instagram = excluded.instagram,
                grad_year = excluded.grad_year,
                meikyoku_roles = excluded.meikyoku_roles,
                career_path = excluded.career_path,
                status = excluded.status,
                data_json = excluded.data_json
        """, (
            username,
            record.get("name"),
            record.get("penname"),
            record.get("discord"),
            record.get("generation"),
            record.get("phone"),
            record.get("instagram"),
            record.get("grad_year"),
            roles,
            record.get("career_path"),
            record.get("status"),
            data_json
        ))
        conn.commit()


def get_record_by_username(username):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT data_json FROM records
            WHERE owner_username = ?
        """, (username,)).fetchone()

        if row:
            return json.loads(row["data_json"])

        return None


def get_published_records():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT data_json FROM records
            WHERE status = 'published'
        """).fetchall()

        return [
            json.loads(row["data_json"])
            for row in rows
        ]


def add_question(asker_name, content):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO questions (asker_name, content)
            VALUES (?, ?)
        """, (asker_name, content))
        conn.commit()


def add_answer(
    question_id, username, name,
    is_anonymous, content
):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO answers (
                question_id, username, name,
                is_anonymous, content
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            question_id,
            username,
            name,
            int(is_anonymous),
            content
        ))
        conn.commit()


def get_questions_and_answers():
    with get_connection() as conn:
        questions = conn.execute("""
            SELECT * FROM questions
            ORDER BY id DESC
        """).fetchall()

        result = []

        for question in questions:
            item = dict(question)

            answers = conn.execute("""
                SELECT * FROM answers
                WHERE question_id = ?
                ORDER BY id ASC
            """, (item["id"],)).fetchall()

            item["answers"] = [
                dict(answer) for answer in answers
            ]

            result.append(item)

        return result


# ==========================================
# 4. 共通処理
# ==========================================

def selected_index(options, value, default=0):
    if value in options:
        return options.index(value)
    return default


def get_gen_sort_key(generation):
    numbers = re.findall(
        r"\d+",
        generation or ""
    )
    return int(numbers[0]) if numbers else 999


def is_graduated_generation(generation):
    if not generation:
        return False

    return get_gen_sort_key(generation) <= 5


def get_record_value(record, key, default=""):
    value = record.get(key, default)
    return default if value is None else value


# ==========================================
# 5. セッション管理
# ==========================================

if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

if "active_tab" not in st.session_state:
    st.session_state.active_tab = "📋 登録情報一覧（トップ）"


# ==========================================
# 6. ログイン・新規登録
# ==========================================

if st.session_state.logged_in_user is None:

    st.title("🎓 メイキョク 就活・進路データベース")
    st.write(
        "サークルメンバー限定サイトです。"
        "ログインまたは新規登録してください。"
    )

    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        login_tab, signup_tab = st.tabs([
            "🔑 ログイン",
            "✨ 新規ユーザー登録"
        ])

        with login_tab:
            with st.form("login_form"):
                st.subheader("ログイン")

                username = st.text_input(
                    "Discord ID（ユーザー名）"
                )

                password = st.text_input(
                    "パスワード",
                    type="password"
                )

                submitted = st.form_submit_button(
                    "ログインする",
                    type="primary",
                    use_container_width=True
                )

                if submitted:
                    account = get_user(username.strip())

                    if (
                        account
                        and verify_password(
                            password,
                            account["password"]
                        )
                    ):
                        if account["status"] == "banned":
                            st.error(
                                "このアカウントは利用停止中です。"
                            )
                        else:
                            # 旧パスワードを安全な形式に更新
                            if not account["password"].startswith(
                                "pbkdf2_sha256$"
                            ):
                                update_user_password(
                                    account["username"],
                                    password
                                )

                            st.session_state.logged_in_user = {
                                "username": account["username"],
                                "name": account["name"],
                                "penname": account["penname"],
                                "role": account["role"]
                            }

                            st.rerun()
                    else:
                        st.error(
                            "ユーザー名またはパスワードが違います。"
                        )

        with signup_tab:
            with st.form("signup_form"):
                st.subheader("新規アカウント作成")

                new_username = st.text_input(
                    "Discord ID *"
                )

                new_password = st.text_input(
                    "パスワード *",
                    type="password"
                )

                new_confirm = st.text_input(
                    "パスワード（確認用）*",
                    type="password"
                )

                st.markdown("---")

                new_name = st.text_input(
                    "名前（本名）*"
                )

                new_penname = st.text_input(
                    "メイキョクネーム *"
                )

                new_generation = st.selectbox(
                    "何期生か *",
                    GENERATIONS,
                    index=3
                )

                new_grad_year = st.selectbox(
                    "卒業年度 *",
                    GRAD_YEARS,
                    index=5
                )

                new_roles = st.multiselect(
                    "メイキョクでの役割・業務 *",
                    ROLE_OPTIONS
                )

                new_career = st.radio(
                    "卒業後の進路 *",
                    CAREER_PATHS
                )

                submitted = st.form_submit_button(
                    "登録してログインする",
                    type="primary",
                    use_container_width=True
                )

                if submitted:
                    new_username = new_username.strip()
                    new_name = new_name.strip()
                    new_penname = new_penname.strip()

                    if not all([
                        new_username,
                        new_password,
                        new_name,
                        new_penname,
                        new_roles
                    ]):
                        st.error(
                            "必須項目をすべて入力してください。"
                        )

                    elif new_username == PRIMARY_ADMIN:
                        st.error(
                            "このIDは使用できません。"
                        )

                    elif get_user(new_username):
                        st.error(
                            "このDiscord IDは登録済みです。"
                        )

                    elif new_password != new_confirm:
                        st.error(
                            "パスワードが一致しません。"
                        )

                    else:
                        add_user(
                            new_username,
                            new_password,
                            new_name,
                            new_penname
                        )

                        initial_record = {
                            "owner_username": new_username,
                            "name": new_name,
                            "penname": new_penname,
                            "discord": new_username,
                            "generation": new_generation,
                            "phone": "",
                            "instagram": "",
                            "grad_year": new_grad_year,
                            "meikyoku_roles": new_roles,
                            "career_path": new_career,
                            "status": "draft"
                        }

                        save_user_record(
                            new_username,
                            initial_record
                        )

                        st.session_state.logged_in_user = {
                            "username": new_username,
                            "name": new_name,
                            "penname": new_penname,
                            "role": "member"
                        }

                        st.rerun()

    st.stop()


# ==========================================
# 7. ログイン後の権限確認
# ==========================================

session_user = st.session_state.logged_in_user
user = get_user(session_user["username"])

if not user or user["status"] != "active":
    st.session_state.logged_in_user = None
    st.rerun()

# データベースの最新権限を使用
st.session_state.logged_in_user.update({
    "name": user["name"],
    "penname": user["penname"],
    "role": user["role"]
})

is_admin = user["role"] == "admin"


# ==========================================
# 8. プロフィール詳細ダイアログ
# ==========================================

@st.dialog("👤 メンバー詳細プロフィール")
def show_user_profile(target_username):

    record = get_record_by_username(target_username)

    if not record or record.get("status") != "published":
        st.warning("プロフィールは未公開です。")
        return

    st.subheader(
        f"{record.get('name', '')}"
        f"（{record.get('penname', '')}）"
    )

    st.write(
        f"**期生:** {record.get('generation', '-')} | "
        f"**卒業年:** {record.get('grad_year', '-')} | "
        f"**進路:** {record.get('career_path', '-')}"
    )

    roles = ", ".join(
        record.get("meikyoku_roles", [])
    )

    st.write(f"**メイキョクでの役割:** {roles}")

    st.write(
        f"**Discord:** {record.get('discord', '-')} | "
        f"**電話:** {record.get('phone', '-')} | "
        f"**Instagram:** {record.get('instagram', '-')}"
    )

    st.markdown("---")

    path = record.get("career_path", "")

    for key, label in CAREER_FIELDS.get(path, {}).items():
        st.write(
            f"**{label}:** "
            f"{record.get(key) or '未記入'}"
        )


# ==========================================
# 9. 管理者専用ダイアログ
# ==========================================

@st.dialog("🔑 パスワード変更")
def show_password_change_dialog(target_username):

    if not is_admin:
        st.error("管理者のみ操作できます。")
        return

    st.write(f"対象ID：`{target_username}`")

    with st.form(f"password_{target_username}"):
        password = st.text_input(
            "新しいパスワード",
            type="password"
        )

        confirm = st.text_input(
            "確認用パスワード",
            type="password"
        )

        submitted = st.form_submit_button(
            "変更する",
            type="primary"
        )

        if submitted:
            if not password:
                st.error("パスワードを入力してください。")
            elif password != confirm:
                st.error("パスワードが一致しません。")
            else:
                update_user_password(
                    target_username,
                    password
                )
                st.success("パスワードを変更しました。")


# ==========================================
# 10. 共通プロフィール編集フォーム
# ==========================================

def render_profile_form(
    target_username,
    target_user,
    record,
    form_key,
    administrator=False
):
    record = record or {}

    def value(key, default=""):
        return get_record_value(record, key, default)

    st.caption(f"対象ユーザー：{target_username}")

    with st.form(form_key):

        st.markdown("### 1. 基本情報")

        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input(
                "名前（本名）*",
                value=value(
                    "name",
                    target_user["name"]
                )
            )

        with col2:
            penname = st.text_input(
                "メイキョクネーム *",
                value=value(
                    "penname",
                    target_user["penname"]
                )
            )

        col1, col2, col3 = st.columns(3)

        with col1:
            discord = st.text_input(
                "Discord ID（プロフィール表示用）",
                value=value(
                    "discord",
                    target_username
                )
            )

        with col2:
            generation = st.selectbox(
                "何期生か *",
                GENERATIONS,
                index=selected_index(
                    GENERATIONS,
                    value("generation", "5期生"),
                    3
                )
            )

        with col3:
            phone = st.text_input(
                "電話番号",
                value=value("phone")
            )

        instagram = st.text_input(
            "Instagram ID",
            value=value("instagram")
        )

        grad_year = st.selectbox(
            "卒業年 *",
            GRAD_YEARS,
            index=selected_index(
                GRAD_YEARS,
                value("grad_year", "2025年"),
                5
            )
        )

        previous_roles = value(
            "meikyoku_roles", []
        )

        if not isinstance(previous_roles, list):
            previous_roles = []

        roles = st.multiselect(
            "メイキョクでの業務内容 *",
            ROLE_OPTIONS,
            default=[
                role for role in previous_roles
                if role in ROLE_OPTIONS
            ]
        )

        st.markdown("---")
        st.markdown("### 2. 進路と詳細情報")

        career_path = st.radio(
            "卒業後の進路 *",
            CAREER_PATHS,
            index=selected_index(
                CAREER_PATHS,
                value("career_path", "就職")
            )
        )

        # 進路変更前の情報も保持
        form_data = {}

        for key, label in CAREER_FIELDS[
            career_path
        ].items():

            form_data[key] = st.text_area(
                label,
                value=value(key)
            )

        st.markdown("---")

        if administrator:
            status = st.selectbox(
                "公開状態",
                ["draft", "published"],
                index=(
                    1 if value("status") == "published"
                    else 0
                ),
                format_func=lambda x: (
                    "🟢 公開" if x == "published"
                    else "🟡 下書き"
                )
            )

            submitted = st.form_submit_button(
                "💾 変更を保存する",
                type="primary",
                use_container_width=True
            )

        else:
            col1, col2 = st.columns(2)

            with col1:
                save_draft = st.form_submit_button(
                    "💾 下書き保存する",
                    use_container_width=True
                )

            with col2:
                publish = st.form_submit_button(
                    "🚀 公開して保存する",
                    type="primary",
                    use_container_width=True
                )

            submitted = save_draft or publish
            status = "published" if publish else "draft"

        if submitted:

            if not name.strip() or not penname.strip():
                st.error(
                    "名前とメイキョクネームは必須です。"
                )
                return

            if not roles:
                st.error(
                    "メイキョクでの業務内容を選択してください。"
                )
                return

            updated = dict(record)

            updated.update({
                "owner_username": target_username,
                "name": name.strip(),
                "penname": penname.strip(),
                "discord": discord,
                "generation": generation,
                "phone": phone,
                "instagram": instagram,
                "grad_year": grad_year,
                "meikyoku_roles": roles,
                "career_path": career_path,
                "status": status
            })

            updated.update(form_data)

            # 基本情報とプロフィールを更新
            update_user_basic(
                target_username,
                name.strip(),
                penname.strip()
            )

            save_user_record(
                target_username,
                updated
            )

            if target_username == user["username"]:
                st.session_state.logged_in_user.update({
                    "name": name.strip(),
                    "penname": penname.strip()
                })

            st.success("情報を保存しました！")
            st.rerun()


@st.dialog("✏️ メンバー情報編集")
def show_member_edit_dialog(target_username):

    if not is_admin:
        st.error("管理者のみ操作できます。")
        return

    target_user = get_user(target_username)

    if not target_user:
        st.error("ユーザーが見つかりません。")
        return

    record = get_record_by_username(
        target_username
    )

    render_profile_form(
        target_username,
        target_user,
        record,
        f"admin_edit_{target_username}",
        administrator=True
    )


# ==========================================
# 11. メイン画面ヘッダー
# ==========================================

col1, col2 = st.columns([3, 1])

with col1:
    st.title("🎓 メイキョク 就活・進路データベース")

    st.write(
        f"ログイン中：**{user['name']}**"
        f"（{user['penname']}）"
    )

    if is_admin:
        st.caption("👑 管理者アカウント")

with col2:
    if st.button(
        "🚪 ログアウト",
        use_container_width=True
    ):
        st.session_state.logged_in_user = None
        st.rerun()


# ==========================================
# 12. タブ切り替え
# ==========================================

tab_names = [
    "📋 登録情報一覧（トップ）",
    "📝 自分の情報登録・編集",
    "💬 質問箱"
]

if is_admin:
    tab_names.append("⚙️ 管理者画面")

selected_tab = st.radio(
    "メニュー切り替え",
    tab_names,
    index=selected_index(
        tab_names,
        st.session_state.active_tab
    ),
    horizontal=True,
    label_visibility="collapsed"
)

st.session_state.active_tab = selected_tab


# ==========================================
# 13. メンバーカード表示
# ==========================================

def render_member_card(item):

    generation = item.get(
        "generation", "期生不明"
    )

    name = item.get("name", "名前未登録")
    penname = item.get("penname", "未設定")
    grad_year = item.get("grad_year", "未設定")
    career_path = item.get("career_path", "未設定")

    title = (
        f"👤 [{generation}] {name} / "
        f"{penname}（{grad_year}卒 / {career_path}）"
    )

    with st.expander(title):

        st.write(
            f"**本名:** {name} | "
            f"**メイキョクネーム:** {penname}"
        )

        roles = ", ".join(
            item.get("meikyoku_roles", [])
        )

        st.write(
            f"**メイキョクでの役職・業務:** "
            f"{roles or '未登録'}"
        )

        st.write(
            f"**Discord:** {item.get('discord', '-')} | "
            f"**電話:** {item.get('phone', '-')} | "
            f"**Instagram:** {item.get('instagram', '-')}"
        )

        st.markdown("---")

        fields = CAREER_FIELDS.get(
            career_path, {}
        )

        for key, label in fields.items():
            content = item.get(key) or "未記入"

            if key in (
                "pr_text",
                "motivation_text",
                "gakuchika"
            ):
                continue

            st.write(f"**{label}:** {content}")

        if career_path == "就職":
            with st.expander(
                "📄 自己PR・志望動機・ガクチカを見る"
            ):
                for key in (
                    "pr_text",
                    "motivation_text",
                    "gakuchika"
                ):
                    label = fields[key]
                    st.write(f"**【{label}】**")
                    st.write(item.get(key) or "未記入")


# ==========================================
# 14. 登録情報一覧
# ==========================================

if selected_tab == "📋 登録情報一覧（トップ）":

    st.subheader(
        "🔍 登録情報の一覧・絞り込み検索"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        keyword = st.text_input(
            "キーワード検索（名前・企業名など）"
        )

    with col2:
        filter_path = st.selectbox(
            "進路で絞り込み",
            ["すべて"] + CAREER_PATHS
        )

    with col3:
        filter_year = st.selectbox(
            "卒業年で絞り込み",
            ["すべて"] + GRAD_YEARS
        )

    records = get_published_records()

    filtered = []

    for record in records:

        if (
            filter_path != "すべて"
            and record.get("career_path") != filter_path
        ):
            continue

        if (
            filter_year != "すべて"
            and record.get("grad_year") != filter_year
        ):
            continue

        if (
            keyword
            and keyword.lower()
            not in str(record).lower()
        ):
            continue

        filtered.append(record)

    filtered.sort(
        key=lambda item: get_gen_sort_key(
            item.get("generation")
        )
    )

    st.write(f"該当件数：**{len(filtered)}件**")

    st.markdown("---")

    graduated = [
        item for item in filtered
        if is_graduated_generation(
            item.get("generation")
        )
    ]

    current = [
        item for item in filtered
        if not is_graduated_generation(
            item.get("generation")
        )
    ]

    tab1, tab2 = st.tabs([
        f"🎓 卒業メンバー（{len(graduated)}件）",
        f"🏫 現役メンバー（{len(current)}件）"
    ])

    with tab1:
        if graduated:
            for item in graduated:
                render_member_card(item)
        else:
            st.info("該当する卒業メンバーはいません。")

    with tab2:
        if current:
            for item in current:
                render_member_card(item)
        else:
            st.info("該当する現役メンバーはいません。")


# ==========================================
# 15. 自分の情報登録・編集
# ==========================================

elif selected_tab == "📝 自分の情報登録・編集":

    st.subheader(
        "📝 自身の就活・進路情報の登録・編集"
    )

    my_record = get_record_by_username(
        user["username"]
    )

    if my_record:
        status = my_record.get("status")

        if status == "published":
            st.info("現在のステータス：🟢 公開中")
        else:
            st.info("現在のステータス：🟡 下書き")

    render_profile_form(
        user["username"],
        user,
        my_record,
        "my_profile_form"
    )


# ==========================================
# 16. 質問箱
# ==========================================

elif selected_tab == "💬 質問箱":

    st.subheader("💬 質問箱（Q&Aボード）")

    st.write(
        "就活や進路についての疑問を投稿したり、"
        "先輩や仲間からの回答を確認できます。"
    )

    with st.container(border=True):

        st.markdown("#### ✍️ 新しい質問を投稿する")

        with st.form("new_question_form"):

            question_text = st.text_area(
                "質問内容",
                placeholder=(
                    "例：インターンで評価される"
                    "ポイントを教えてください！"
                )
            )

            col1, col2 = st.columns([3, 1])

            with col1:
                anonymous = st.checkbox(
                    "匿名で質問を投稿する",
                    value=True
                )

            with col2:
                submitted = st.form_submit_button(
                    "質問を送信",
                    type="primary",
                    use_container_width=True
                )

            if submitted:

                if not question_text.strip():
                    st.error("質問を入力してください。")

                else:
                    asker = (
                        "匿名希望"
                        if anonymous
                        else (
                            f"{user['name']} "
                            f"({user['penname']})"
                        )
                    )

                    add_question(
                        asker,
                        question_text.strip()
                    )

                    st.rerun()

    st.markdown("---")
    st.markdown("### 📬 質問＆回答一覧")

    questions = get_questions_and_answers()

    if not questions:
        st.info(
            "現在、投稿された質問はありません。"
        )

    for question in questions:

        with st.container(border=True):

            st.markdown(
                f"### ❓ {question['content']}"
            )

            st.caption(
                f"投稿者：{question['asker_name']}"
            )

            answers = question["answers"]

            if answers:
                st.markdown(
                    f"**💬 回答（{len(answers)}件）**"
                )

                for answer in answers:

                    col1, col2 = st.columns([2, 8])

                    with col1:

                        if answer["is_anonymous"]:
                            st.write("👤 匿名回答")

                        else:
                            if st.button(
                                f"👤 {answer['name']}",
                                key=f"answer_user_{answer['id']}"
                            ):
                                show_user_profile(
                                    answer["username"]
                                )

                    with col2:
                        st.info(answer["content"])

            else:
                st.caption(
                    "まだ回答はありません。"
                )

            with st.expander(
                "✏️ この質問に回答する"
            ):

                with st.form(
                    f"answer_form_{question['id']}"
                ):

                    answer_text = st.text_area(
                        "回答を入力",
                        placeholder=(
                            "経験やアドバイスを"
                            "教えてください"
                        )
                    )

                    anonymous_answer = st.checkbox(
                        "匿名で回答する"
                    )

                    submitted = st.form_submit_button(
                        "回答を送信",
                        use_container_width=True
                    )

                    if submitted:

                        if not answer_text.strip():
                            st.error(
                                "回答を入力してください。"
                            )

                        else:
                            add_answer(
                                question["id"],
                                user["username"],
                                (
                                    f"{user['name']} "
                                    f"({user['penname']})"
                                ),
                                anonymous_answer,
                                answer_text.strip()
                            )

                            st.rerun()


# ==========================================
# 17. 管理者画面
# ==========================================

elif selected_tab == "⚙️ 管理者画面":

    # 表示だけでなく、操作前にも権限を確認
    if not is_admin:
        st.error("管理者権限がありません。")
        st.stop()

    st.subheader("⚙️ 管理者画面")

    st.write(
        "メンバー情報・パスワード・権限・"
        "アクセス状態を管理できます。"
    )

    users = get_all_users()

    st.metric(
        "登録ユーザー数",
        len(users)
    )

    st.markdown("---")

    search = st.text_input(
        "🔍 メンバー検索",
        placeholder="名前・メイキョクネーム・Discord ID"
    )

    for target in users:

        target_username = target["username"]

        if search:
            search_text = (
                target["username"]
                + target["name"]
                + target["penname"]
            ).lower()

            if search.lower() not in search_text:
                continue

        is_primary = (
            target_username == PRIMARY_ADMIN
        )

        title = (
            f"👤 {target['name']} "
            f"（{target['penname']}）"
            f" / {target_username}"
        )

        if is_primary:
            title += " 👑"

        with st.expander(title):

            st.write(
                f"**Discord ID:** `{target_username}`"
            )

            st.write(
                "**現在の権限:** "
                + (
                    "管理者"
                    if target["role"] == "admin"
                    else "一般メンバー"
                )
            )

            st.write(
                "**アクセス状態:** "
                + (
                    "🟢 許可"
                    if target["status"] == "active"
                    else "🔴 ブロック"
                )
            )

            st.markdown("---")

            col1, col2 = st.columns(2)

            with col1:

                if st.button(
                    "✏️ 情報編集",
                    key=f"edit_{target_username}",
                    use_container_width=True
                ):
                    show_member_edit_dialog(
                        target_username
                    )

            with col2:

                if st.button(
                    "🔑 パスワード変更",
                    key=f"password_{target_username}",
                    use_container_width=True
                ):
                    show_password_change_dialog(
                        target_username
                    )

            st.markdown("---")

            if is_primary:
                st.info(
                    "👑 このアカウントは固定管理者です。"
                    "管理者権限とアクセス許可は保護されています。"
                )

            else:
                col1, col2 = st.columns(2)

                with col1:
                    new_role = st.selectbox(
                        "ユーザー権限",
                        ["admin", "member"],
                        index=selected_index(
                            ["admin", "member"],
                            target["role"]
                        ),
                        format_func=lambda role: (
                            "👑 管理者"
                            if role == "admin"
                            else "👤 一般メンバー"
                        ),
                        key=f"role_{target_username}"
                    )

                    if st.button(
                        "権限を保存",
                        key=f"save_role_{target_username}"
                    ):
                        update_user_role(
                            target_username,
                            new_role
                        )
                        st.success("権限を変更しました。")
                        st.rerun()

                with col2:
                    if target["status"] == "active":

                        if st.button(
                            "🚫 ブロックする",
                            key=f"ban_{target_username}",
                            use_container_width=True
                        ):
                            update_user_status(
                                target_username,
                                "banned"
                            )
                            st.rerun()

                    else:

                        if st.button(
                            "⭕ ブロック解除",
                            key=f"unban_{target_username}",
                            use_container_width=True
                        ):
                            update_user_status(
                                target_username,
                                "active"
                            )
                            st.rerun()
