
import json
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

DB_FILE = "database.db"
ADMIN_ID = "admin"
ADMIN_INITIAL_PASSWORD = "admin1020"

GENERATIONS = [
    "1〜2期生", "3期生", "4期生", "5期生",
    "6期生", "7期生", "8期生", "9期生", "10期生+"
]
YEARS = [f"{y}年" for y in range(2020, 2033)] + ["その他 / 既卒"]
ROLES = ["代表", "副代表", "営業", "イベント企画", "SNS", "開発", "記事"]
PATHS = ["就職", "進学", "起業"]

DETAIL_FIELDS = {
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
        "gakuchika": "メイキョクでのガクチカ"
    },
    "進学": {
        "grad_school": "進学先",
        "grad_choice_reason": "進学先選びで留意したこと",
        "grad_advice": "進学のアドバイス"
    },
    "起業": {
        "startup_name": "起業企業名",
        "startup_industry": "起業の業界",
        "startup_reason": "起業理由"
    }
}


# ==========================================
# CSS
# ==========================================

try:
    with open("style.css", encoding="utf-8") as f:
        st.markdown(
            f"<style>{f.read()}</style>",
            unsafe_allow_html=True
        )
except FileNotFoundError:
    pass


# ==========================================
# パスワード
# ==========================================

def hash_password(password):
    salt = secrets.token_bytes(16)
    iterations = 600000
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, iterations
    )
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    if not stored:
        return False

    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, count, salt, digest = stored.split("$")
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(),
                bytes.fromhex(salt),
                int(count)
            )
            return hmac.compare_digest(actual, bytes.fromhex(digest))
        except (ValueError, TypeError):
            return False

    # 旧データベースの平文パスワードとの互換性
    return hmac.compare_digest(password, stored)


# ==========================================
# データベース
# ==========================================

def get_connection():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def delete_account(conn, username):
    conn.execute(
        "DELETE FROM answers WHERE username = ?",
        (username,)
    )
    conn.execute(
        "DELETE FROM records WHERE owner_username = ?",
        (username,)
    )
    conn.execute(
        "DELETE FROM users WHERE username = ?",
        (username,)
    )


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                name TEXT NOT NULL,
                penname TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)

        conn.execute("""
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
                data_json TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asker_name TEXT,
                content TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER,
                username TEXT,
                name TEXT,
                is_anonymous INTEGER,
                content TEXT
            )
        """)

        columns = [
            row["name"] for row in
            conn.execute("PRAGMA table_info(records)").fetchall()
        ]

        if "generation" not in columns:
            conn.execute(
                "ALTER TABLE records ADD COLUMN generation TEXT"
            )

        # 旧管理者とテストユーザーを一度だけ削除
        # 山田はIDがyamadaの場合のみ削除する
        for username in ("lil_3316", "aaaa", "yamada"):
            delete_account(conn, username)

        # adminがまだ存在しない場合に新規作成
        existing = conn.execute(
            "SELECT username FROM users WHERE username = ?",
            (ADMIN_ID,)
        ).fetchone()

        if existing is None:
            conn.execute("""
                INSERT INTO users
                (username, password, name, penname, role, status)
                VALUES (?, ?, ?, ?, 'admin', 'active')
            """, (
                ADMIN_ID,
                hash_password(ADMIN_INITIAL_PASSWORD),
                "管理者",
                "管理者"
            ))
        else:
            # パスワードは変更しない
            conn.execute("""
                UPDATE users
                SET role = 'admin', status = 'active'
                WHERE username = ?
            """, (ADMIN_ID,))

        conn.commit()


init_db()


def get_user(username):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        return dict(row) if row else None


def get_users():
    with get_connection() as conn:
        return [
            dict(row) for row in conn.execute(
                "SELECT * FROM users ORDER BY username"
            ).fetchall()
        ]


