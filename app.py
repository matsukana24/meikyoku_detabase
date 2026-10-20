import datetime
import json
import sqlite3
import streamlit as st

st.set_page_config(
    page_title="メイキョク就活・進路データベース", layout="wide"
)


# 外部CSSファイルの読み込み
def load_css(file_name):
  try:
    with open(file_name, "r", encoding="utf-8") as f:
      st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
  except FileNotFoundError:
    pass


load_css("style.css")

# ==========================================
# 0. データベース（SQLite）のセットアップ
# ==========================================
DB_FILE = "database.db"


def get_connection():
  conn = sqlite3.connect(DB_FILE)
  conn.row_factory = sqlite3.Row
  return conn


def init_db():
  with get_connection() as conn:
    c = conn.cursor()

    # 1. ユーザーテーブル
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

    # 2. 進路情報テーブル
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
                FOREIGN KEY(owner_username) REFERENCES users(username)
            )
        """)

    try:
      c.execute("ALTER TABLE records ADD COLUMN generation TEXT")
    except sqlite3.OperationalError:
      pass

    # 3. 質問テーブル
    c.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asker_name TEXT,
                content TEXT
            )
        """)

    # 4. 回答テーブル
    c.execute("""
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER,
                username TEXT,
                name TEXT,
                is_anonymous INTEGER,
                content TEXT,
                FOREIGN KEY(question_id) REFERENCES questions(id)
            )
        """)

    # 初期管理者「松田夏奈 (lil_3316)」の登録（存在しない場合）
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
      c.execute(
          """
                INSERT INTO users (username, password, name, penname, role, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
          (
              "lil_3316",
              "08044713515",
              "松田夏奈",
              "まつかな",
              "admin",
              "active",
          ),
      )

    conn.commit()


init_db()

# Session State 初期設定
if "logged_in_user" not in st.session_state:
  st.session_state.logged_in_user = None

if "active_tab" not in st.session_state:
  st.session_state.active_tab = "📋 登録情報一覧（トップ）"


# --- DB操作用ヘルパー関数 ---
def get_user(username):
  with get_connection() as conn:
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    return dict(row) if row else None


def add_user(username, password, name, penname):
  with get_connection() as conn:
    conn.execute(
        "INSERT INTO users (username, password, name, penname, role, status)"
        " VALUES (?, ?, ?, ?, 'member', 'active')",
        (username, password, name, penname),
    )
    conn.commit()


def update_user_status(username, status):
  with get_connection() as conn:
    conn.execute(
        "UPDATE users SET status = ? WHERE username = ?", (status, username)
    )
    conn.commit()


def update_user_role(username, role):
  with get_connection() as conn:
    conn.execute(
        "UPDATE users SET role = ? WHERE username = ?", (role, username)
    )
    conn.commit()


def update_user_password(username, new_password):
  with get_connection() as conn:
    conn.execute(
        "UPDATE users SET password = ? WHERE username = ?",
        (new_password, username),
    )
    conn.commit()


def get_all_users():
  with get_connection() as conn:
    rows = conn.execute("SELECT * FROM users").fetchall()
    return [dict(r) for r in rows]


def save_user_record(username, record_dict):
  data_json = json.dumps(record_dict, ensure_ascii=False)
  roles_str = ",".join(record_dict.get("meikyoku_roles", []))

  with get_connection() as conn:
    conn.execute(
        """
            INSERT INTO records (
                owner_username, name, penname, discord, generation, phone, instagram,
                grad_year, meikyoku_roles, career_path, status, data_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_username) DO UPDATE SET
                name=excluded.name,
                penname=excluded.penname,
                discord=excluded.discord,
                generation=excluded.generation,
                phone=excluded.phone,
                instagram=excluded.instagram,
                grad_year=excluded.grad_year,
                meikyoku_roles=excluded.meikyoku_roles,
                career_path=excluded.career_path,
                status=excluded.status,
                data_json=excluded.data_json
        """,
        (
            username,
            record_dict.get("name"),
            record_dict.get("penname"),
            record_dict.get("discord"),
            record_dict.get("generation"),
            record_dict.get("phone"),
            record_dict.get("instagram"),
            record_dict.get("grad_year"),
            roles_str,
            record_dict.get("career_path"),
            record_dict.get("status"),
            data_json,
        ),
    )
    conn.commit()


def get_published_records():
  with get_connection() as conn:
    rows = conn.execute(
        "SELECT data_json FROM records WHERE status = 'published'"
    ).fetchall()
    return [json.loads(r["data_json"]) for r in rows]


def get_record_by_username(username):
  with get_connection() as conn:
    row = conn.execute(
        "SELECT data_json FROM records WHERE owner_username = ?", (username,)
    ).fetchone()
    return json.loads(row["data_json"]) if row else None


def add_question(asker_name, content):
  with get_connection() as conn:
    conn.execute(
        "INSERT INTO questions (asker_name, content) VALUES (?, ?)",
        (asker_name, content),
    )
    conn.commit()


def add_answer(question_id, username, name, is_anonymous, content):
  with get_connection() as conn:
    conn.execute(
        """
            INSERT INTO answers (question_id, username, name, is_anonymous, content)
            VALUES (?, ?, ?, ?, ?)
        """,
        (question_id, username, name, 1 if is_anonymous else 0, content),
    )
    conn.commit()


def get_questions_and_answers():
  with get_connection() as conn:
    questions = conn.execute(
        "SELECT * FROM questions ORDER BY id DESC"
    ).fetchall()
    result = []
    for q in questions:
      q_dict = dict(q)
      answers = conn.execute(
          "SELECT * FROM answers WHERE question_id = ? ORDER BY id ASC",
          (q_dict["id"],),
      ).fetchall()
      q_dict["answers"] = [
          {
              "username": a["username"],
              "name": a["name"],
              "is_anonymous": bool(a["is_anonymous"]),
              "content": a["content"],
          }
          for a in answers
      ]
      result.append(q_dict)
    return result


def get_gen_sort_key(gen_str):
  if not gen_str:
    return 999
  import re

  nums = re.findall(r"\d+", gen_str)
  if nums:
    return int(nums[0])
  return 999


def is_graduated_generation(gen_str):
  if not gen_str:
    return False
  for g in ["1〜2期", "1-2期", "3期", "4期", "5期"]:
    if g in gen_str:
      return True
  import re

  nums = re.findall(r"\d+", gen_str)
  if nums and int(nums[0]) <= 5:
    return True
  return False


# ==========================================
# 1. ログイン & 新規ユーザー登録画面
# ==========================================
if st.session_state.logged_in_user is None:
  st.title("🎓 メイキョク 就活・進路データベース")
  st.write(
      "※このサイトはサークルメンバー限定です。ログインまたは新規登録を行ってください。"
  )
  st.markdown("---")

  col1, col2, col3 = st.columns([1, 2, 1])
  with col2:
    auth_tab1, auth_tab2 = st.tabs(["🔑 ログイン", "✨ 新規ユーザー登録"])

    with auth_tab1:
      with st.form("login_form"):
        st.subheader("ログイン")
        username_input = st.text_input("Discord ID（ユーザー名）")
        pass_input = st.text_input("パスワード", type="password")
        submit_login = st.form_submit_button(
            "ログインする", use_container_width=True, type="primary"
        )

        if submit_login:
          user_info = get_user(username_input)
          if user_info and user_info["password"] == pass_input:
            if user_info["status"] == "banned":
              st.error(
                  "❌"
                  " このアカウントはアクセス権限が停止（除籍等）されています。管理者に連絡してください。"
              )
            else:
              st.session_state.logged_in_user = {
                  "username": user_info["username"],
                  "name": user_info["name"],
                  "penname": user_info["penname"],
                  "role": user_info["role"],
              }
              st.success("ログイン成功！")
              st.rerun()
          else:
            st.error("ユーザー名またはパスワードが正しくありません。")

    with auth_tab2:
      with st.form("signup_form"):
        st.subheader("新規アカウント作成 ＆ 必須情報登録")
        st.caption(
            "登録完了と同時にアカウントが作成され、初期データが保存されます。"
        )

        new_username = st.text_input(
            "Discord ID *", placeholder="例: taro123"
        )
        new_pass = st.text_input("パスワード *", type="password")
        new_pass_confirm = st.text_input(
            "パスワード（確認用）*", type="password"
        )

        st.markdown("---")
        st.markdown("**【プロフィール必須項目】**")
        new_name = st.text_input(
            "名前（本名）*", placeholder="例: 山田 太郎"
        )
        new_penname = st.text_input(
            "メイキョクネーム *", placeholder="例: ヤマタツ"
        )

        generation_options = [
            "1〜2期生",
            "3期生",
            "4期生",
            "5期生",
            "6期生",
            "7期生",
            "8期生",
            "9期生",
            "10期生+",
        ]
        new_generation = st.selectbox(
            "何期生か *", generation_options, index=3
        )

        grad_years_list = [f"{y}年" for y in range(2020, 2033)] + [
            "その他 / 既卒"
        ]
        new_grad_year = st.selectbox(
            "卒業年度 *", grad_years_list, index=5
        )

        role_options = [
            "代表",
            "副代表",
            "営業",
            "イベント企画",
            "SNS",
            "開発",
            "記事",
        ]
        new_roles = st.multiselect(
            "メイキョクでの役割・業務 *", options=role_options
        )

        new_career_path = st.radio(
            "卒業後の進路 *", ["就職", "進学", "起業"]
        )

        submit_signup = st.form_submit_button(
            "登録してログインする", type="primary", use_container_width=True
        )

        if submit_signup:
          if (
              not new_username
              or not new_name
              or not new_penname
              or not new_pass
              or not new_roles
          ):
            st.error("すべての必須項目（*）を入力・選択してください。")
          elif get_user(new_username):
            st.error("このDiscord IDはすでに使われています。")
          elif new_pass != new_pass_confirm:
            st.error("確認用パスワードが一致しません。")
          else:
            # 1. ユーザー作成
            add_user(new_username, new_pass, new_name, new_penname)
            # 2. 初期レコード（下書きまたは公開）の作成
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
                "career_path": new_career_path,
                "status": "draft",  # 初回は下書き保存状態、編集から公開可能
            }
            save_user_record(new_username, initial_record)

            st.session_state.logged_in_user = {
                "username": new_username,
                "name": new_name,
                "penname": new_penname,
                "role": "member",
            }
            st.success(
                "アカウント作成＆初期登録が完了しました！マイページから詳細情報を追記・公開できます。"
            )
            st.rerun()

  st.stop()

# ==========================================
# 2. ログイン後のメイン画面
# ==========================================
user = st.session_state.logged_in_user


# プロフィール詳細ポップアップ関数
@st.dialog("👤 メンバー詳細プロフィール")
def show_user_profile(target_username):
  target_record = get_record_by_username(target_username)
  if not target_record or target_record.get("status") != "published":
    st.warning("このユーザーの情報はまだ登録されていないか、未公開です。")
    return

  st.subheader(f"{target_record['name']}（{target_record.get('penname', '')}）")
  st.write(
      f"**期生:** {target_record.get('generation', '-')} | **卒業年:**"
      f" {target_record.get('grad_year', '-')} | **進路:**"
      f" {target_record.get('career_path', '-')}"
  )
  roles_str = ", ".join(target_record.get("meikyoku_roles", []))
  st.write(f"**メイキョクでの役割:** {roles_str}")
  st.write(
      f"📞 **連絡先:** Discord: `{target_record.get('discord', '-')}` | 電話:"
      f" {target_record.get('phone', '-')} | Insta:"
      f" {target_record.get('instagram', '-')}"
  )
  st.markdown("---")

  path = target_record.get("career_path")
  if path == "就職":
    st.write(
        f"**入社決定先:** {target_record.get('company_joined', '未記入')}"
    )
    st.write(f"**内定先:** {target_record.get('offers', '未記入')}")
    st.write(
        f"**志望業界/職種:** {target_record.get('target_industry', '')} /"
        f" {target_record.get('target_occupation', '')}"
    )
    st.write(
        f"**就活の軸（本音）:** {target_record.get('axis_real', '未記入')}"
    )
    st.write(
        f"**就活の軸（建前）:**"
        f" {target_record.get('axis_official', '未記入')}"
    )
    st.write(
        f"**入社決定理由:** {target_record.get('decision_reason', '未記入')}"
    )
    st.write(f"**自己分析Tips:** {target_record.get('tips_self', '未記入')}")
    st.write(f"**ES Tips:** {target_record.get('tips_es', '未記入')}")
    st.write(f"**面接Tips:** {target_record.get('tips_interview', '未記入')}")
  elif path == "進学":
    st.write(f"**進学先:** {target_record.get('grad_school', '未記入')}")
    st.write(
        f"**留意したこと:**"
        f" {target_record.get('grad_choice_reason', '未記入')}"
    )
    st.write(
        f"**アドバイス:** {target_record.get('grad_advice', '未記入')}"
    )
  elif path == "起業":
    st.write(
        f"**起業企業名:** {target_record.get('startup_name', '未記入')}"
    )
    st.write(
        f"**起業理由:** {target_record.get('startup_reason', '未記入')}"
    )


# 管理者用のパスワード変更ポップアップ関数
@st.dialog("🔑 パスワード変更")
def show_password_change_dialog(target_username, target_name):
  st.write(f"**対象ユーザー:** {target_name} (ID: `{target_username}`)")
  with st.form(f"change_pass_form_{target_username}"):
    new_pass = st.text_input("新しいパスワード", type="password")
    new_pass_confirm = st.text_input(
        "新しいパスワード（確認用）", type="password"
    )
    submit_change = st.form_submit_button(
        "パスワードを更新する", type="primary"
    )

    if submit_change:
      if not new_pass:
        st.error("パスワードを入力してください。")
      elif new_pass != new_pass_confirm:
        st.error("確認用パスワードが一致しません。")
      else:
        update_user_password(target_username, new_pass)
        st.success(f"{target_name} さんのパスワードを変更しました！")
        st.rerun()


# ヘッダーエリア
col_head1, col_head2 = st.columns([3, 1])
with col_head1:
  st.title("🎓 メイキョク 就活・進路データベース")
  st.write(
      f"ログイン中: **{user['name']}（メイキョクネーム: {user['penname']}）** さん"
  )

with col_head2:
  if st.button("🚪 ログアウト", use_container_width=True):
    st.session_state.logged_in_user = None
    st.rerun()

# タブメニュー定義
tab_names = ["📋 登録情報一覧（トップ）", "📝 自分の情報登録・編集", "💬 質問箱"]
if user["role"] == "admin":
  tab_names.append("⚙️ 管理者画面")

selected_tab = st.radio(
    "メニュー切り替え",
    options=tab_names,
    index=(
        tab_names.index(st.session_state.active_tab)
        if st.session_state.active_tab in tab_names
        else 0
    ),
    horizontal=True,
    label_visibility="collapsed",
)

st.session_state.active_tab = selected_tab


# 共通カード表示関数（一覧用）
def render_member_card(item):
  roles_str = (
      ", ".join(item.get("meikyoku_roles", []))
      if item.get("meikyoku_roles")
      else "未登録"
  )
  gen_title = item.get("generation", "期生不明")
  with st.expander(
      f"👤 [{gen_title}] {item['name']} / {item.get('penname', '未設定')}（{item['grad_year']}卒"
      f" / {item['career_path']}）"
  ):
    st.markdown(
        f"**本名:** {item['name']} | **メイキョクネーム:**"
        f" {item.get('penname', '未設定')} | **期生:**"
        f" {item.get('generation', '未設定')}"
    )
    st.markdown(f"**メイキョクでの役職・業務:** {roles_str}")
    st.markdown(
        f"📞 **連絡先:** Discord: `{item.get('discord', '-')}` | 電話:"
        f" `{item.get('phone', '-')}` | Instagram:"
        f" `{item.get('instagram', '-')}`"
    )
    st.markdown("---")

    path = item.get("career_path")
    if path == "就職":
      col_a, col_b = st.columns(2)
      with col_a:
        st.write(
            f"**🏢 入社確定先:** {item.get('company_joined', '未記入')}"
        )
        st.write(f"**🎯 内定先:** {item.get('offers', '未記入')}")
        st.write(
            f"**💼 インターン先:** {item.get('internships', '未記入')}"
        )
      with col_b:
        st.write(
            f"**🌐 志望業界:** {item.get('target_industry', '未記入')}"
        )
        st.write(
            f"**⚙️ 志望職種:** {item.get('target_occupation', '未記入')}"
        )

      st.write(f"**💡 就活の軸（本音）:** {item.get('axis_real', '未記入')}")
      st.write(
          f"**📢 就活の軸（建前）:** {item.get('axis_official', '未記入')}"
      )
      st.write(
          f"**🎯 入社決定理由:** {item.get('decision_reason', '未記入')}"
      )
      st.write(f"・**自己分析Tips:** {item.get('tips_self', '未記入')}")
      st.write(f"・**ES Tips:** {item.get('tips_es', '未記入')}")
      st.write(f"・**面接Tips:** {item.get('tips_interview', '未記入')}")

      with st.expander("📄 自己PR・志望動機・ガクチカを見る"):
        st.write(f"**【自己PR】**\n{item.get('pr_text', '未記入')}")
        st.write(
            f"**【志望動機】**\n{item.get('motivation_text', '未記入')}"
        )
        st.write(
            f"**【メイキョクでのガクチカ】**\n{item.get('gakuchika', '未記入')}"
        )

    elif path == "進学":
      st.write(f"**進学先:** {item.get('grad_school', '未記入')}")
      st.write(
          f"**留意したこと:** {item.get('grad_choice_reason', '未記入')}"
      )
      st.write(
          f"**進学のアドバイス:** {item.get('grad_advice', '未記入')}"
      )

    elif path == "起業":
      st.write(f"**起業企業名:** {item.get('startup_name', '未記入')}")
      st.write(
          f"**（起業の）業界:** {item.get('startup_industry', '未記入')}"
      )
      st.write(f"**起業理由:** {item.get('startup_reason', '未記入')}")


# --- タブ1: 一覧表示 ---
if selected_tab == "📋 登録情報一覧（トップ）":
  st.subheader("🔍 登録情報の一覧・絞り込み検索")
  col_s1, col_s2, col_s3 = st.columns(3)
  with col_s1:
    search_keyword = st.text_input("キーワード検索（名前・企業名など）")
  with col_s2:
    filter_path = st.selectbox(
        "進路で絞り込み", ["すべて", "就職", "進学", "起業"]
    )
  with col_s3:
    year_options = (
        ["すべて"] + [f"{y}年" for y in range(2020, 2033)] + ["その他 / 既卒"]
    )
    filter_year = st.selectbox("卒業年で絞り込み", year_options)

  published_records = get_published_records()
  filtered_data = published_records
  if filter_path != "すべて":
    filtered_data = [
        d for d in filtered_data if d.get("career_path") == filter_path
    ]
  if filter_year != "すべて":
    filtered_data = [
        d for d in filtered_data if d.get("grad_year") == filter_year
    ]
  if search_keyword:
    filtered_data = [
        d for d in filtered_data if search_keyword.lower() in str(d).lower()
    ]

  # 期生の数字が小さい順（先輩順）にソート
  filtered_data.sort(key=lambda x: get_gen_sort_key(x.get("generation", "")))

  st.write(f"該当件数: **{len(filtered_data)} 件**")
  st.markdown("---")

  # 現役メンバーと卒業メンバーに分類
  graduated_list = [
      d for d in filtered_data if is_graduated_generation(d.get("generation"))
  ]
  current_list = [
      d
      for d in filtered_data
      if not is_graduated_generation(d.get("generation"))
  ]

  list_tab1, list_tab2 = st.tabs([
      f"🎓 卒業メンバー（{len(graduated_list)}件）",
      f"🏫 現役メンバー（{len(current_list)}件）",
  ])

  with list_tab1:
    if graduated_list:
      for item in graduated_list:
        render_member_card(item)
    else:
      st.info("該当する卒業メンバーはいません。")

  with list_tab2:
    if current_list:
      for item in current_list:
        render_member_card(item)
    else:
      st.info("該当する現役メンバーはいません。")

# --- タブ2: 自分の情報登録 ---
elif selected_tab == "📝 自分の情報登録・編集":
  st.subheader("📝 自身の就活・進路情報の登録・編集")
  my_record = get_record_by_username(user["username"])

  if my_record:
    status_label = (
        "🟢 公開中" if my_record.get("status") == "published" else "🟡 下書き"
    )
    st.info(f"現在のステータス: **{status_label}**")

  def get_val(key, default=""):
    return my_record.get(key, default) if my_record else default

  st.markdown("### 1. 基本情報（必須）")
  col_name1, col_name2 = st.columns(2)
  with col_name1:
    name = st.text_input("名前（本名）*", value=get_val("name", user["name"]))
  with col_name2:
    penname = st.text_input(
        "メイキョクネーム *", value=get_val("penname", user["penname"])
    )

  col_c1, col_c2, col_c3 = st.columns(3)
  with col_c1:
    discord = st.text_input(
        "Discord ID *", value=get_val("discord", user["username"])
    )
  with col_c2:
    generation_options = [
        "1〜2期生",
        "3期生",
        "4期生",
        "5期生",
        "6期生",
        "7期生",
        "8期生",
        "9期生",
        "10期生+",
    ]
    gen_val = get_val("generation", "5期生")
    gen_idx = (
        generation_options.index(gen_val)
        if gen_val in generation_options
        else 3
    )
    generation = st.selectbox("何期生か *", generation_options, index=gen_idx)
  with col_c3:
    phone = st.text_input("電話番号", value=get_val("phone", ""))

  instagram = st.text_input("Instagram ID", value=get_val("instagram", ""))

  grad_years_list = [f"{y}年" for y in range(2020, 2033)] + ["その他 / 既卒"]
  current_year_idx = (
      grad_years_list.index(get_val("grad_year"))
      if get_val("grad_year") in grad_years_list
      else 5
  )
  grad_year = st.selectbox("卒業年 *", grad_years_list, index=current_year_idx)

  role_options = [
      "代表",
      "副代表",
      "営業",
      "イベント企画",
      "SNS",
      "開発",
      "記事",
  ]
  meikyoku_roles = st.multiselect(
      "メイキョクでの業務内容 *",
      options=role_options,
      default=get_val("meikyoku_roles", []),
  )

  st.markdown("---")
  st.markdown("### 2. 進路と詳細情報")
  career_paths = ["就職", "進学", "起業"]
  path_idx = (
      career_paths.index(get_val("career_path"))
      if get_val("career_path") in career_paths
      else 0
  )
  career_path = st.radio("卒業後の進路 *", career_paths, index=path_idx)

  form_data = {}
  if career_path == "就職":
    col_j1, col_j2 = st.columns(2)
    with col_j1:
      form_data["company_joined"] = st.text_input(
          "入社先（自由記述）", value=get_val("company_joined")
      )
      form_data["offers"] = st.text_input(
          "内定先（自由記述）", value=get_val("offers")
      )
      form_data["internships"] = st.text_input(
          "インターン先（自由記述）", value=get_val("internships")
      )
    with col_j2:
      form_data["target_industry"] = st.text_input(
          "志望業界", value=get_val("target_industry")
      )
      form_data["target_occupation"] = st.text_input(
          "志望職種", value=get_val("target_occupation")
      )

    form_data["axis_real"] = st.text_area(
        "就活の軸（本音）", value=get_val("axis_real")
    )
    form_data["axis_official"] = st.text_area(
        "就活の軸（建前）", value=get_val("axis_official")
    )
    form_data["decision_reason"] = st.text_area(
        "入社先決定理由", value=get_val("decision_reason")
    )
    form_data["tips_self"] = st.text_area(
        "自己分析のTips", value=get_val("tips_self")
    )
    form_data["tips_es"] = st.text_area("ESのTips", value=get_val("tips_es"))
    form_data["tips_interview"] = st.text_area(
        "面接のTips", value=get_val("tips_interview")
    )
    form_data["pr_text"] = st.text_area("自己PR文", value=get_val("pr_text"))
    form_data["motivation_text"] = st.text_area(
        "志望動機", value=get_val("motivation_text")
    )
    form_data["gakuchika"] = st.text_area(
        "メイキョクについてのガクチカ", value=get_val("gakuchika")
    )

  elif career_path == "進学":
    form_data["grad_school"] = st.text_input(
        "進学先（自由記述）", value=get_val("grad_school")
    )
    form_data["grad_choice_reason"] = st.text_area(
        "進学先選びで留意したこと", value=get_val("grad_choice_reason")
    )
    form_data["grad_advice"] = st.text_area(
        "進学のアドバイス", value=get_val("grad_advice")
    )

  elif career_path == "起業":
    form_data["startup_name"] = st.text_input(
        "起業企業名（自由記述）", value=get_val("startup_name")
    )
    form_data["startup_industry"] = st.text_input(
        "（起業の）業界", value=get_val("startup_industry")
    )
    form_data["startup_reason"] = st.text_area(
        "起業理由", value=get_val("startup_reason")
    )

  st.markdown("---")
  col_btn1, col_btn2 = st.columns(2)


  def handle_save(status_type):
    record_dict = {
        "owner_username": user["username"],
        "name": name,
        "penname": penname,
        "discord": discord,
        "generation": generation,
        "phone": phone,
        "instagram": instagram,
        "grad_year": grad_year,
        "meikyoku_roles": meikyoku_roles,
        "career_path": career_path,
        "status": status_type,
        **form_data,
    }
    save_user_record(user["username"], record_dict)


  with col_btn1:
    if st.button("💾 下書き保存する", use_container_width=True):
      handle_save("draft")
      st.toast("下書きとして保存しました！")
      st.rerun()

  with col_btn2:
    if st.button("🚀 公開して保存する", type="primary", use_container_width=True):
      handle_save("published")
      st.session_state.active_tab = "📋 登録情報一覧（トップ）"
      st.toast("情報を公開保存し、一覧ページへ移動しました！")
      st.rerun()

# --- タブ3: 質問箱（リニューアル） ---
elif selected_tab == "💬 質問箱":
  st.subheader("💬 質問箱（Q&Aボード）")
  st.write(
      "就活や進路についての疑問を投稿したり、先輩や仲間からの回答を確認できます。"
  )

  # 新規質問投稿エリア
  with st.container(border=True):
    st.markdown("#### ✍️ 新しい質問を投稿する")
    with st.form("new_question_form"):
      q_input = st.text_area(
          "質問内容",
          placeholder="例: IT業界のインターンで評価されるポイントを教えてください！",
          label_visibility="collapsed",
      )
      col_q1, col_q2 = st.columns([3, 1])
      with col_q1:
        is_q_anon = st.checkbox("匿名で質問を投稿する", value=True)
      with col_q2:
        submit_q = st.form_submit_button(
            "質問を送信", type="primary", use_container_width=True
        )

      if submit_q and q_input:
        asker = (
            "匿名希望" if is_q_anon else f"{user['name']} ({user['penname']})"
        )
        add_question(asker, q_input)
        st.toast("質問を投稿しました！")
        st.rerun()

  st.markdown("---")
  st.markdown("### 📬 質問＆回答一覧")

  questions_data = get_questions_and_answers()
  if not questions_data:
    st.info("現在、投稿された質問はありません。最初の質問を投稿してみましょう！")

  for q in questions_data:
    with st.container(border=True):
      # 質問ヘッダー
      st.markdown(f"### ❓ {q['content']}")
      st.caption(f"投稿者: **{q['asker_name']}**")

      # 回答セクション
      if q["answers"]:
        st.markdown(f"**💬 回答 ({len(q['answers'])}件)**")
        for ans in q["answers"]:
          with st.container():
            col_ans1, col_ans2 = st.columns([2, 8])
            with col_ans1:
              if ans["is_anonymous"]:
                st.write("👤 **匿名回答**")
              else:
                if st.button(
                    f"👤 {ans['name']}",
                    key=(
                        f"user_btn_{q['id']}_{ans['username']}_{ans['content'][:5]}"
                    ),
                ):
                  show_user_profile(ans["username"])
            with col_ans2:
              st.info(ans["content"])
      else:
        st.caption("💬 まだ回答はありません。最初の回答をしてみませんか？")

      # 回答投稿用フォーム
      with st.expander("✏️ この質問に回答する"):
        with st.form(f"answer_form_{q['id']}"):
          ans_input = st.text_area(
              "回答を入力",
              placeholder="あなたの経験やアドバイスを教えてください",
              key=f"text_{q['id']}",
              label_visibility="collapsed",
          )
          col_a1, col_a2 = st.columns([3, 1])
          with col_a1:
            is_ans_anon = st.checkbox("匿名で回答する", key=f"anon_{q['id']}")
          with col_a2:
            submit_ans = st.form_submit_button(
                "回答を送信", use_container_width=True
            )

          if submit_ans and ans_input:
            add_answer(
                q["id"],
                user["username"],
                f"{user['name']} ({user['penname']})",
                is_ans_anon,
                ans_input,
            )
            st.toast("回答を送信しました！")
            st.rerun()

# --- タブ4: 管理者画面 ---
elif selected_tab == "⚙️ 管理者画面":
  st.subheader("⚙️ メンバーの権限・パスワード・アクセス管理")
  users_list = get_all_users()
  for u_info in users_list:
    username = u_info["username"]
    if username == user["username"]:
      continue

    col_u1, col_u2, col_u3, col_u4, col_u5 = st.columns([2, 1.5, 1, 1, 1])
    with col_u1:
      st.write(
          f"**{u_info['name']}**（メイキョクネーム:"
          f" {u_info.get('penname', '-')}) - ID: `{username}`"
      )

    with col_u2:
      if username == "lil_3316":
        st.write("👑 管理者 (固定)")
      else:
        current_role_idx = 0 if u_info["role"] == "admin" else 1
        new_role_choice = st.selectbox(
            "権限",
            ["admin", "member"],
            index=current_role_idx,
            key=f"role_{username}",
            label_visibility="collapsed",
        )
        if new_role_choice != u_info["role"]:
          update_user_role(username, new_role_choice)
          st.toast(
              f"{u_info['name']} さんの権限を"
              f" {'管理者' if new_role_choice == 'admin' else 'メンバー'} に変更しました。"
          )
          st.rerun()

    with col_u3:
      status_label = (
          "🟢 許可" if u_info["status"] == "active" else "🔴 ブロック"
      )
      st.write(f"状態: {status_label}")

    with col_u4:
      if st.button("🔑 パスワード", key=f"pass_btn_{username}"):
        show_password_change_dialog(username, u_info["name"])

    with col_u5:
      if username == "lil_3316":
        st.write("🔒 保護中")
      else:
        if u_info["status"] == "active":
          if st.button("🚫 ブロック", key=f"ban_{username}"):
            update_user_status(username, "banned")
            st.toast(f"{u_info['name']} さんをブロックしました。")
            st.rerun()
        else:
          if st.button("⭕️ 解除", key=f"unban_{username}"):
            update_user_status(username, "active")
            st.toast(f"{u_info['name']} さんのブロックを解除しました。")
            st.rerun()