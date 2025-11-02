# app.py — 키오스크 모드: 워드클라우드만 풀화면 표출(모든 UI 제거)
import random, re
from collections import Counter
from pathlib import Path

import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from streamlit_autorefresh import st_autorefresh

# ─────────────────────────────
# 기본 설정
# ─────────────────────────────
st.set_page_config(layout="wide", page_title="ChocoCloud", page_icon="🍫")

# 자동 새로고침 (부하 고려해 10~30초 권장)
AUTO_REFRESH_MS = 10000
st_autorefresh(interval=AUTO_REFRESH_MS, key="refresh")

# ─────────────────────────────
# 키오스크 CSS: 모든 UI 숨김 + 배경/여백 제거
# ─────────────────────────────
st.markdown("""
<style>
  html, body { height: 100%; background: #7F3100; overflow: hidden; }
  /* 스트림릿 UI 전부 숨김 */
  header, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
  [data-testid="stStatusWidget"], [data-testid="stAppDeployButton"],
  .viewerBadge_container__1QSob, .stActionButtonIcon, .st-emotion-cache-1wbqy5l {
    display: none !important;
  }
  /* 사이드바 제거 */
  [data-testid="stSidebar"], section[data-testid="stSidebar"] {
    display: none !important;
  }
  /* 컨테이너 여백/마진 제거 */
  .block-container { padding: 0 !important; margin: 0 !important; }
  [data-testid="stAppViewContainer"] > .main { padding: 0 !important; }
  [data-testid="stAppViewContainer"] {
    background: #7F3100 !important;
  }
  /* 차트 주변 그림자/라운드 제거 */
  .stPlotlyChart, .stImage, .stMarkdown, .stPlot {
    box-shadow: none !important;
    border-radius: 0 !important;
    background: #7F3100 !important;
  }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────
# 팔레트 & 폰트
# ─────────────────────────────
MY_COLORS = ["#FF7AB6", "#FFA442", "#FFF755", "#96FF73", "#59D0FF", "#CF9BFF", "#65FFEB"]
def random_color_func(*args, **kwargs):
    return random.choice(MY_COLORS)

def pick_font():
    candidates = [
        "fonts/GabiaDunn.otf",                               # 프로젝트 동봉(원하는 폰트로 교체 가능)
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",   # Linux 컨테이너
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        r"C:\Windows\Fonts\malgun.ttf",                      # Windows
        r"C:\Windows\Fonts\NanumGothic.ttf",
        "fonts/NotoSansKR-Regular.otf",
        "fonts/NotoSansCJKkr-Regular.otf",
        "fonts/NanumGothic.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    # 폰트가 없으면 영어 폰트로 렌더되며 한글이 깨질 수 있음
    return None

FONT_PATH = pick_font()

# ─────────────────────────────
# 구글 시트 인증 (Secrets → 파일 순)
# ─────────────────────────────
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    secrets = None
    try:
        secrets = st.secrets.get("gcp_service_account", None)
    except Exception:
        secrets = None
    if secrets:
        fixed = dict(secrets)
        if "private_key" in fixed and isinstance(fixed["private_key"], str):
            fixed["private_key"] = fixed["private_key"].replace("\\n", "\n").strip()
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(fixed, scopes=scope)
        return gspread.authorize(credentials)
    if Path("service_account.json").exists():
        credentials = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
        return gspread.authorize(credentials)
    st.stop()  # 키오스크 모드에서는 메시지 노출 안 함

client = get_gspread_client()

# ─────────────────────────────
# 시트/컬럼 설정
# ─────────────────────────────
SPREADSHEET_ID = "1ysnVySqyDXNxpYc-vULP887GUDVPHXMFdRoZoZW4DTU"
SHEET_A = "answerA"  # BEFORE
SHEET_B = "answerB"  # AFTER
TARGET_COL = "의미 정리 함수"

# ─────────────────────────────
# 데이터 로딩 & 토큰 카운팅
# ─────────────────────────────
def clean_columns(columns: pd.Index) -> pd.Index:
    cols = pd.Index(columns)
    cols = cols.str.replace("\u200b", "", regex=False).str.replace("\ufeff", "", regex=False).str.strip()
    return cols

def find_target_column(columns: pd.Index, target_name: str):
    if target_name in columns:
        return target_name
    for c in columns:
        if target_name.replace(" ", "") == c.replace(" ", ""):
            return c
    return None

def get_phrase_counts(worksheet_name: str, target_col_name: str = TARGET_COL):
    ws = client.open_by_key(SPREADSHEET_ID).worksheet(worksheet_name)
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    df.columns = clean_columns(df.columns)

    col = find_target_column(df.columns, target_col_name)
    if col is None:
        return Counter()

    series = df[col].dropna().astype(str)

    phrase_list = []
    for row in series:
        if any(sep in row for sep in [",", "，", ";", "\n"]):
            tmp = re.sub(r"[，;\n]", ",", row)
            pieces = tmp.split(",")
        else:
            pieces = [row]
        for piece in pieces:
            t = piece.strip()
            if len(t) >= 2 and re.search(r"[가-힣A-Za-z0-9]", t):
                phrase_list.append(t)

    return Counter(phrase_list)

# ─────────────────────────────
# 렌더: 워드클라우드(제목/여백 없이)  ⬅️ 이 함수만 교체
# ─────────────────────────────
def render_wordcloud_only(counts: Counter, *, bg="#7F3100"):
    if not counts:
        fig, ax = plt.subplots(figsize=(10, 14), facecolor=bg)  # ⬅️ 세로 더 길게
        ax.axis("off")
        st.pyplot(fig, use_container_width=True)
        return

    wc = WordCloud(
        font_path=FONT_PATH,
        background_color=bg,
        width=900, height=1100,         # ⬅️ 세로 해상도 증가
        color_func=random_color_func,
        min_font_size=5, max_font_size=200,
        prefer_horizontal=0.95
    ).generate_from_frequencies(counts)

    fig, ax = plt.subplots(figsize=(10, 12), facecolor=bg)      # ⬅️ 세로 더 길게
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    st.pyplot(fig, use_container_width=True)

# ─────────────────────────────
# 레이아웃: 좌(B) | 중앙 흰색 구분선 오버레이 | 우(A)
# ─────────────────────────────
# 두 컬럼은 완전히 같은 폭(1:1)
col_left, col_right = st.columns(2, gap="small")

with col_left:
    countsB = get_phrase_counts(SHEET_B, TARGET_COL)
    render_wordcloud_only(countsB, bg="#7F3100")

with col_right:
    countsA = get_phrase_counts(SHEET_A, TARGET_COL)
    render_wordcloud_only(countsA, bg="#7F3100")
# ─────────────────────────────
# 중앙 흰색 구분선 (진짜로 워드클라우드 위에 고정 표시)
# ─────────────────────────────
st.markdown("""
<style>
/* 워드클라우드보다 위에 오도록 전역 고정 */
.center-divider-real {
    position: fixed !important;
    top: 0;
    bottom: 0;
    left: 50%;
    width: 2px;
    background: #ffffff;    /* 선 색상 */
    opacity: 0.8;           /* 투명도 */
    transform: translateX(-50%);
    z-index: 999999 !important;   /* Streamlit 모든 레이어 위 */
    pointer-events: none;
}
</style>
<div class="center-divider-real"></div>
""", unsafe_allow_html=True)