def create_user(username, password, name, penname):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO users
            (username, password, name, penname, role, status)
            VALUES (?, ?, ?, ?, 'member', 'active')
        """, (username, hash_password(password), name, penname))


def update_password(username, password):
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET password = ? WHERE username = ?",
            (hash_password(password), username)
        )


def update_user(username, name, penname, role=None, status=None):
    with get_connection() as conn:
        conn.execute("""
            UPDATE users SET name = ?, penname = ?
            WHERE username = ?
        """, (name, penname, username))

        if role is not None:
            conn.execute(
                "UPDATE users SET role = ? WHERE username = ?",
                (role, username)
            )

        if status is not None:
            conn.execute(
                "UPDATE users SET status = ? WHERE username = ?",
                (status, username)
            )


def get_record(username):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT data_json FROM records WHERE owner_username = ?",
            (username,)
        ).fetchone()
        return json.loads(row["data_json"]) if row else None


def save_record(username, record):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO records (
                owner_username, name, penname, discord,
                generation, phone, instagram, grad_year,
                meikyoku_roles, career_path, status, data_json
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
            ",".join(record.get("meikyoku_roles", [])),
            record.get("career_path"),
            record.get("status"),
            json.dumps(record, ensure_ascii=False)
        ))


def get_published_records():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT data_json FROM records
            WHERE status = 'published'
        """).fetchall()
        return [json.loads(row["data_json"]) for row in rows]


def get_questions():
    with get_connection() as conn:
        questions = [
            dict(q) for q in conn.execute(
                "SELECT * FROM questions ORDER BY id DESC"
            ).fetchall()
        ]
        for q in questions:
            q["answers"] = [
                dict(a) for a in conn.execute(
                    "SELECT * FROM answers WHERE question_id = ? ORDER BY id",
                    (q["id"],)
                ).fetchall()
            ]
        return questions


def add_question(name, content):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO questions (asker_name, content) VALUES (?, ?)",
            (name, content)
        )


