import re
from io import StringIO
from typing import Dict, List
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

try:
    import accounts as account_module
except Exception:
    account_module = None

try:
    from area import AREA_CONFIG
except Exception:
    AREA_CONFIG = {
        "台北": {
            "sheet_id": "1hsmwhA36I0BPXQ8d6OYGGn8R_SETQe4vTR_FB5Sp8Uc",
            "sheet_name": "新人基本資料",
            "extra_payload": {},
        }
    }

try:
    import gspread
except Exception:
    gspread = None

BASE_URL = "https://backend.lemonclean.com.tw"
LOGIN_URL = f"{BASE_URL}/login"
USER_ADD_URL = f"{BASE_URL}/user/add"
USER_LIST_URL = f"{BASE_URL}/user"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": USER_ADD_URL,
}

FIXED_VALUES = {
    "使用者類型": "專員",
    "專員類型": "居家專員",
    "服務項目": "居家清潔",
    "意外險": "有",
    "良民證": "有",
    "角色": "專員管理",
    "狀態": "正常",
}

FORM_FIELD_MAP = {
    "使用者類型": "user_type_id",
    "專員類型": "coordinator_type",
    "使用者名稱": "name",
    "使用者密碼": "password",
    "email": "email",
    "生日": "birthday",
    "身分證字號": "id_number",
    "電話": "phone",
    "地址": "address",
    "緊急連絡人姓名": "urgent_name",
    "緊急連絡人關係": "urgent_relationship",
    "緊急連絡人電話": "urgent_phone",
    "到職日期": "date_arrival",
    "意外險": "pa",
    "良民證": "police_certificate",
    "總體表現": "score",
    "薪等": "wage_level",
    "時薪": "wage",
    "排班備註": "memoSchedule",
    "備註": "memo",
    "角色": "role_id[]",
    "狀態": "flag",
}

VALUE_MAP = {
    "使用者類型": {"專員": "2", "內勤": "1", "客服": "1"},
    "專員類型": {"居家專員": "1", "家電／傢俱專員": "2", "收納專員": "3"},
    "意外險": {"有": "1", "無": "0"},
    "良民證": {"有": "1", "無": "0"},
    "狀態": {"正常": "1", "停用": "0"},
    "角色": {
        "專員管理": "1",
        "系統管理員": "2",
        "客服": "3",
        "外場主管": "4",
        "分店主管": "5",
        "行銷": "6",
    },
}

COORDINATOR_ITEM_MAP = {
    "居家清潔": "1",
    "簡易收納": "2",
    "整理收納": "3",
    "裝潢清潔": "4",
    "空屋清潔": "5",
    "鐘點清潔": "6",
    "家電清潔": "7",
    "洗衣機清潔": "8",
    "冷氣清潔": "9",
    "床墊清潔": "10",
}

REQUIRED_SHEET_COLUMNS = [
    "使用者名稱", "使用者密碼", "email", "生日", "身分證字號", "電話", "地址",
    "緊急連絡人姓名", "緊急連絡人關係", "緊急連絡人電話", "到職日期",
    "總體表現", "薪等", "時薪"
]

SOURCE_COLUMN_MAP = {
    "使用者名稱": "使用者名稱",
    "使用者密碼": "使用者密碼",
    "email": "email",
    "生日": "生日",
    "身分證字號": "身分證字號",
    "電話": "電話",
    "地址": "地址",
    "緊急連絡人姓名": "緊急連絡人姓名",
    "緊急連絡人關係": "緊急連絡人關係",
    "緊急連絡人電話": "緊急連絡人電話",
    "到職日期": "到職日期",
    "意外險": "意外險",
    "良民證": "良民證",
    "總體表現": "總體表現",
    "薪等": "薪等",
    "時薪": "時薪",
    "角色": "角色",
    "狀態": "狀態",
    "服務項目": "服務項目",
    "排班備註": "排班備註",
    "備註": "備註",
}


def load_accounts() -> Dict[str, Dict[str, str]]:
    accounts: Dict[str, Dict[str, str]] = {}
    if account_module is None:
        return accounts

    if hasattr(account_module, "ACCOUNTS"):
        raw = getattr(account_module, "ACCOUNTS")
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(v, dict):
                    email = v.get("email")
                    password = v.get("password")
                    if email and password:
                        accounts[str(k)] = {
                            "email": str(email),
                            "password": str(password),
                        }
    return accounts


