# app.py — 최신 Streamlit + 프레젠테이션 모드 토글 통합본
from streamlit.components.v1 import html  # ✅ 전체화면 JS 버튼용
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

# =========================
# 🔧 기본 설정
# =========================
st.set_page_config(layout="wide", page_title="ChocoCloud", page_icon="🍫")

# 필요 시 자동 새로고침(초). 배포 시 10~30초 권장.
AUTO_REFRESH_MS = 10000
st_autorefresh(interval=AUTO_REFRESH_MS, key="refresh")

# (옵션) 커스텀 스타일
try:
    with open("./styles/styles.css", "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except:
    pass

DEBUG = st.sidebar.checkbox("디버그 모드", value=False)

# =========================
# 🎬 프레젠테이션 모드 (UI 최소화 + 전체화면)
# =========================
def apply_minimal_css(hide_sidebar: bool = False):
    css = """
    <style>
      header, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
      .block-container { padding-top: 0 !important; padding-bottom: 0 !important; padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
    </style>
    """
    if hide_sidebar:
        css += """
        <style>
          [data-testid="stSidebar"], section[data-testid="stSidebar"] { display: none !important; }
        </style>
        """
    st.markdown(css, unsafe_allow_html=True)

def apply_full_window_css():
    """
    Streamlit 뷰 컨테이너를 화면에 고정해 '창 채우기' 효과를 만듦.
    (진짜 브라우저 전체화면은 아니지만, 시각적으로 동일하게 느껴짐)
    """
    st.markdown("""
    <style>
      html, body { margin:0; padding:0; height:100%; overflow:hidden; background:#000; }
      /* 페이지 스크롤 제거 및 컨테이너를 창 전체로 확대 */
      [data-testid="stAppViewContainer"] > .main {
        padding: 0 !important;
      }
      [data-testid="stAppViewContainer"] {
        position: fixed !important;
        top: 0; left: 0; right: 0; bottom: 0;
        width: 100vw; height: 100vh;
        background: #000; /* 가장자리 빛샘 방지 */
        overflow: hidden !important;
      }
      .block-container { margin: 0 !important; }
    </style>
    """, unsafe_allow_html=True)

def presentation_controls(default_minimal=False):
    with st.container():
        c1, c2, c3 = st.columns([0.7, 0.9, 1.4])
        with c1:
            minimal = st.checkbox("🎬 프레젠테이션 모드", value=default_minimal,
                                  help="헤더/푸터/툴바/여백을 숨깁니다.")
        with c2:
            hide_sb = st.checkbox("사이드바 숨기기", value=False,
                                  help="체크 시 사이드바도 숨깁니다. 해제는 새로고침 또는 주소창 view로 재진입.")
        with c3:
            fullwin = st.checkbox("⛶ 창 채우기(가짜 전체화면)", value=False,
                                  help="브라우저 전체화면 대신 앱이 창을 가득 채우도록 CSS로 고정합니다.")

        st.caption("💡 진짜 전체화면은 단축키를 쓰세요 — Windows: F11, macOS: ⌃⌘F")

    if minimal:
        apply_minimal_css(hide_sidebar=hide_sb)
    if fullwin:
        apply_full_window_css()


# ✅ 컨트롤 표시 (레이아웃 렌더 전에 호출)
presentation_controls(default_minimal=False)

# =========================
# 🎨 팔레트 & 폰트
# =========================
MY_COLORS = ["#FF7AB6", "#FFA442", "#FFF755", "#96FF73", "#59D0FF", "#CF9BFF", "#65FFEB"]
def random_color_func(*args, **kwargs):
    return random.choice(MY_COLORS)

def pick_font():
    """배포/로컬 모두 고려한 한글 폰트 후보."""
    candidates = [
        "fonts/GabiaDunn.otf",                    # 프로젝트 동봉 (파일명 단순화 권장)
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",         # Linux 컨테이너(배포)
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        r"C:\Windows\Fonts\malgun.ttf",                            # Windows
        r"C:\Windows\Fonts\NanumGothic.ttf",
        "fonts/NotoSansKR-Regular.otf",                            # 프로젝트 동봉
        "fonts/NotoSansCJKkr-Regular.otf",
        "fonts/NanumGothic.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    st.warning("한글 폰트를 찾지 못했습니다. fonts/에 NotoSansKR 같은 한글 폰트를 추가해 주세요.")
    return None

FONT_PATH = pick_font()

# =========================
# 🔐 구글 시트 인증 (secrets → 파일 순, 안전 가드)
# =========================
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # 1) st.secrets 시도 (배포/로컬 둘 다 가능)
    secrets = None
    try:
        secrets = st.secrets.get("gcp_service_account", None)
    except Exception:
        secrets = None
    if secrets:
        # 🔧 private_key 개행 복원 (\\n → \n) — Secrets 입력 방식에 상관없이 안전
        fixed = dict(secrets)
        if "private_key" in fixed and isinstance(fixed["private_key"], str):
            fixed["private_key"] = fixed["private_key"].replace("\\n", "\n").strip()
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(fixed, scopes=scope)
        return gspread.authorize(credentials)

    # 2) 로컬: service_account.json 파일
    if Path("service_account.json").exists():
        credentials = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
        return gspread.authorize(credentials)

    st.error(
        "구글 서비스계정 인증정보가 없습니다.\n"
        "- 로컬: 프로젝트 루트에 service_account.json 파일을 두세요.\n"
        "- 배포: Settings → Secrets에 [gcp_service_account] JSON을 넣으세요."
    )
    st.stop()

client = get_gspread_client()

# =========================
# 📄 시트/컬럼 설정
# =========================
SPREADSHEET_ID = "1ysnVySqyDXNxpYc-vULP887GUDVPHXMFdRoZoZW4DTU"
SHEET_A = "answerA"
SHEET_B = "answerB"
TARGET_COL = "의미 정리 함수"   # 쉼표(,)로 구분된 키워드 컬럼

# =========================
# 🧼 유틸: 컬럼 정리/토큰 카운팅/렌더
# =========================
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
        return Counter(), df.columns.tolist()

    series = df[col].dropna().astype(str)

    # 쉼표/중국어 쉼표/세미콜론/줄바꿈 등 구분자 대응
    phrase_list = []
    for row in series:
        if any(sep in row for sep in [",", "，", ";", "\n"]):
            tmp = re.sub(r"[，;\n]", ",", row)
            pieces = tmp.split(",")
        else:
            pieces = [row]
        for piece in pieces:
            t = piece.strip()
            # 너무 짧거나 기호-only 제외
            if len(t) >= 2 and re.search(r"[가-힣A-Za-z0-9]", t):
                phrase_list.append(t)

    counts = Counter(phrase_list)
    return counts, df.columns.tolist()

def render_wordcloud(title: str, counts: Counter, bg="#7F3100"):
    if not counts:
        st.error(f"[{title}] 유효 토큰이 없습니다. 시트의 '{TARGET_COL}' 컬럼을 확인하세요.")
        return
    wc = WordCloud(
        font_path=FONT_PATH,
        background_color=bg,
        width=1200, height=700,
        color_func=random_color_func,
        min_font_size=5, max_font_size=200
    ).generate_from_frequencies(counts)

    st.subheader(title)
    fig, ax = plt.subplots(figsize=(12, 9), facecolor=bg)
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    st.pyplot(fig, use_container_width=True)

# =========================
# 🔀 라우팅: ?view=answerA / ?view=answerB / (기본=홈)
# =========================
query = st.query_params  # ✅ 최신 Streamlit 방식
view = (query.get("view", "home") or "home").lower()

# 상단 내비게이션(새 탭으로 열기)
st.markdown(
    """
    <div style="display:flex; gap:12px; flex-wrap:wrap;">
      <a href="?view=answerA" target="_blank" style="text-decoration:none; padding:8px 12px; background:#111; color:#fff; border-radius:8px;">🧾 answerA 새 탭</a>
      <a href="?view=answerB" target="_blank" style="text-decoration:none; padding:8px 12px; background:#111; color:#fff; border-radius:8px;">🧾 answerB 새 탭</a>
      <a href="?view=both"     style="text-decoration:none; padding:8px 12px; background:#444; color:#fff; border-radius:8px;">🪟 한 화면에 둘 다</a>
    </div>
    """,
    unsafe_allow_html=True
)

# =========================
# 🖥️ 뷰 렌더링
# =========================
if view == "answera":
    st.title("📄 answerA — 실시간 워드클라우드")
    countsA, colsA = get_phrase_counts(SHEET_A, TARGET_COL)
    if DEBUG:
        st.write("Columns(A):", list(colsA))
        st.write("Top20(A):", countsA.most_common(20))
    render_wordcloud(f"{SHEET_A} 워드클라우드", countsA)

elif view == "answerb":
    st.title("📄 answerB — 실시간 워드클라우드")
    countsB, colsB = get_phrase_counts(SHEET_B, TARGET_COL)
    if DEBUG:
        st.write("Columns(B):", list(colsB))
        st.write("Top20(B):", countsB.most_common(20))
    render_wordcloud(f"{SHEET_B} 워드클라우드", countsB)

else:
    # 홈(기본) — 두 워드클라우드 나란히 표시 (AFTER 오른쪽, BEFORE 왼쪽)
    st.markdown("""
    <div style="text-align:center; font-size:28px; font-weight:700; margin-bottom:0.5rem;">
      🍫 ChocoCloud — 워드클라우드 대시보드
    </div>
    <p style="text-align:center; color:#bbb;">비포 / 에프터 리뷰를 한 화면에 비교해보세요.</p>
    """, unsafe_allow_html=True)

    # 배경색을 통일시키고 두 워드클라우드를 하나의 영역처럼
    container = st.container()
    with container:
        st.markdown("""
        <div style="display:flex; flex-direction:row; justify-content:center; align-items:stretch;
                    width:100%; background-color:#7F3100; padding:0; margin:0;">
        """, unsafe_allow_html=True)

        # ✅ 왼쪽 = AFTER (answerB)
        col_left, col_right = st.columns([1, 1], gap="small")
        with col_left:
            st.markdown(
                "<h2 style='text-align:center; color:white; margin-top:0;'>에프터 리뷰</h2>",
                unsafe_allow_html=True,
            )
            countsB, colsB = get_phrase_counts(SHEET_B, TARGET_COL)
            if DEBUG:
                st.write("Columns(B):", list(colsB))
                st.write("Top20(B):", countsB.most_common(20))
            render_wordcloud(f"{SHEET_B}", countsB)

        # ✅ 오른쪽 = BEFORE (answerA)
        with col_right:
            st.markdown(
                "<h2 style='text-align:center; color:white; margin-top:0;'>비포 리뷰</h2>",
                unsafe_allow_html=True,
            )
            countsA, colsA = get_phrase_counts(SHEET_A, TARGET_COL)
            if DEBUG:
                st.write("Columns(A):", list(colsA))
                st.write("Top20(A):", countsA.most_common(20))
            render_wordcloud(f"{SHEET_A}", countsA)

        st.markdown("</div>", unsafe_allow_html=True)