def add_answer(question_id, username, name, anonymous, content):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO answers
            (question_id, username, name, is_anonymous, content)
            VALUES (?, ?, ?, ?, ?)
        """, (question_id, username, name, int(anonymous), content))


# ==========================================
# 共通処理
# ==========================================

def option_index(options, value, default=0):
    return options.index(value) if value in options else default


def generation_number(generation):
    numbers = re.findall(r"\d+", generation or "")
    return int(numbers[0]) if numbers else 999


def is_graduated(generation):
    return generation_number(generation) <= 5


if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

if "active_tab" not in st.session_state:
    st.session_state.active_tab = "📋 登録情報一覧（トップ）"


# ==========================================
# ログイン・新規登録
# ==========================================

if st.session_state.logged_in_user is None:
    st.title("🎓 メイキョク 就活・進路データベース")
    st.write("サークルメンバー限定サイトです。")

    _, center, _ = st.columns([1, 2, 1])

    with center:
        login_tab, signup_tab = st.tabs([
            "🔑 ログイン", "✨ 新規ユーザー登録"
        ])

        with login_tab:
            with st.form("login"):
                username = st.text_input("Discord ID")
                password = st.text_input("パスワード", type="password")
                submit = st.form_submit_button(
                    "ログインする", type="primary",
                    use_container_width=True
                )

                if submit:
                    account = get_user(username.strip())

                    if account and verify_password(
                        password, account["password"]
                    ):
                        if account["status"] != "active":
                            st.error("このアカウントは利用停止中です。")
                        else:
                            # 旧形式のパスワードをハッシュ化
                            if not account["password"].startswith(
                                "pbkdf2_sha256$"
                            ):
                                update_password(account["username"], password)

                            st.session_state.logged_in_user = account["username"]
                            st.rerun()
                    else:
                        st.error("IDまたはパスワードが違います。")

        with signup_tab:
            with st.form("signup"):
                new_id = st.text_input("Discord ID *")
                new_password = st.text_input(
                    "パスワード *", type="password"
                )
                new_confirm = st.text_input(
                    "確認用パスワード *", type="password"
                )
                new_name = st.text_input("名前（本名）*")
                new_penname = st.text_input("メイキョクネーム *")
                new_generation = st.selectbox(
                    "何期生か *", GENERATIONS, index=3
                )
                new_year = st.selectbox(
                    "卒業年度 *", YEARS, index=5
                )
                new_roles = st.multiselect(
                    "メイキョクでの役割 *", ROLES
                )
                new_path = st.radio("卒業後の進路 *", PATHS)

                submit = st.form_submit_button(
                    "登録してログインする",
                    type="primary",
                    use_container_width=True
                )

                if submit:
                    new_id = new_id.strip()
                    new_name = new_name.strip()
                    new_penname = new_penname.strip()

                    if not all([
                        new_id, new_password, new_name,
                        new_penname, new_roles
                    ]):
                        st.error("必須項目を入力してください。")
                    elif new_id in ("admin", "lil_3316", "aaaa", "yamada"):
                        st.error("このIDは使用できません。")
                    elif get_user(new_id):
                        st.error("このIDはすでに登録されています。")
                    elif new_password != new_confirm:
                        st.error("確認用パスワードが一致しません。")
                    else:
                        create_user(
                            new_id, new_password, new_name, new_penname
                        )
                        save_record(new_id, {
                            "owner_username": new_id,
                            "name": new_name,
                            "penname": new_penname,
                            "discord": new_id,
                            "generation": new_generation,
                            "grad_year": new_year,
                            "meikyoku_roles": new_roles,
                            "career_path": new_path,
                            "phone": "",
                            "instagram": "",
                            "status": "draft"
                        })
                        st.session_state.logged_in_user = new_id
                        st.rerun()

    st.stop()


# ==========================================
# ログイン後の権限確認
# ==========================================

user = get_user(st.session_state.logged_in_user)

if not user or user["status"] != "active":
    st.session_state.logged_in_user = None
    st.rerun()

is_admin = user["role"] == "admin"


# ==========================================
# プロフィール編集フォーム
# ==========================================

def profile_editor(username, key_prefix, administrator=False):
    target = get_user(username)

    if not target:
        st.error("ユーザーが見つかりません。")
        return

    record = get_record(username) or {}

    def val(key, default=""):
        value = record.get(key, default)
        return default if value is None else value

    with st.form(f"{key_prefix}_profile"):
        st.markdown("### 基本情報")

        name = st.text_input(
            "名前（本名）*",
            value=val("name", target["name"])
        )
        penname = st.text_input(
            "メイキョクネーム *",
            value=val("penname", target["penname"])
        )
        discord = st.text_input(
            "Discord ID（プロフィール表示用）",
            value=val("discord", username)
        )

        generation = st.selectbox(
            "期生", GENERATIONS,
            index=option_index(GENERATIONS, val("generation"), 3)
        )
        grad_year = st.selectbox(
            "卒業年", YEARS,
            index=option_index(YEARS, val("grad_year"), 5)
        )
        phone = st.text_input("電話番号", value=val("phone"))
        instagram = st.text_input(
            "Instagram ID", value=val("instagram")
        )

        old_roles = val("meikyoku_roles", [])
        if not isinstance(old_roles, list):
            old_roles = []

        roles = st.multiselect(
            "メイキョクでの業務内容",
            ROLES,
            default=[r for r in old_roles if r in ROLES]
        )

        st.markdown("### 進路情報")

        career_path = st.radio(
            "卒業後の進路",
            PATHS,
            index=option_index(PATHS, val("career_path"))
        )

        detail_values = {}
        for field, label in DETAIL_FIELDS[career_path].items():
            detail_values[field] = st.text_area(
                label, value=val(field)
            )

        if administrator:
            status = st.selectbox(
                "公開状態",
                ["draft", "published"],
                index=1 if val("status") == "published" else 0,
                format_func=lambda s: (
                    "公開" if s == "published" else "下書き"
                )
            )
            save = st.form_submit_button(
                "変更を保存する", type="primary"
            )
        else:
            col1, col2 = st.columns(2)
            with col1:
                draft = st.form_submit_button("下書き保存")
            with col2:
                publish = st.form_submit_button(
                    "公開して保存", type="primary"
                )
            save = draft or publish
            status = "published" if publish else "draft"

        if save:
            if not name.strip() or not penname.strip():
                st.error("名前とメイキョクネームは必須です。")
            else:
                updated = dict(record)
                updated.update({
                    "owner_username": username,
                    "name": name.strip(),
                    "penname": penname.strip(),
                    "discord": discord,
                    "generation": generation,
                    "grad_year": grad_year,
                    "phone": phone,
                    "instagram": instagram,
                    "meikyoku_roles": roles,
                    "career_path": career_path,
                    "status": status
                })
                updated.update(detail_values)

                update_user(username, name.strip(), penname.strip())
                save_record(username, updated)

                st.success("保存しました！")
                st.rerun()


# ==========================================
# 管理者専用機能
# ==========================================

@st.dialog("✏️ メンバー情報編集")
def admin_edit_profile(username):
    if not is_admin:
        st.error("管理者のみ操作できます。")
        return

    st.write(f"対象ID：`{username}`")
    profile_editor(username, f"admin_{username}", True)


@st.dialog("🔑 パスワード変更")
def admin_change_password(username):
    if not is_admin:
        st.error("管理者のみ操作できます。")
        return

    st.write(f"対象ID：`{username}`")

    with st.form(f"password_{username}"):
        password = st.text_input(
            "新しいパスワード", type="password"
        )
        confirm = st.text_input(
            "確認用パスワード", type="password"
        )

        if st.form_submit_button("変更する", type="primary"):
            if not password:
                st.error("パスワードを入力してください。")
            elif password != confirm:
                st.error("パスワードが一致しません。")
            else:
                update_password(username, password)
                st.success("パスワードを変更しました。")


@st.dialog("👤 メンバー詳細")
def show_profile(username):
    record = get_record(username)

    if not record or record.get("status") != "published":
        st.warning("このプロフィールは未公開です。")
        return

    st.subheader(record.get("name", ""))
    st.write(f"メイキョクネーム：{record.get('penname', '')}")
    st.write(f"期生：{record.get('generation', '')}")
    st.write(f"卒業年：{record.get('grad_year', '')}")
    st.write(f"進路：{record.get('career_path', '')}")

    for field, label in DETAIL_FIELDS.get(
        record.get("career_path"), {}
    ).items():
        st.write(f"**{label}：** {record.get(field) or '未記入'}")


# ==========================================
# ヘッダー
# ==========================================

col1, col2 = st.columns([3, 1])

with col1:
    st.title("🎓 メイキョク 就活・進路データベース")
    st.write(f"ログイン中：**{user['name']}**（{user['penname']}）")
    if is_admin:
        st.caption("👑 管理者")

with col2:
    if st.button("🚪 ログアウト", use_container_width=True):
        st.session_state.logged_in_user = None
        st.rerun()


tabs = [
    "📋 登録情報一覧（トップ）",
    "📝 自分の情報登録・編集",
    "💬 質問箱"
]
if is_admin:
    tabs.append("⚙️ 管理者画面")

selected_tab = st.radio(
    "メニュー",
    tabs,
    index=option_index(tabs, st.session_state.active_tab),
    horizontal=True,
    label_visibility="collapsed"
)
st.session_state.active_tab = selected_tab


# ==========================================
# 登録情報一覧
# ==========================================

if selected_tab == "📋 登録情報一覧（トップ）":
    st.subheader("🔍 登録情報一覧")

    c1, c2, c3 = st.columns(3)
    with c1:
        keyword = st.text_input("キーワード検索")
    with c2:
        filter_path = st.selectbox(
            "進路", ["すべて"] + PATHS
        )
    with c3:
        filter_year = st.selectbox(
            "卒業年", ["すべて"] + YEARS
        )

    records = get_published_records()
    filtered = []

    for record in records:
        if filter_path != "すべて" and record.get(
            "career_path"
        ) != filter_path:
            continue

        if filter_year != "すべて" and record.get(
            "grad_year"
        ) != filter_year:
            continue

        if keyword and keyword.lower() not in str(record).lower():
            continue

        filtered.append(record)

    filtered.sort(
        key=lambda r: generation_number(r.get("generation"))
    )

    graduated = [
        r for r in filtered
        if is_graduated(r.get("generation"))
    ]
    current = [
        r for r in filtered
        if not is_graduated(r.get("generation"))
    ]

    st.write(f"該当件数：**{len(filtered)}件**")

    tab1, tab2 = st.tabs([
        f"🎓 卒業メンバー（{len(graduated)}件）",
        f"🏫 現役メンバー（{len(current)}件）"
    ])

    def render_card(record):
        generation = record.get("generation") or "期生不明"
        name = record.get("name") or "未登録"
        penname = record.get("penname") or "未設定"
        year = record.get("grad_year") or "未設定"
        path = record.get("career_path") or "未設定"

        with st.expander(
            f"👤 [{generation}] {name} / {penname}"
            f"（{year}卒 / {path}）"
        ):
            roles = ", ".join(record.get("meikyoku_roles", []))
            st.write(f"**メイキョクでの役割：** {roles}")
            st.write(f"**Discord：** {record.get('discord', '-')}")
            st.write(f"**電話：** {record.get('phone', '-')}")
            st.write(f"**Instagram：** {record.get('instagram', '-')}")

            for field, label in DETAIL_FIELDS.get(path, {}).items():
                st.write(
                    f"**{label}：** {record.get(field) or '未記入'}"
                )

    with tab1:
        if graduated:
            for record in graduated:
                render_card(record)
        else:
            st.info("該当メンバーはいません。")

    with tab2:
        if current:
            for record in current:
                render_card(record)
        else:
            st.info("該当メンバーはいません。")


# ==========================================
# 自分の情報編集
# ==========================================

elif selected_tab == "📝 自分の情報登録・編集":
    st.subheader("📝 自分の情報登録・編集")
    profile_editor(user["username"], "my")


# ==========================================
# 質問箱
# ==========================================

elif selected_tab == "💬 質問箱":
    st.subheader("💬 質問箱（Q&Aボード）")

    with st.container(border=True):
        st.markdown("#### ✍️ 新しい質問を投稿")

        with st.form("question_form"):
            content = st.text_area("質問内容")
            anonymous = st.checkbox("匿名で投稿する", value=True)
            submit = st.form_submit_button(
                "質問を送信", type="primary"
            )

            if submit:
                if not content.strip():
                    st.error("質問を入力してください。")
                else:
                    name = (
                        "匿名希望" if anonymous
                        else f"{user['name']} ({user['penname']})"
                    )
                    add_question(name, content.strip())
                    st.rerun()

    st.markdown("### 📬 質問＆回答一覧")

    questions = get_questions()

    if not questions:
        st.info("まだ質問はありません。")

    for q in questions:
        with st.container(border=True):
            st.markdown(f"### ❓ {q['content']}")
            st.caption(f"投稿者：{q['asker_name']}")

            if q["answers"]:
                st.write(f"**回答：{len(q['answers'])}件**")

            for answer in q["answers"]:
                col1, col2 = st.columns([2, 8])

                with col1:
                    if answer["is_anonymous"]:
                        st.write("👤 匿名回答")
                    else:
                        if st.button(
                            f"👤 {answer['name']}",
                            key=f"answer_{answer['id']}"
                        ):
                            show_profile(answer["username"])

                with col2:
                    st.info(answer["content"])

            with st.expander("✏️ この質問に回答する"):
                with st.form(f"answer_form_{q['id']}"):
                    content = st.text_area("回答内容")
                    anonymous = st.checkbox("匿名で回答する")
                    submit = st.form_submit_button("回答を送信")

                    if submit:
                        if not content.strip():
                            st.error("回答を入力してください。")
                        else:
                            add_answer(
                                q["id"],
                                user["username"],
                                f"{user['name']} ({user['penname']})",
                                anonymous,
                                content.strip()
                            )
                            st.rerun()


# ==========================================
# 管理者画面
# ==========================================

elif selected_tab == "⚙️ 管理者画面":
    if not is_admin:
        st.error("管理者権限がありません。")
        st.stop()

    st.subheader("⚙️ 管理者画面")
    st.write(
        "メンバーのプロフィール、パスワード、"
        "権限、アクセス状態を管理できます。"
    )

    users = get_users()
    st.metric("登録ユーザー数", len(users))

    search = st.text_input(
        "🔍 メンバー検索",
        placeholder="名前・メイキョクネーム・ID"
    )

    for target in users:
        username = target["username"]

        search_text = (
            username + target["name"] + target["penname"]
        ).lower()

        if search and search.lower() not in search_text:
            continue

        with st.expander(
            f"👤 {target['name']}（{target['penname']}）"
            f" / {username}"
        ):
            st.write(f"**ID：** `{username}`")
            st.write(f"**権限：** {target['role']}")
            st.write(f"**状態：** {target['status']}")

            col1, col2 = st.columns(2)

            with col1:
                if st.button(
                    "✏️ 情報編集",
                    key=f"edit_{username}",
                    use_container_width=True
                ):
                    admin_edit_profile(username)

            with col2:
                if st.button(
                    "🔑 パスワード変更",
                    key=f"password_{username}",
                    use_container_width=True
                ):
                    admin_change_password(username)

            st.markdown("---")

            # adminは唯一の固定管理者として保護
            if username == ADMIN_ID:
                st.info(
                    "👑 メイン管理者です。"
                    "プロフィールとパスワードは編集できます。"
                )
            else:
                col1, col2 = st.columns(2)

                with col1:
                    role = st.selectbox(
                        "権限",
                        ["admin", "member"],
                        index=option_index(
                            ["admin", "member"], target["role"]
                        ),
                        key=f"role_{username}"
                    )

                    if st.button(
                        "権限を保存",
                        key=f"save_role_{username}"
                    ):
                        update_user(
                            username,
                            target["name"],
                            target["penname"],
                            role=role
                        )
                        st.rerun()

                with col2:
                    status = st.selectbox(
                        "アクセス状態",
                        ["active", "banned"],
                        index=option_index(
                            ["active", "banned"], target["status"]
                        ),
                        key=f"status_{username}"
                    )

                    if st.button(
                        "アクセス状態を保存",
                        key=f"save_status_{username}"
                    ):
                        update_user(
                            username,
                            target["name"],
                            target["penname"],
                            status=status
                        )
                        st.rerun()