def build_sheet_csv_url(sheet_id: str, sheet_name: str) -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
        f"?tqx=out:csv&sheet={sheet_name}"
    )


def fetch_sheet(sheet_id: str, sheet_name: str) -> pd.DataFrame:
    url = build_sheet_csv_url(sheet_id, sheet_name)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return pd.read_csv(StringIO(resp.text), dtype=str, keep_default_na=False)


def get_login_token(session: requests.Session) -> str:
    r = session.get(LOGIN_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    token_input = soup.find("input", {"name": "_token"})
    if not token_input or not token_input.get("value"):
        raise RuntimeError("找不到登入頁 _token")
    return token_input["value"]


def login_backend(email: str, password: str) -> requests.Session:
    session = requests.Session()
    token = get_login_token(session)
    payload = {"_token": token, "email": email, "password": password}
    r = session.post(LOGIN_URL, data=payload, headers=HEADERS, timeout=30, allow_redirects=True)
    r.raise_for_status()
    if "login" in r.url.lower():
        raise RuntimeError("登入失敗，請確認 accounts.py 的帳密")
    return session


def inspect_user_add_form(session: requests.Session) -> Dict:
    r = session.get(USER_ADD_URL, headers=HEADERS, timeout=30, allow_redirects=True)
    r.raise_for_status()
    if "login" in r.url.lower():
        raise RuntimeError("登入狀態失效，已被導回登入頁")

    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form")
    if not form:
        raise RuntimeError("找不到新增使用者表單")

    token_input = form.find("input", {"name": "_token"})
    if not token_input or not token_input.get("value"):
        raise RuntimeError("找不到表單 _token")

    action = form.get("action") or "/user/add"
    method = (form.get("method") or "POST").upper()
    submit_url = action if action.startswith("http") else BASE_URL + action

    names = set()
    for tag in form.find_all(["input", "select", "textarea"]):
        name = tag.get("name")
        if name:
            names.add(name)

    return {
        "submit_url": submit_url,
        "method": method,
        "_token": token_input["value"],
        "field_names": sorted(names),
    }


def validate_sheet_columns(df: pd.DataFrame) -> List[str]:
    return [c for c in REQUIRED_SHEET_COLUMNS if c not in df.columns]


def fix_phone(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    if "e" in text.lower():
        try:
            text = str(int(float(text)))
        except Exception:
            pass

    digits = re.sub(r"\D", "", text)

    if len(digits) == 9 and digits.startswith("9"):
        digits = "0" + digits

    return digits if digits else text


def normalize_row(row: Dict) -> Dict[str, str]:
    normalized = {}
    for target_key, source_col in SOURCE_COLUMN_MAP.items():
        value = row.get(source_col, "")
        if pd.isna(value):
            normalized[target_key] = ""
        else:
            text = str(value).strip()
            if target_key in ["電話", "緊急連絡人電話"]:
                text = fix_phone(text)
            normalized[target_key] = text
    return normalized


def map_single_value(zh_name: str, value: str) -> str:
    value = str(value or "").strip()
    mapper = VALUE_MAP.get(zh_name)
    return mapper.get(value, value) if mapper else value


def convert_roc_to_ad_if_needed(value: str) -> str:
    text = str(value or "").strip()
    m = re.match(r"^\s*(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})\s*$", text)
    if not m:
        return text
    y = int(m.group(1)) + 1911
    mth = int(m.group(2))
    day = int(m.group(3))
    return f"{y:04d}-{mth:02d}-{day:02d}"


def build_payload(
    row: Dict[str, str],
    token: str,
    convert_birthday_to_ad: bool,
    area_extra_payload: Dict[str, str],
) -> Dict[str, object]:
    merged = {}
    merged.update(FIXED_VALUES)
    merged.update(row)

    payload: Dict[str, object] = {"_token": token}

    for zh_name, field_name in FORM_FIELD_MAP.items():
        value = merged.get(zh_name, "").strip()

        if zh_name in ["生日", "到職日期"]:
            if convert_birthday_to_ad:
                value = convert_roc_to_ad_if_needed(value)
            payload[field_name] = value
            continue

        if zh_name == "角色":
            mapped = map_single_value(zh_name, value)
            payload[field_name] = [mapped] if mapped else []
            continue

        payload[field_name] = map_single_value(zh_name, value)

    service_value = merged.get("服務項目", "").strip()
    items = []
    raw_items = [x.strip() for x in re.split(r"[、,，/]+", service_value) if x.strip()]
    if not raw_items and service_value:
        raw_items = [service_value]

    for item in raw_items:
        mapped = COORDINATOR_ITEM_MAP.get(item)
        if mapped:
            items.append(mapped)
    payload["coordinator_item[]"] = items

    if payload.get("password") and "password_confirmation" not in payload:
        payload["password_confirmation"] = payload["password"]

    for key, value in area_extra_payload.items():
        payload[key] = value

    return payload


def submit_user(session: requests.Session, submit_url: str, payload: Dict[str, object]) -> requests.Response:
    return session.post(submit_url, data=payload, headers=HEADERS, timeout=30, allow_redirects=True)


def extract_error_message(resp: requests.Response) -> str:
    soup = BeautifulSoup(resp.text, "html.parser")
    msgs = []

    for selector in [".alert-danger", ".invalid-feedback", ".help-block", ".text-danger", ".error"]:
        for tag in soup.select(selector):
            txt = tag.get_text(" ", strip=True)
            if txt and txt not in msgs:
                msgs.append(txt)

    for li in soup.select("ul li"):
        txt = li.get_text(" ", strip=True)
        if txt and ("必填" in txt or "錯誤" in txt or "required" in txt.lower()):
            if txt not in msgs:
                msgs.append(txt)

    if msgs:
        return " | ".join(msgs[:10])

    title = soup.title.get_text(strip=True) if soup.title else ""
    return f"回傳表單頁，可能驗證失敗。URL={resp.url} TITLE={title}"


def is_success_response(resp: requests.Response) -> bool:
    if resp.status_code >= 400:
        return False

    normalized_url = resp.url.rstrip("/")
    if normalized_url == USER_LIST_URL:
        return True

    text = resp.text.lower()
    if "<form" in text and 'name="name"' in text and 'name="password"' in text and 'name="_token"' in text:
        return False

    return False


def parse_sheet_row_input(text: str, max_data_rows: int) -> List[int]:
    raw = str(text or "").strip()
    if not raw:
        return []

    result = set()
    parts = [p.strip() for p in raw.split(",") if p.strip()]

    for part in parts:
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start_n = int(start_s.strip())
            end_n = int(end_s.strip())
            if end_n < start_n:
                start_n, end_n = end_n, start_n

            for n in range(start_n, end_n + 1):
                if 2 <= n <= max_data_rows + 1:
                    result.add(n)
        else:
            n = int(part)
            if 2 <= n <= max_data_rows + 1:
                result.add(n)

    return sorted(result)


def get_gspread_worksheet(sheet_id: str, sheet_name: str):
    if gspread is None:
        raise RuntimeError("尚未安裝 gspread，請先 pip install gspread google-auth")

    try:
        gc = gspread.service_account(filename="service_account.json")
    except Exception as e:
        raise RuntimeError(
            f"無法載入 service_account.json：{e}。"
            f"請確認檔案存在於 app 同層目錄，且該帳號已被加入 Google Sheet 共用名單。"
        )

    sh = gc.open_by_key(sheet_id)
    return sh.worksheet(sheet_name)


def read_u_column_value(sheet_id: str, sheet_name: str, row_no: int) -> str:
    ws = get_gspread_worksheet(sheet_id, sheet_name)
    return str(ws.acell(f"U{row_no}").value or "").strip()


def write_import_date_to_u_column(
    sheet_id: str,
    sheet_name: str,
    row_no: int,
    value: str,
) -> None:
    ws = get_gspread_worksheet(sheet_id, sheet_name)
    ws.update_acell(f"U{row_no}", value)


def build_import_mark() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


st.set_page_config(page_title="新人匯入工具", page_icon="🍋", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Space+Grotesk:wght@500;700&display=swap');

:root {
    --lemon:       #F5C518;
    --lemon-dark:  #D4A017;
    --lemon-soft:  #FFFBEA;
    --lemon-mid:   #FFF3C4;
    --charcoal:    #1C1C1E;
    --ink:         #3A3A3C;
    --muted:       #8E8E93;
    --border:      #E5E5EA;
    --surface:     #FFFFFF;
    --success:     #34C759;
    --danger:      #FF3B30;
    --radius:      14px;
    --shadow:      0 2px 16px rgba(0,0,0,0.07);
}

html, body, [class*="css"] {
    font-family: 'Noto Sans TC', sans-serif;
    color: var(--charcoal);
}

#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2rem !important; max-width: 1120px; }

.hero {
    background: linear-gradient(135deg, #FFFDF0 0%, #FFFBEA 100%);
    border: 1.5px solid var(--lemon-mid);
    border-radius: var(--radius);
    padding: 2rem 2.5rem 1.6rem;
    margin-bottom: 2rem;
    display: flex;
    align-items: center;
    gap: 1.2rem;
    box-shadow: 0 2px 12px rgba(245,197,24,0.10);
}
.hero-emoji { font-size: 3rem; line-height: 1; }
.hero-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.9rem;
    font-weight: 700;
    color: var(--charcoal);
    margin: 0;
    letter-spacing: -0.5px;
}
.hero-sub { color: var(--ink); font-size: 0.88rem; margin-top: 0.3rem; opacity: 0.75; }

.step-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--lemon-mid);
    border: 1.5px solid var(--lemon);
    border-radius: 30px;
    padding: 0.28rem 0.9rem;
    font-size: 0.78rem;
    font-weight: 700;
    color: var(--charcoal);
    margin-bottom: 0.9rem;
    letter-spacing: 0.02em;
    text-transform: uppercase;
}
.step-num {
    background: var(--lemon);
    border-radius: 50%;
    width: 20px;
    height: 20px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 0.72rem;
    font-weight: 700;
}

.badge-ok {
    display: inline-block;
    background: #D1FAE5; color: #065F46;
    border-radius: 6px; padding: 0.18rem 0.7rem;
    font-size: 0.8rem; font-weight: 600;
}
.badge-err {
    display: inline-block;
    background: #FEE2E2; color: #991B1B;
    border-radius: 6px; padding: 0.18rem 0.7rem;
    font-size: 0.8rem; font-weight: 600;
}
.badge-warn {
    display: inline-block;
    background: var(--lemon-mid); color: #92400E;
    border-radius: 6px; padding: 0.18rem 0.7rem;
    font-size: 0.8rem; font-weight: 600;
}

.info-strip {
    background: var(--lemon-soft);
    border-left: 4px solid var(--lemon);
    border-radius: 0 8px 8px 0;
    padding: 0.6rem 1rem;
    font-size: 0.84rem;
    color: var(--ink);
    margin-bottom: 0.8rem;
}

.stat-row { display: flex; gap: 1rem; margin-top: 1rem; }
.stat-box {
    flex: 1;
    background: var(--lemon-soft);
    border: 1.5px solid var(--lemon-mid);
    border-radius: 10px;
    padding: 0.9rem 1.2rem;
    text-align: center;
}
.stat-num { font-size: 2rem; font-weight: 700; font-family: 'Space Grotesk', sans-serif; }
.stat-lbl { font-size: 0.78rem; color: var(--muted); margin-top: 0.1rem; }
.stat-ok  .stat-num { color: var(--success); }
.stat-err .stat-num { color: var(--danger); }
.stat-tot .stat-num { color: var(--charcoal); }

.stButton > button {
    background: var(--lemon) !important;
    color: var(--charcoal) !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    font-family: 'Noto Sans TC', sans-serif !important;
    padding: 0.45rem 1.2rem !important;
    transition: background 0.18s, transform 0.12s !important;
    box-shadow: 0 2px 8px rgba(245,197,24,0.3) !important;
}
.stButton > button:hover {
    background: var(--lemon-dark) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="primary"] {
    background: var(--charcoal) !important;
    color: var(--lemon) !important;
    box-shadow: 0 2px 12px rgba(28,28,30,0.25) !important;
}
.stButton > button[kind="primary"]:hover {
    background: #2C2C2E !important;
}

.stSelectbox > div > div,
.stTextInput > div > div > input,
.stNumberInput > div > div > input {
    border-radius: 8px !important;
    border: 1.5px solid var(--border) !important;
}

.streamlit-expanderHeader {
    font-weight: 600 !important;
    font-size: 0.93rem !important;
}

.stDataFrame { border-radius: 10px !important; overflow: hidden; }
.stProgress > div > div > div > div { background: var(--lemon) !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="hero-emoji">🍋</div>
  <div>
    <div class="hero-title">新人系統建檔工具</div>
    <div class="hero-sub">登入後台 → 選擇地區 → 讀取 Google Sheet → 選擇列號 → 批次匯入 → 成功後回寫 U 欄匯入日</div>
  </div>
</div>
""", unsafe_allow_html=True)

accounts = load_accounts()
for key in ["session", "logged_in_email", "sheet_df", "form_info"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "logged_in_email" else ""

if "area_name" not in st.session_state:
    st.session_state.area_name = list(AREA_CONFIG.keys())[0]

if "selected_rows_text" not in st.session_state:
    st.session_state.selected_rows_text = "3,5"

if "selected_sheet_rows" not in st.session_state:
    st.session_state.selected_sheet_rows = []

st.markdown('<div class="step-pill"><span class="step-num">1</span>選擇地區</div>', unsafe_allow_html=True)

area_name = st.selectbox("選擇地區", list(AREA_CONFIG.keys()), key="area_name")
area_conf = AREA_CONFIG[area_name]

st.markdown(
    f'<div class="info-strip">📍 目前地區：<strong>{area_name}</strong>　'
    f'工作表：<strong>{area_conf.get("sheet_name", "")}</strong></div>',
    unsafe_allow_html=True,
)

st.markdown("<hr>", unsafe_allow_html=True)

st.markdown('<div class="step-pill"><span class="step-num">2</span>後台登入</div>', unsafe_allow_html=True)

login_status_placeholder = st.empty()

with st.expander("展開登入設定", expanded=st.session_state.session is None):
    if accounts:
        account_name = st.selectbox("選擇帳號", list(accounts.keys()))
        default_email = accounts[account_name]["email"]
        default_password = accounts[account_name]["password"]
    else:
        default_email = ""
        default_password = ""

    c1, c2, c3 = st.columns([3, 3, 1.4])
    with c1:
        email = st.text_input("Email", value=default_email, placeholder="admin@example.com")
    with c2:
        password = st.text_input("Password", value=default_password, type="password", placeholder="••••••••")
    with c3:
        st.write("")
        st.write("")
        login_clicked = st.button("🔐 登入後台", use_container_width=True)

    if login_clicked:
        with st.spinner("登入中…"):
            try:
                sess = login_backend(email, password)
                form_info = inspect_user_add_form(sess)
                st.session_state.session = sess
                st.session_state.logged_in_email = email
                st.session_state.form_info = form_info
                st.success(f"✅ 登入成功：**{email}**")
                st.caption(f"Submit URL: `{form_info['submit_url']}`")
            except Exception as e:
                st.error(f"❌ {e}")

if st.session_state.session:
    login_status_placeholder.markdown(
        f'<span class="badge-ok">✓ 已登入　{st.session_state.logged_in_email}</span>',
        unsafe_allow_html=True,
    )
else:
    login_status_placeholder.markdown(
        '<span class="badge-warn">尚未登入</span>',
        unsafe_allow_html=True,
    )

st.markdown("<hr>", unsafe_allow_html=True)

st.markdown('<div class="step-pill"><span class="step-num">3</span>讀取 Google Sheet</div>', unsafe_allow_html=True)

st.markdown(
    f'<div class="info-strip">📋 工作表：<strong>{area_conf.get("sheet_name", "")}</strong>'
    f'　　ID：<code>{area_conf.get("sheet_id", "")}</code></div>',
    unsafe_allow_html=True,
)

col_btn, col_status = st.columns([1.5, 5])
with col_btn:
    fetch_clicked = st.button("📥 讀取資料", use_container_width=True)
with col_status:
    sheet_status = st.empty()

if fetch_clicked:
    with st.spinner("讀取中…"):
        try:
            df = fetch_sheet(area_conf["sheet_id"], area_conf["sheet_name"])
            st.session_state.sheet_df = df
            sheet_status.markdown(
                f'<span class="badge-ok">✓ 已讀取 {len(df)} 筆資料</span>',
                unsafe_allow_html=True,
            )
        except Exception as e:
            sheet_status.markdown(
                f'<span class="badge-err">✗ 讀取失敗：{e}</span>',
                unsafe_allow_html=True,
            )

df = st.session_state.sheet_df
if df is not None:
    missing = validate_sheet_columns(df)
    if missing:
        st.error("Google Sheet 缺少欄位：" + "、".join(missing))
    else:
        st.markdown('<span class="badge-ok">✓ 欄位檢查通過</span>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

st.markdown('<div class="step-pill"><span class="step-num">4</span>選擇列號與預覽</div>', unsafe_allow_html=True)

df = st.session_state.sheet_df
if df is None:
    st.markdown('<div class="info-strip">請先完成步驟 3 讀取資料。</div>', unsafe_allow_html=True)
else:
    total_rows = len(df)
    st.caption(f"資料總列數（不含標題）：**{total_rows}**")

    selected_rows_text = st.text_input(
        "請輸入要匯入的 Google Sheet 列號",
        key="selected_rows_text",
        help="可輸入：3,5 或 3-5,8,10-12",
        placeholder="例如：3,5,8-10",
    )

    try:
        selected_sheet_rows = parse_sheet_row_input(selected_rows_text, total_rows)
        st.session_state.selected_sheet_rows = selected_sheet_rows
    except Exception:
        selected_sheet_rows = []
        st.session_state.selected_sheet_rows = []
        st.error("列號格式錯誤，請輸入如：3,5 或 3-5,8")

    if not selected_sheet_rows:
        st.warning("目前沒有可匯入的列")
    else:
        row_indexes = [row_no - 2 for row_no in selected_sheet_rows]
        selected_df = df.iloc[row_indexes].copy()
        preview_rows = [normalize_row(r.to_dict()) for _, r in selected_df.iterrows()]
        preview_df = pd.DataFrame(preview_rows)
        preview_df.insert(0, "Sheet列號", selected_sheet_rows)
        st.caption(f"已選取 **{len(preview_rows)}** 筆：{selected_sheet_rows}")
        st.dataframe(preview_df, use_container_width=True)

st.markdown("<hr>", unsafe_allow_html=True)

with st.expander("🔍 進階：表單欄位對照（除錯用）", expanded=False):
    form_info = st.session_state.form_info
    if not form_info:
        st.info("請先登入後台")
    else:
        st.markdown("**後台表單欄位**")
        st.json(form_info["field_names"], expanded=False)
        st.markdown("**欄位 Mapping**")
        st.json(FORM_FIELD_MAP, expanded=False)
        st.markdown("**目前地區 extra_payload**")
        st.json(area_conf.get("extra_payload", {}), expanded=False)

st.markdown("<hr>", unsafe_allow_html=True)

st.markdown('<div class="step-pill"><span class="step-num">5</span>開始匯入</div>', unsafe_allow_html=True)

st.markdown(
    '<div class="info-strip">📝 預設規則：U 欄寫入日期＋時間；若 U 欄已有值，將自動略過該列不匯入。</div>',
    unsafe_allow_html=True,
)

import_clicked = st.button("🚀 開始匯入", type="primary", use_container_width=False)

if import_clicked:
    df = st.session_state.sheet_df
    session = st.session_state.session
    form_info = st.session_state.form_info
    selected_sheet_rows = st.session_state.get("selected_sheet_rows", [])

    if df is None:
        st.error("請先讀取 Google Sheet（步驟 3）")
    elif session is None or form_info is None:
        st.error("請先登入後台（步驟 2）")
    elif not selected_sheet_rows:
        st.error("請先輸入要匯入的列號（步驟 4）")
    else:
        missing = validate_sheet_columns(df)
        if missing:
            st.error("Google Sheet 缺少欄位：" + "、".join(missing))
        else:
            results = []
            total = max(len(selected_sheet_rows), 1)
            progress_bar = st.progress(0)
            status_text = st.empty()

            for idx, sheet_row_no in enumerate(selected_sheet_rows, start=1):
                row = df.iloc[sheet_row_no - 2]
                row_dict = normalize_row(row.to_dict())

                u_before = ""
                skip_reason = ""
                u_read_error = ""

                try:
                    u_before = read_u_column_value(
                        area_conf["sheet_id"],
                        area_conf["sheet_name"],
                        sheet_row_no,
                    )
                    if u_before:
                        skip_reason = f"U欄已有值：{u_before}"
                except Exception as e:
                    u_read_error = str(e)

                if skip_reason:
                    results.append({
                        "地區": area_name,
                        "Sheet列號": sheet_row_no,
                        "使用者名稱": row_dict.get("使用者名稱", ""),
                        "email": row_dict.get("email", ""),
                        "電話": row_dict.get("電話", ""),
                        "緊急連絡人電話": row_dict.get("緊急連絡人電話", ""),
                        "到職日期": row_dict.get("到職日期", ""),
                        "U欄原值": u_before,
                        "U欄寫入": "",
                        "結果": "⏭️ 略過",
                        "訊息": skip_reason,
                    })
                    progress_bar.progress(idx / total)
                    continue

                payload = build_payload(
                    row_dict,
                    form_info["_token"],
                    convert_birthday_to_ad=convert_birthday_to_ad,
                    area_extra_payload=area_conf.get("extra_payload", {}),
                )

                with st.expander(f"第 {sheet_row_no} 列 payload", expanded=False):
                    st.json(payload)

                try:
                    resp = submit_user(session, form_info["submit_url"], payload)
                    success = is_success_response(resp)
                    message = "成功" if success else f"失敗 HTTP {resp.status_code} / {extract_error_message(resp)}"
                except Exception as e:
                    success = False
                    message = str(e)

                u_written = ""
                if success:
                    mark_value = build_import_mark()

                    try:
                        write_import_date_to_u_column(
                            area_conf["sheet_id"],
                            area_conf["sheet_name"],
                            sheet_row_no,
                            mark_value,
                        )
                        u_written = mark_value
                    except Exception as e:
                        if u_read_error:
                            message = f"{message} / U欄讀取失敗：{u_read_error} / U欄寫入失敗：{e}"
                        else:
                            message = f"{message} / U欄寫入失敗：{e}"

                results.append({
                    "地區": area_name,
                    "Sheet列號": sheet_row_no,
                    "使用者名稱": row_dict.get("使用者名稱", ""),
                    "email": row_dict.get("email", ""),
                    "電話": row_dict.get("電話", ""),
                    "緊急連絡人電話": row_dict.get("緊急連絡人電話", ""),
                    "到職日期": row_dict.get("到職日期", ""),
                    "U欄原值": u_before,
                    "U欄寫入": u_written,
                    "結果": "✅ 成功" if success else "❌ 失敗",
                    "訊息": message,
                })

                name = row_dict.get("使用者名稱", "")
                status_text.markdown(
                    f'<span class="badge-warn">處理中：{area_name}｜第 {sheet_row_no} 列｜{name}</span>',
                    unsafe_allow_html=True,
                )
                progress_bar.progress(idx / total)

            status_text.empty()
            result_df = pd.DataFrame(results)

            ok_count = (result_df["結果"] == "✅ 成功").sum()
            err_count = (result_df["結果"] == "❌ 失敗").sum()
            skip_count = (result_df["結果"] == "⏭️ 略過").sum()

            st.markdown(f"""
            <div class="stat-row">
              <div class="stat-box stat-tot">
                <div class="stat-num">{len(results)}</div>
                <div class="stat-lbl">處理總筆數</div>
              </div>
              <div class="stat-box stat-ok">
                <div class="stat-num">{ok_count}</div>
                <div class="stat-lbl">成功</div>
              </div>
              <div class="stat-box stat-err">
                <div class="stat-num">{err_count}</div>
                <div class="stat-lbl">失敗</div>
              </div>
              <div class="stat-box">
                <div class="stat-num">{skip_count}</div>
                <div class="stat-lbl">略過</div>
              </div>
            </div>
            <br>
            """, unsafe_allow_html=True)

            st.dataframe(result_df, use_container_width=True)

            csv_bytes = result_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📄 下載結果 CSV",
                data=csv_bytes,
                file_name=f"import_result_{area_name}.csv",
                mime="text/csv",
            )
