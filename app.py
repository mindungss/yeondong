"""
치안 과학기술 동향 분석 플랫폼
Korean Policing Science & Technology Trend System
Version 1.0 | 경찰청 R&D 기획 지원 전문 시스템
"""

import streamlit as st
import pandas as pd
import json
import os
import re
import math
from datetime import datetime, timedelta, timezone
from collections import Counter

# ─────────────────────────────────────────────
# 0. 페이지 설정 (가장 먼저 호출해야 함)
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="치안 과학기술 동향 | KIPOT",
    page_icon="🚔",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://www.kipot.or.kr",
        "About": "치안 과학기술 R&D 동향 분석 플랫폼 v1.0 | Powered by KIPOT"
    }
)

# ─────────────────────────────────────────────
# 1. 전역 CSS 스타일
# ─────────────────────────────────────────────
st.markdown("""
<style>
  .issue-card { background:#fff; border:1px solid #e5e7eb; border-left:3px solid #ef4444; border-radius:6px; padding:0.85rem 1rem; margin-bottom:0.6rem; }
  .issue-card .card-title { color:#111827; font-weight:600; font-size:0.93rem; margin-bottom:0.2rem; line-height:1.5; }
  .issue-card .card-meta  { color:#6b7280; font-size:0.75rem; }
  .issue-card .card-body  { color:#374151; font-size:0.85rem; line-height:1.65; margin-top:0.4rem; }
  .tech-card { background:#fff; border:1px solid #e5e7eb; border-left:3px solid #10b981; border-radius:6px; padding:0.85rem 1rem; margin-bottom:0.6rem; }
  .tech-card .card-title { color:#111827; font-weight:600; font-size:0.93rem; margin-bottom:0.2rem; line-height:1.5; }
  .tech-card .card-meta  { color:#6b7280; font-size:0.75rem; }
  .tech-card .card-body  { color:#374151; font-size:0.85rem; line-height:1.65; margin-top:0.4rem; }
  .trl-badge { display:inline-block; background:#f3f4f6; color:#374151; border:1px solid #d1d5db; border-radius:4px; padding:1px 7px; font-size:0.7rem; font-weight:600; margin-left:0.4rem; }
  .severity-high   { display:inline-block; background:#fef2f2; color:#b91c1c; border:1px solid #fecaca; border-radius:4px; padding:1px 7px; font-size:0.7rem; font-weight:600; }
  .severity-medium { display:inline-block; background:#fffbeb; color:#b45309; border:1px solid #fde68a; border-radius:4px; padding:1px 7px; font-size:0.7rem; font-weight:600; }
  .severity-low    { display:inline-block; background:#f0fdf4; color:#15803d; border:1px solid #bbf7d0; border-radius:4px; padding:1px 7px; font-size:0.7rem; font-weight:600; }
  .domain-tag { display:inline-block; background:#f3f4f6; color:#374151; border:1px solid #e5e7eb; border-radius:4px; padding:1px 8px; font-size:0.72rem; margin-right:0.25rem; margin-bottom:0.25rem; }
  .section-divider { display:flex; align-items:center; margin:1.4rem 0 0.8rem; }
  .section-divider .divider-label { font-size:0.8rem; font-weight:600; color:#374151; white-space:nowrap; padding-right:0.8rem; }
  .section-divider::after { content:""; flex:1; border-top:1px solid #e5e7eb; }
  .progress-outer { background:#f3f4f6; border-radius:4px; height:6px; overflow:hidden; margin:4px 0 10px; }
  .progress-inner { height:100%; border-radius:4px; }
  .sim-bar-outer { background:#f3f4f6; border-radius:4px; height:14px; overflow:hidden; }
  .sim-bar-inner { height:100%; border-radius:4px; display:flex; align-items:center; padding-left:6px; font-size:0.68rem; font-weight:600; color:white; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 2. 데이터 로더
# ─────────────────────────────────────────────
DATA_PATH = "data/trend_data.json"

@st.cache_data(ttl=300)
def load_trend_data() -> dict:
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def get_available_dates(data: dict) -> list:
    dates = sorted(data.keys(), reverse=True)
    return dates

def get_domain_stats(data: dict, date: str) -> dict:
    domains = [
        "🤖 AI/머신러닝 기반 치안",
        "📹 영상분석·CCTV·드론",
        "🔐 디지털포렌식·사이버수사",
        "🧬 과학수사·감식·법과학",
        "📜 정책·법·제도",
        "🌐 국제 치안",
        "🚓 신종 범죄"
    ]
    stats = {d: 0 for d in domains}
    if date in data:
        day = data[date]
        all_items = day.get("issues", []) + day.get("technologies", [])
        for item in all_items:
            d = item.get("domain", "")
            if d in stats:
                stats[d] += 1
    return stats

def severity_label(s: str) -> str:
    m = {"high": "🔴 긴급", "medium": "🟡 주의", "low": "🟢 정보"}
    return m.get(s, "⚪ 미분류")

def trl_color(trl: int) -> str:
    if trl <= 3: return "#e74c3c"
    if trl <= 6: return "#f39c12"
    return "#27ae60"

def compute_similarity(query: str, text: str) -> float:
    """단순 키워드 기반 유사도 계산 (한국어 토큰)"""
    def tokenize(s):
        tokens = set(re.findall(r'[가-힣a-zA-Z]{2,}', s.lower()))
        # 불용어 제거
        stopwords = {'기반', '기술', '시스템', '개발', '연구', '활용', '위한', '이상', '이하', '이내'}
        return tokens - stopwords
    q_tokens = tokenize(query)
    t_tokens = tokenize(text)
    if not q_tokens or not t_tokens:
        return 0.0
    intersection = q_tokens & t_tokens
    union = q_tokens | t_tokens
    jaccard = len(intersection) / len(union)
    # 보정: 교집합 비율 추가 가중
    recall = len(intersection) / len(q_tokens) if q_tokens else 0
    return round(min(1.0, jaccard * 0.6 + recall * 0.4), 4)

def find_common_keywords(query: str, text: str) -> list:
    def tokenize(s):
        tokens = re.findall(r'[가-힣a-zA-Z]{2,}', s.lower())
        stopwords = {'기반', '기술', '시스템', '개발', '연구', '활용', '위한', '이상', '이하', '이내', '및', '통한'}
        return [t for t in tokens if t not in stopwords]
    q_set = set(tokenize(query))
    t_list = tokenize(text)
    return [t for t in t_list if t in q_set]


# ─────────────────────────────────────────────
# 3. 사이드바 네비게이션
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("# 🚔 치안 동향 분석")
    st.caption("KIPoT Platform")
    st.divider()

    # 세션에서 메뉴 상태 관리
    if "menu" not in st.session_state:
        st.session_state.menu = "🏢 메인 대시보드"

    MENU_ITEMS = [
        ("🏢", "메인 대시보드"),
        ("📰", "일일 DB"),
        ("💡", "기술 아이디어"),
        ("📄", "RFP 사업기획"),
        ("📋", "NTIS 치안 분야 과제"),
    ]
    for icon, label in MENU_ITEMS:
        full = f"{icon} {label}"
        is_active = st.session_state.menu == full
        btn_style = (
            "background:#1a56db; color:#EEECE9; border:none; border-radius:8px; "
            "padding:0.65rem 1rem; width:100%; text-align:left; font-size:1.05rem; "
            "font-weight:600; margin-bottom:4px; cursor:pointer;"
            if is_active else
            "background:transparent; color:#2155A4; border:0px solid #e2e8f0; border-radius:8px; "
            "padding:0.65rem 1rem; width:100%; text-align:left; font-size:1.05rem; "
            "font-weight:500; margin-bottom:4px; cursor:pointer;"
        )
        if st.button(f"{icon}  {label}", key=f"menu_{label}",
                     use_container_width=True,
                     type="primary" if is_active else "secondary"):
            st.session_state.menu = full
            st.rerun()

    menu = st.session_state.menu
    st.divider()

    trend_data = load_trend_data()
    avail_dates = get_available_dates(trend_data)



# ─────────────────────────────────────────────
# 4. 메인 헤더
# ─────────────────────────────────────────────
st.title("🚔 치안 과학기술 동향 플랫폼")
st.caption("경찰청 R&D 국내외 치안 이슈·기술 동향 분석")
st.divider()


# ═══════════════════════════════════════════════════════════
# PAGE 1: 메인 대시보드 — 도메인 블록 + TODAY 브리핑
# ═══════════════════════════════════════════════════════════
if menu == "🏢 메인 대시보드":

    TODAY = datetime.now().strftime("%Y-%m-%d")
    # 오늘 데이터 없으면 가장 최근 날짜로 fallback
    if TODAY not in trend_data and avail_dates:
        DISPLAY_DATE = avail_dates[0]
    else:
        DISPLAY_DATE = TODAY
    today_data   = trend_data.get(DISPLAY_DATE, {})
    today_issues = today_data.get("issues", [])
    today_techs  = today_data.get("technologies", [])
    today_all    = today_issues + today_techs
    today_domains = set(item.get("domain","") for item in today_all)

    # 전체 누적 데이터 — 모든 날짜 합산
    all_issues = []
    all_techs  = []
    for date_key, day in trend_data.items():
        for item in day.get("issues", []):
            item = dict(item); item["_date"] = date_key
            all_issues.append(item)
        for item in day.get("technologies", []):
            item = dict(item); item["_date"] = date_key
            all_techs.append(item)
    all_items = all_issues + all_techs

    DOMAINS = [
        ("🤖 AI",            "#3498db"),
        ("🌐 국제 치안",     "#1abc9c"),
        ("🧬 과학 수사",     "#16a085"),
        ("🚗 교통",          "#2980b9"),
        ("💊 마약",          "#8e44ad"),
        ("📜 법·제도",       "#f39c12"),
        ("🔐 사이버 보안",   "#e74c3c"),
        ("🏘️ 생활 안전",    "#27ae60"),
        ("🚓 신종 범죄",     "#e67e22"),
        ("🛠️ 장비",         "#7f8c8d"),
    ]

    # ── 세션 상태 초기화
    if "dash_domain" not in st.session_state:
        st.session_state.dash_domain = None
    if "dash_filter" not in st.session_state:
        st.session_state.dash_filter = "all"   # "all" | "issues" | "techs"

    # ════════════════════════════════════════
    # 서브페이지: 특정 도메인 상세 목록
    # ════════════════════════════════════════
    if st.session_state.dash_domain:
        domain    = st.session_state.dash_domain
        color     = dict(DOMAINS)[domain]
        item_filter = st.session_state.dash_filter   # "all" | "issues" | "techs"

        # ── 브레드크럼 + 날짜 필터 (오른쪽 정렬)
        bc_col, _, filt_col = st.columns([3, 1, 2])
        with bc_col:
            # 브레드크럼 표시
            filter_label = {"all": "전체", "issues": "이슈만", "techs": "기술만", "today": "오늘 신규"}[item_filter]
            st.markdown(f"""
            <div style="display:flex; align-items:center; gap:6px; font-size:0.85rem; margin-bottom:0.8rem;">
              <span style="color:#7f8c8d;">🏢 메인 대시보드</span>
              <span style="color:#7f8c8d;">›</span>
              <span style="color:{color}; font-weight:700;">{domain}</span>
              <span style="background:{color}33; color:{color}; font-size:0.7rem;
                   padding:1px 8px; border-radius:99px; font-weight:600;">{filter_label}</span>
            </div>
            """, unsafe_allow_html=True)
            if st.button("← 대시보드로 돌아가기", key="back_btn"):
                st.session_state.dash_domain = None
                st.session_state.dash_filter = "all"
                st.rerun()

        with filt_col:
            filter_opts2 = ["📊 전체 누적"] + [f"📅 {d}" for d in avail_dates]
            filter_sel2  = st.selectbox("날짜 필터", options=filter_opts2,
                                        label_visibility="collapsed",
                                        key="sub_date_filter")

        # 날짜 필터 적용
        if filter_sel2 == "📊 전체 누적":
            sub_items = [it for it in all_items if it.get("domain") == domain]
            sub_label = "누적 전체"
        else:
            sub_date  = filter_sel2.replace("📅 ", "")
            sub_day   = trend_data.get(sub_date, {})
            sub_raw   = []
            for item in sub_day.get("issues", []):
                item = dict(item); item["_date"] = sub_date; sub_raw.append(item)
            for item in sub_day.get("technologies", []):
                item = dict(item); item["_date"] = sub_date; sub_raw.append(item)
            sub_items = [it for it in sub_raw if it.get("domain") == domain]
            sub_label = sub_date

        # 이슈/기술 분리
        all_sub_issues = [it for it in sub_items if it.get("id","").startswith("I")]
        all_sub_techs  = [it for it in sub_items if it.get("id","").startswith("T")]

        # 오늘 신규 항목
        all_sub_today  = [it for it in sub_items if it.get("_date") == TODAY]

        # 이슈/기술/오늘 필터 전환 버튼 (서브페이지 내부 탭)
        tab_all, tab_iss, tab_tec, tab_new = st.columns(4)
        with tab_all:
            active_all = item_filter == "all"
            if st.button(
                f"{'▶ ' if active_all else ''}📋 전체 ({len(sub_items)}건)",
                key="sub_tab_all", use_container_width=True,
                type="primary" if active_all else "secondary"
            ):
                st.session_state.dash_filter = "all"; st.rerun()
        with tab_iss:
            active_iss = item_filter == "issues"
            if st.button(
                f"{'▶ ' if active_iss else ''}🚨 이슈 ({len(all_sub_issues)}건)",
                key="sub_tab_iss", use_container_width=True,
                type="primary" if active_iss else "secondary",
                disabled=(len(all_sub_issues) == 0)
            ):
                st.session_state.dash_filter = "issues"; st.rerun()
        with tab_tec:
            active_tec = item_filter == "techs"
            if st.button(
                f"{'▶ ' if active_tec else ''}🔬 기술 ({len(all_sub_techs)}건)",
                key="sub_tab_tec", use_container_width=True,
                type="primary" if active_tec else "secondary",
                disabled=(len(all_sub_techs) == 0)
            ):
                st.session_state.dash_filter = "techs"; st.rerun()
        with tab_new:
            active_new = item_filter == "today"
            if st.button(
                f"{'▶ ' if active_new else ''}🆕 오늘 ({len(all_sub_today)}건)",
                key="sub_tab_new", use_container_width=True,
                type="primary" if active_new else "secondary",
                disabled=(len(all_sub_today) == 0)
            ):
                st.session_state.dash_filter = "today"; st.rerun()

        # 도메인 헤더
        new_badge_sub = " 🆕" if domain in today_domains else ""
        st.subheader(f"{domain}{new_badge_sub}")
        st.caption(f"표시 기준: {sub_label}  ·  이슈 {len(all_sub_issues)}건  ·  기술 {len(all_sub_techs)}건")

        # 표시할 항목 결정
        if item_filter == "issues":
            sub_issues = all_sub_issues
            sub_techs  = []
        elif item_filter == "techs":
            sub_issues = []
            sub_techs  = all_sub_techs
        elif item_filter == "today":
            sub_issues = [it for it in all_sub_issues if it.get("_date") == TODAY]
            sub_techs  = [it for it in all_sub_techs  if it.get("_date") == TODAY]
        else:  # "all"
            sub_issues = all_sub_issues
            sub_techs  = all_sub_techs

        if not sub_issues and not sub_techs:
            st.info("해당 조건에 맞는 데이터가 없습니다.")
        else:

            # 이슈 카드
            if sub_issues:
                st.markdown("""
                <div class="section-divider">
                  <span class="divider-label">🚨 치안 이슈</span>
                </div>
                """, unsafe_allow_html=True)
                for issue in sub_issues:
                    sev = severity_label(issue.get("severity",""))
                    tags_html = "".join(f'<span class="domain-tag">{t}</span>' for t in issue.get("tags",[]))
                    is_today_item = issue.get("_date") == TODAY
                    today_mark = '<span style="background:#e53e3e;color:white;font-size:0.65rem;padding:2px 7px;border-radius:4px;margin-left:6px;">NEW</span>' if is_today_item else ""
                    st.markdown(f"""
                    <div class="issue-card">
                      <div class="card-title">
                        {issue.get('title','')} {today_mark}
                        <span class="severity-{issue.get('severity','low')}">{sev}</span>
                      </div>
                      <div class="card-meta">
                        📅 {issue.get('_date','')} &nbsp;|&nbsp; 출처: {issue.get('source','')}
                      </div>
                      <div class="card-body">{issue.get('summary','')}</div>
                      <div style="margin-top:0.5rem;">{tags_html}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    with st.expander(f"🔎 상세 분석 + 원문 링크 — {issue.get('title','')[:35]}…"):
                        st.markdown(f"""
**🔍 심층 분석**

{issue.get('detail','')}

---
**🏷️ 분류 태그:** {" · ".join(issue.get('tags',[]))}

**🔗 [기사·원문 바로가기]({issue.get('url','#')})**
> ⚠️ 외부 링크는 해당 기관 공식 페이지로 연결됩니다.
                        """)

            # 기술 카드
            if sub_techs:
                st.markdown("""
                <div class="section-divider">
                  <span class="divider-label">🔬 치안 기술</span>
                </div>
                """, unsafe_allow_html=True)
                for tech in sub_techs:
                    tags_html = "".join(f'<span class="domain-tag">{t}</span>' for t in tech.get("tags",[]))
                    is_today_item = tech.get("_date") == TODAY
                    today_mark = '<span style="background:#e53e3e;color:white;font-size:0.65rem;padding:2px 7px;border-radius:4px;margin-left:6px;">NEW</span>' if is_today_item else ""
                    st.markdown(f"""
                    <div class="tech-card">
                      <div class="card-title">
                        {tech.get('title','')} {today_mark}
                      </div>
                      <div class="card-meta">📅 {tech.get('_date','')} </div>
                      <div class="card-body">{tech.get('summary','')}</div>
                      <div style="margin-top:0.5rem;">{tags_html}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    with st.popover(f"🔬 기술 원리 설명 — {tech.get('title','')[:20]}…"):
                        st.markdown(f"""
### 🔬 {tech.get('title','')}

**📋 기술 원리 및 상세 정보**

{tech.get('detail','')}

---
**🔗 [관련 기관/연구소 바로가기]({tech.get('url','#')})**
                        """)
                    with st.expander(f"📂 기술 심층 데이터 — {tech.get('title','')[:35]}…"):
                        st.metric("수집 날짜", tech.get('_date',''))
                        st.markdown(f"""
**기술 상세 설명:**
{tech.get('detail','')}

**🔗 [원문/관련 기관 링크]({tech.get('url','#')})**
                        """)

    # ════════════════════════════════════════
    # 메인: 4분할 인텔리전스 대시보드
    # ════════════════════════════════════════
    else:
        from collections import Counter
        from datetime import datetime, timedelta

        # ── 데이터 준비
        today_dt   = datetime.now()
        week_ago   = (today_dt - timedelta(days=7)).strftime("%Y-%m-%d")
        month_ago  = (today_dt - timedelta(days=30)).strftime("%Y-%m-%d")

        # weekly_summary.json 로드
        WEEKLY_PATH = "data/weekly_summary.json"
        weekly_data = {}
        if os.path.exists(WEEKLY_PATH):
            try:
                with open(WEEKLY_PATH, "r", encoding="utf-8") as f:
                    weekly_data = json.load(f)
            except Exception:
                weekly_data = {}

        DOMAIN_LIST = [
            "🤖 AI", "🌐 국제 치안", "🧬 과학 수사", "🚗 교통",
            "💊 마약", "📜 법·제도", "🔐 사이버 보안",
            "🏘️ 생활 안전", "🚓 신종 범죄", "🛠️ 장비"
        ]
        DOMAIN_COLORS = {
            "🤖 AI": "#3498db", "🌐 국제 치안": "#1abc9c", "🧬 과학 수사": "#16a085",
            "🚗 교통": "#2980b9", "💊 마약": "#8e44ad", "📜 법·제도": "#f39c12",
            "🔐 사이버 보안": "#e74c3c", "🏘️ 생활 안전": "#27ae60",
            "🚓 신종 범죄": "#e67e22", "🛠️ 장비": "#7f8c8d"
        }
        DOMAIN_SHORT = {
            "🤖 AI": "AI", "🌐 국제 치안": "국제", "🧬 과학 수사": "과학수사",
            "🚗 교통": "교통", "💊 마약": "마약", "📜 법·제도": "법제도",
            "🔐 사이버 보안": "사이버", "🏘️ 생활 안전": "생활안전",
            "🚓 신종 범죄": "신종범죄", "🛠️ 장비": "장비"
        }

        # 최근 30일 날짜별·분야별 이슈 카운트
        month_dates = sorted([d for d in trend_data.keys() if d >= month_ago])
        month_domain_series = {dom: [] for dom in DOMAIN_LIST}
        for date_key in month_dates:
            day = trend_data.get(date_key, {})
            day_counts = Counter(item.get("domain","") for item in day.get("issues",[]))
            for dom in DOMAIN_LIST:
                month_domain_series[dom].append(day_counts.get(dom, 0))

        # ── CSS
        st.markdown("""
        <style>
        .dash-panel {
            background: #fff;
            border: 0px solid #e5e7eb;
            border-radius: 10px;
            padding: 1.1rem 1.2rem 1rem;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
            height: 100%;
        }
        .dash-panel-title {
            font-size: 0.78rem;
            font-weight: 700;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.8rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid #f3f4f6;
        }
        .rank-row {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 0.45rem;
        }
        .rank-num {
            font-size: 0.7rem;
            font-weight: 700;
            color: #9ca3af;
            width: 16px;
            text-align: center;
        }
        .rank-bar-wrap {
            flex: 1;
            background: #f3f4f6;
            border-radius: 4px;
            height: 20px;
            overflow: hidden;
            position: relative;
        }
        .rank-bar-fill {
            height: 100%;
            border-radius: 4px;
            display: flex;
            align-items: center;
            padding-left: 7px;
        }
        .rank-label {
            font-size: 0.72rem;
            font-weight: 600;
            color: #fff;
            white-space: nowrap;
        }
        .rank-count {
            font-size: 0.72rem;
            font-weight: 700;
            color: #374151;
            width: 28px;
            text-align: right;
        }
        .sparkline-wrap {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .spark-row {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .spark-label {
            font-size: 0.68rem;
            color: #374151;
            width: 52px;
            flex-shrink: 0;
        }
        .spark-dots {
            flex: 1;
            display: flex;
            align-items: flex-end;
            gap: 2px;
            height: 22px;
        }
        .wc-placeholder {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 160px;
            color: #9ca3af;
            font-size: 0.8rem;
            gap: 8px;
        }
        </style>
        """, unsafe_allow_html=True)

        col_left, col_right = st.columns(2)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 패널 1 (왼쪽 위): 최근 7일 급상승 분야 (노션 동기화)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        with col_left:
            weekly_domains = weekly_data.get("domains", [])
            weekly_period  = weekly_data.get("period", "")
            top_domains    = [(d["domain"], d["count"]) for d in weekly_domains if d.get("count", 0) > 0][:3]
            max_cnt        = top_domains[0][1] if top_domains else 1

            rows_html = ""
            for i, (dom, cnt) in enumerate(top_domains, 1):
                color  = DOMAIN_COLORS.get(dom, "#6b7280")
                short  = DOMAIN_SHORT.get(dom, dom)
                pct    = int(cnt / max_cnt * 100)
                medal  = ["🥇","🥈","🥉"][i-1]
                rows_html += (
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:0.5rem;">'
                    f'<span style="font-size:1rem;width:22px;text-align:center;">{medal}</span>'
                    f'<div style="flex:1;background:#f3f4f6;border-radius:4px;height:22px;overflow:hidden;">'
                    f'<div style="width:{pct}%;height:100%;background:{color};border-radius:4px;'
                    f'display:flex;align-items:center;padding-left:7px;">'
                    f'<span style="font-size:0.72rem;font-weight:600;color:#fff;white-space:nowrap;">{short}</span>'
                    f'</div></div>'
                    f'<span style="font-size:0.72rem;font-weight:700;color:#374151;width:28px;text-align:right;">{cnt}건</span>'
                    f'</div>'
                )

            if not top_domains:
                rows_html = '<div style="color:#9ca3af;font-size:0.8rem;padding:1rem 0;">동기화 대기 중...</div>'

            period_txt = f'<span style="font-weight:400;color:#9ca3af;font-size:0.7rem;margin-left:6px;">{weekly_period}</span>' if weekly_period else ""
            st.markdown(
                f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;'
                f'padding:1.1rem 1.2rem 1rem;box-shadow:0 1px 4px rgba(0,0,0,0.06);">'
                f'<div style="font-size:0.78rem;font-weight:700;color:#6b7280;text-transform:uppercase;'
                f'letter-spacing:0.05em;margin-bottom:0.8rem;padding-bottom:0.5rem;border-bottom:1px solid #f3f4f6;">'
                f'📈 급상승 분야{period_txt}</div>'
                + rows_html +
                f'</div>',
                unsafe_allow_html=True
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 패널 2 (오른쪽 위): 30일 분야별 추이
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        with col_right:
            # 30일 중 누적 건수 있는 도메인만 표시
            active_domains = [(dom, sum(month_domain_series[dom]))
                              for dom in DOMAIN_LIST if sum(month_domain_series[dom]) > 0]
            active_domains.sort(key=lambda x: -x[1])

            spark_rows_html = ""
            n_dates = len(month_dates)

            for dom, total in active_domains:
                color  = DOMAIN_COLORS.get(dom, "#6b7280")
                short  = DOMAIN_SHORT.get(dom, dom)
                series = month_domain_series[dom]
                max_v  = max(series) if max(series) > 0 else 1

                dots_html = ""
                for v in series:
                    h = max(2, int(v / max_v * 20))
                    opacity = "1.0" if v > 0 else "0.15"
                    dots_html += f'<div style="flex:1;height:{h}px;background:{color};opacity:{opacity};border-radius:1px;min-width:3px;"></div>'

                spark_rows_html += f"""
                <div class="spark-row">
                  <span class="spark-label">{short}</span>
                  <div class="spark-dots">{dots_html}</div>
                  <span style="font-size:0.68rem;font-weight:700;color:{color};width:24px;text-align:right;">{total}</span>
                </div>"""

            if not active_domains:
                spark_rows_html = '<div style="color:#9ca3af;font-size:0.8rem;">데이터 없음</div>'

            date_range = f"{month_dates[0]} ~ {month_dates[-1]}" if month_dates else "—"
            st.markdown(f"""
            <div class="dash-panel">
              <div class="dash-panel-title">📊 30일 분야별 이슈 추이 &nbsp;<span style="font-weight:400;text-transform:none;letter-spacing:0;color:#9ca3af;font-size:0.7rem;">{date_range}</span></div>
              <div class="sparkline-wrap">{spark_rows_html}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top:0.8rem;'></div>", unsafe_allow_html=True)
        col_left2, col_right2 = st.columns(2)

        # ── wordcloud.json 로드
        WC_PATH = "data/wordcloud.json"
        wc_data = {}
        if os.path.exists(WC_PATH):
            try:
                with open(WC_PATH, "r", encoding="utf-8") as f:
                    wc_data = json.load(f)
            except Exception:
                wc_data = {}
        wc_domains = wc_data.get("domains", {})

        # ── 세션 상태 초기화
        if "wc_issue_domain" not in st.session_state:
            st.session_state.wc_issue_domain = None
        if "wc_tech_domain" not in st.session_state:
            st.session_state.wc_tech_domain = None

        def render_wc_panel(title, wc_key, kw_type, session_key):
            import random, hashlib, json as _json
            st.markdown(
                f'<div style="background:#F5F5F4;border:0px solid #e5e7eb;border-radius:0px 0px 0 0;'
                f'padding:0.8rem 1.2rem 0.6rem;border-bottom:1px solid #e5e7eb;">'
                f'<span style="font-size:0.78rem;font-weight:700;color:#6b7280;'
                f'text-transform:uppercase;letter-spacing:0.05em;">{title}</span></div>',
                unsafe_allow_html=True
            )

            if not wc_domains:
                st.markdown(
                    '<div style="background:#fff;border:1px solid #e5e7eb;border-top:0;'
                    'border-radius:0 0 10px 10px;padding:1.5rem;text-align:center;'
                    'color:#9ca3af;font-size:0.8rem;">동기화 대기 중...</div>',
                    unsafe_allow_html=True
                )
                return

            has_data = [d for d in DOMAIN_LIST if wc_domains.get(d, {}).get(kw_type)]
            if st.session_state[session_key] not in DOMAIN_LIST:
                st.session_state[session_key] = has_data[0] if has_data else DOMAIN_LIST[0]

            sel_dom  = st.session_state[session_key]
            keywords = wc_domains.get(sel_dom, {}).get(kw_type, [])
            color    = DOMAIN_COLORS.get(sel_dom, "#3498db")

            # Canvas 워드클라우드
            if keywords:
                import streamlit.components.v1 as components
                r_hex = int(color[1:3], 16)
                g_hex = int(color[3:5], 16)
                b_hex = int(color[5:7], 16)
                palette = [
                    color,
                    f"#{max(0,r_hex-40):02x}{max(0,g_hex-40):02x}{max(0,b_hex-40):02x}",
                    f"#{min(255,r_hex+60):02x}{min(255,g_hex+40):02x}{min(255,b_hex+40):02x}",
                    f"#{max(0,r_hex-20):02x}{min(255,g_hex+30):02x}{max(0,b_hex-10):02x}",
                    "#4b5563",
                ]
                import json as _json
                kw_json = _json.dumps(keywords[:40], ensure_ascii=False)
                palette_json = _json.dumps(palette)
                seed = int(hashlib.md5(sel_dom.encode()).hexdigest()[:8], 16) % 9999

                components.html(f"""
<canvas id="wc" width="600" height="240"
  style="width:100%;height:240px;display:block;"></canvas>
<script>
(function(){{
  var canvas = document.getElementById('wc');
  var ctx = canvas.getContext('2d');
  var W = canvas.width, H = canvas.height;
  var words = {kw_json};
  var palette = {palette_json};
  var maxCnt = words[0].count;
  var s = {seed};
  function rand(){{ s = (s * 1664525 + 1013904223) & 0xffffffff; return (s>>>0)/0xffffffff; }}
  ctx.clearRect(0,0,W,H);
  var placed = [];
  function overlap(x,y,w,h){{
    for(var i=0;i<placed.length;i++){{
      var p=placed[i];
      if(!(x+w+2<p.x||x>p.x+p.w+2||y+h+2<p.y||y>p.y+p.h+2)) return true;
    }}
    return false;
  }}
  for(var i=0;i<words.length;i++){{
    var ratio = words[i].count / maxCnt;
    var fs = Math.round(10 + ratio * 30);
    var weight = ratio>0.6?'800':(ratio>0.3?'600':'400');
    var angle = (ratio<0.35 && rand()>0.55) ? (rand()>0.5?Math.PI/2:-Math.PI/2) : 0;
    var col = palette[i % palette.length];
    var word = words[i].word;
    ctx.font = weight+' '+fs+'px Arial,sans-serif';
    var tw = ctx.measureText(word).width + 4;
    var th = fs * 1.3;
    var rw = angle===0?tw:th, rh = angle===0?th:tw;
    var cx0=W/2, cy0=H/2;
    for(var t=0;t<800;t++){{
      var a = t*0.3, r = t*0.55;
      var cx = Math.round(cx0 + r*Math.cos(a));
      var cy = Math.round(cy0 + r*Math.sin(a));
      var bx=cx-rw/2, by=cy-rh/2;
      if(bx<2||by<2||bx+rw>W-2||by+rh>H-2) continue;
      if(!overlap(bx,by,rw,rh)){{
        placed.push({{x:bx,y:by,w:rw,h:rh}});
        ctx.save();
        ctx.translate(cx,cy);
        ctx.rotate(angle);
        ctx.globalAlpha = 0.55+ratio*0.45;
        ctx.fillStyle = col;
        ctx.font = weight+' '+fs+'px Arial,sans-serif';
        ctx.textAlign='center'; ctx.textBaseline='middle';
        ctx.fillText(word,0,0);
        ctx.restore();
        break;
      }}
    }}
  }}
}})();
</script>
""", height=250, scrolling=False)
            else:
                st.markdown(
                    '<div style="background:#fff;border-left:1px solid #e5e7eb;'
                    'border-right:1px solid #e5e7eb;padding:2rem;text-align:center;'
                    'color:#9ca3af;font-size:0.8rem;">해당 기간 데이터 없음</div>',
                    unsafe_allow_html=True
                )

            # 5개씩 2행 버튼
            for row_doms in [DOMAIN_LIST[:5], DOMAIN_LIST[5:]]:
                row_cols = st.columns(5)
                for i, dom in enumerate(row_doms):
                    short  = DOMAIN_SHORT.get(dom, dom)
                    is_sel = (st.session_state[session_key] == dom)
                    has_d  = bool(wc_domains.get(dom, {}).get(kw_type))
                    with row_cols[i]:
                        if st.button(
                            short,
                            key=f"{wc_key}_btn_{dom}",
                            use_container_width=True,
                            type="primary" if is_sel else "secondary",
                            disabled=not has_d
                        ):
                            st.session_state[session_key] = dom
                            st.rerun()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 패널 3 (왼쪽 아래): 이슈 워드클라우드
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        with col_left2:
            render_wc_panel("☁️ 이슈 키워드", "wc_issue", "issues", "wc_issue_domain")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 패널 4 (오른쪽 아래): 기술 워드클라우드
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        with col_right2:
            render_wc_panel("☁️ 기술 키워드", "wc_tech", "techs", "wc_tech_domain")



# ═══════════════════════════════════════════════════════════
# PAGE 2: 일일 DB — 치안과학기술 동향분석 일일 리포트
# ═══════════════════════════════════════════════════════════
elif menu == "📰 일일 DB":

    DAILY_PATH = "data/daily_reports.json"

    def load_daily():
        if os.path.exists(DAILY_PATH):
            try:
                with open(DAILY_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        return {}

    daily_data = load_daily()  # {날짜: {issues:[], technologies:[]}}

    # ── 기준 날짜
    DAILY_TODAY = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
    avail_set   = set(daily_data.keys()) if daily_data else set()
    avail_daily = sorted(avail_set, reverse=True)

    if "daily_sel_date" not in st.session_state:
        st.session_state.daily_sel_date = (
            DAILY_TODAY if DAILY_TODAY in avail_set
            else (avail_daily[0] if avail_daily else DAILY_TODAY)
        )
    DAILY_DISPLAY = st.session_state.daily_sel_date

    # ── 달력 연/월 (선택 날짜와 별개로 session_state로 관리 → 월 이동 가능)
    import calendar as _cal
    if "daily_cal_ym" not in st.session_state:
        try:
            _init_cy, _init_cm = int(DAILY_DISPLAY[:4]), int(DAILY_DISPLAY[5:7])
        except Exception:
            _init_cy, _init_cm = int(DAILY_TODAY[:4]), int(DAILY_TODAY[5:7])
        st.session_state.daily_cal_ym = (_init_cy, _init_cm)

    _cy, _cm = st.session_state.daily_cal_ym

    _first_wd, _days_n = _cal.monthrange(_cy, _cm)
    _start_off = (_first_wd + 1) % 7

    _cells = [None] * _start_off + list(range(1, _days_n + 1))
    _mn    = ["","1월","2월","3월","4월","5월","6월","7월","8월","9월","10월","11월","12월"]

    # ── 레이아웃: 왼쪽(필터) / 오른쪽(달력)
    _col_left, _col_right = st.columns([1, 2])

    with _col_left:
        # 분야 필터
        all_daily_domains = sorted({
            item.get("domain","")
            for day in daily_data.values()
            for lst in day.values()
            for item in (lst if isinstance(lst, list) else [])
            if item.get("domain")
        })
        sel_domain = st.selectbox("분야", ["전체"] + list(all_daily_domains),
                                  label_visibility="collapsed")
        st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)

        # 이슈 / 기술 필터 버튼
        if "daily_type_filter" not in st.session_state:
            st.session_state.daily_type_filter = "전체"
        _tf = st.session_state.daily_type_filter
        _tb1, _tb2, _tb3 = st.columns(3)
        with _tb1:
            if st.button("전체",  key="dtf_all",   type="primary" if _tf=="전체"  else "secondary", use_container_width=True):
                st.session_state.daily_type_filter = "전체";  st.rerun()
        with _tb2:
            if st.button("🚨 이슈", key="dtf_issue", type="primary" if _tf=="이슈"  else "secondary", use_container_width=True):
                st.session_state.daily_type_filter = "이슈";  st.rerun()
        with _tb3:
            if st.button("🔬 기술", key="dtf_tech",  type="primary" if _tf=="기술"  else "secondary", use_container_width=True):
                st.session_state.daily_type_filter = "기술";  st.rerun()

    with _col_right:
        # ── 달력 헤더: 이전/다음 달 이동 버튼
        _nav1, _nav2, _nav3 = st.columns([1, 5, 1])
        with _nav1:
            if st.button("◀", key="cal_prev_month", use_container_width=True):
                _pm, _py = (_cm - 1, _cy) if _cm > 1 else (12, _cy - 1)
                st.session_state.daily_cal_ym = (_py, _pm)
                st.rerun()
        with _nav2:
            st.markdown(
                f'<div style="text-align:center;font-size:0.9rem;font-weight:700;'
                f'color:#111827;padding-top:6px;">📅 {_cy}년 {_mn[_cm]}</div>',
                unsafe_allow_html=True
            )
        with _nav3:
            if st.button("▶", key="cal_next_month", use_container_width=True):
                _nm, _ny = (_cm + 1, _cy) if _cm < 12 else (1, _cy + 1)
                st.session_state.daily_cal_ym = (_ny, _nm)
                st.rerun()

        # 요일 헤더
        _hdrs = st.columns(7)
        for _hi, _dn in enumerate(["일","월","화","수","목","금","토"]):
            _hdrs[_hi].markdown(
                f'<div style="text-align:center;font-size:0.68rem;color:#9ca3af;font-weight:600;">{_dn}</div>',
                unsafe_allow_html=True
            )
        # 날짜 셀 (7개씩 행으로)
        _rows = [_cells[i:i+7] for i in range(0, len(_cells), 7)]
        for _row in _rows:
            _rcols = st.columns(7)
            for _ci, _d in enumerate(_row):
                with _rcols[_ci]:
                    if _d is None:
                        st.markdown('<div style="height:32px;"></div>', unsafe_allow_html=True)
                    else:
                        _ds = f"{_cy:04d}-{_cm:02d}-{_d:02d}"
                        if _ds == DAILY_DISPLAY:
                            # 선택됨 — primary 버튼
                            st.button(str(_d), key=f"cal_{_ds}", type="primary",
                                      use_container_width=True)
                        elif _ds in avail_set:
                            # 데이터 있음 — 클릭 가능
                            if st.button(str(_d), key=f"cal_{_ds}",
                                         use_container_width=True):
                                st.session_state.daily_sel_date = _ds
                                st.rerun()
                        else:
                            # 데이터 없음 — 비활성
                            st.button(str(_d), key=f"cal_{_ds}",
                                      disabled=True, use_container_width=True)

    # ── TODAY 브리핑 헤더
    st.markdown(f"""
    <div style="margin-top:0.8rem; padding-bottom:0.5rem; border-bottom:2px solid #e2e8f0;">
      <span style="font-size:1.25rem; font-weight:700; color:#1a202c;">📡 TODAY 브리핑</span>
    </div>
    """, unsafe_allow_html=True)

    if not daily_data:
        st.info("📭 아직 등록된 일일 리포트가 없습니다. 오전 10:00에 업데이트됩니다.")
    else:
        # ── 날짜 메트릭
        day_content  = daily_data.get(DAILY_DISPLAY, {})
        _d_issues = len(day_content.get("issues", []))
        _d_techs  = len(day_content.get("technologies", []))
        _m1, _m2, _m3, _m4 = st.columns(4)
        _m1.metric("📅 날짜", DAILY_DISPLAY)
        _m2.metric("🚨 새 이슈", f"{_d_issues}개")
        _m3.metric("🔬 새 기술", f"{_d_techs}개")
        _m4.metric("📊 총합", f"{_d_issues + _d_techs}개")
        _type_filter = st.session_state.get("daily_type_filter", "전체")
        daily_issues = [r for r in day_content.get("issues", [])
                        if (sel_domain == "전체" or r.get("domain","") == sel_domain)
                        and _type_filter in ("전체", "이슈")]
        daily_techs  = [r for r in day_content.get("technologies", [])
                        if (sel_domain == "전체" or r.get("domain","") == sel_domain)
                        and _type_filter in ("전체", "기술")]

        if not daily_issues and not daily_techs:
            st.info(f"📭 {DAILY_DISPLAY} 수집된 데이터가 없습니다.")
        else:

            # 이슈 섹션
            if daily_issues:
                st.markdown("""
                <div class="section-divider">
                  <span class="divider-label">🚨 오늘의 치안 이슈</span>
                </div>
                """, unsafe_allow_html=True)
                for issue in daily_issues:
                    sev = severity_label(issue.get("severity",""))
                    tags_html = "".join(f'<span class="domain-tag">{t}</span>' for t in issue.get("tags",[]))
                    st.markdown(f"""
                    <div class="issue-card">
                      <div class="card-title">
                        {issue.get('title','')}
                        <span class="severity-{issue.get('severity','low')}">{sev}</span>
                      </div>
                      <div class="card-meta">
                        {issue.get('domain','')} &nbsp;|&nbsp; 출처: {issue.get('source','')}
                      </div>
                      <div class="card-body">{issue.get('summary','')}</div>
                      <div style="margin-top:0.5rem;">{tags_html}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    with st.expander(f"🔎 상세 분석 + 원문 링크 — {issue.get('title','')[:35]}…"):
                        st.markdown(f"""
**🔍 심층 분석**

{issue.get('detail','')}

---
**📎 관련 도메인:** `{issue.get('domain','')}`  
**🏷️ 분류 태그:** {' · '.join(issue.get('tags',[]))}

**🔗 [기사·원문 바로가기]({issue.get('url','#')})**
                        """)

            # 기술 섹션
            if daily_techs:
                st.markdown("""
                <div class="section-divider">
                  <span class="divider-label">🔬 오늘의 치안 기술</span>
                </div>
                """, unsafe_allow_html=True)
                for tech in daily_techs:
                    tags_html = "".join(f'<span class="domain-tag">{t}</span>' for t in tech.get("tags",[]))
                    st.markdown(f"""
                    <div class="tech-card">
                      <div class="card-title">{tech.get('title','')}</div>
                      <div class="card-meta">{tech.get('domain','')}</div>
                      <div class="card-body">{tech.get('summary','')}</div>
                      <div style="margin-top:0.5rem;">{tags_html}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    with st.expander(f"📂 기술 심층 데이터 — {tech.get('title','')[:35]}…"):
                        st.markdown(f"""
**🔍 기술 상세 설명**

{tech.get('detail','')}

---
**📎 관련 도메인:** `{tech.get('domain','')}`  
**🏷️ 분류 태그:** {' · '.join(tech.get('tags',[]))}

**🔗 [기사·원문 바로가기]({tech.get('url','#')})**
                        """)


# ═══════════════════════════════════════════════════════════
# PAGE 3: 아이디어 — 누적 동향 기반 과학기술 치안 접목 카드
# ═══════════════════════════════════════════════════════════
elif menu == "💡 기술 아이디어":

    IDEA_PATH = "data/idea_cards.json"

    @st.cache_data(ttl=300)
    def load_ideas():
        if os.path.exists(IDEA_PATH):
            with open(IDEA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    ideas = load_ideas()
    ideas = sorted(ideas, key=lambda x: x.get("date", ""), reverse=True)

    st.markdown("## 💡 치안 접목 가능 과학기술 아이디어")
    st.markdown("""
    <div style="background:#EAF5D2; border:1px solid #283B51; border-radius:8px;
         padding:0.9rem 1.2rem; margin-bottom:1.2rem;">
      <p style="color:#283B51; font-size:0.87rem; margin:0;">
        📡 일반 과학기술 뉴스·동향을 분석하여 치안 현장에 접목 가능한 기술 아이디어를 정리합니다.<br>
      </p>
    </div>
    """, unsafe_allow_html=True)

    DOMAIN_OPTS_9 = [
        "전체", "🤖 AI", "🌐 국제 치안", "🧬 과학 수사",
        "🚗 교통", "💊 마약", "📜 법·제도",
        "🔐 사이버 보안", "🏘️ 생활 안전", "🚓 신종 범죄", "🛠️ 장비"
    ]

    if "idea_domain_filter" not in st.session_state:
        st.session_state.idea_domain_filter = "전체"

    # ── 카테고리 버튼 그리드 (4열) + 검색창
    _idea_filter_l, _idea_filter_r = st.columns([3, 2])
    with _idea_filter_l:
        _idea_rows = [DOMAIN_OPTS_9[i:i+4] for i in range(0, len(DOMAIN_OPTS_9), 4)]
        for _row in _idea_rows:
            _btn_cols = st.columns(4)
            for _ci, _opt in enumerate(_row):
                with _btn_cols[_ci]:
                    _is_sel = st.session_state.idea_domain_filter == _opt
                    if st.button(_opt, key=f"idea_dom_{_opt}",
                                 type="primary" if _is_sel else "secondary",
                                 use_container_width=True):
                        st.session_state.idea_domain_filter = _opt
                        st.rerun()
    with _idea_filter_r:
        idea_search = st.text_input("기술명·키워드 검색", placeholder="예: 양자암호, 연합학습, 위성 …", label_visibility="collapsed")

    idea_domain_filter = st.session_state.idea_domain_filter
    filtered_ideas = ideas
    if idea_domain_filter != "전체":
        filtered_ideas = [i for i in filtered_ideas if i.get("domain") == idea_domain_filter]
    if idea_search.strip():
        sq = idea_search.lower()
        filtered_ideas = [i for i in filtered_ideas if
            sq in i.get("tech_name","").lower() or
            sq in " ".join(i.get("tags",[])).lower() or
            sq in i.get("features","").lower()]

    st.caption(f"표시: {len(filtered_ideas)}건 / 전체: {len(ideas)}건")

    if not filtered_ideas:
        st.info("조건에 맞는 아이디어가 없습니다. 데이터가 오전 10:00에 업데이트됩니다.")
    else:
        for idea in filtered_ideas:
            domain   = idea.get("domain", "")
            tech     = idea.get("tech_name", "")
            date     = idea.get("date", "")
            policing_issues = idea.get("policing_issues", []) or []
            target_issue    = idea.get("target_issue", "")
            tags     = idea.get("tags", [])
            tags_html = "".join(f'<span class="domain-tag">{t}</span>' for t in tags)
            is_new   = date == datetime.now().strftime("%Y-%m-%d")
            new_mark = '<span style="background:#e74c3c;color:white;font-size:0.62rem;font-weight:700;padding:1px 7px;border-radius:99px;margin-left:6px;">NEW</span>' if is_new else ""

            # 해결 가능 치안 이슈: rich_text 문자열
            _pi = idea.get("policing_issues", "") or idea.get("target_issue", "")
            if _pi:
                _issue_block = (
                    f'<div style="font-size:0.82rem;color:#374151;margin-bottom:0.4rem;">'
                    f'🎯 해결 가능 치안 이슈: <b>{_pi}</b></div>'
                )
            else:
                _issue_block = '<div style="font-size:0.82rem;color:#9ca3af;margin-bottom:0.4rem;">🎯 해결 가능 치안 이슈: —</div>'

            st.markdown(f"""
            <div style="background:#EAF5D2; border:1px solid #283B51;
                 border-left:4px solid #283B51; border-radius:8px;
                 padding:0.9rem 1.1rem; margin-bottom:0.6rem;
                 box-shadow:0 1px 3px rgba(0,0,0,0.05);">
              <div style="display:flex; align-items:center; gap:8px; margin-bottom:0.4rem;">
                <span style="font-size:0.78rem; color:#1d4ed8; font-weight:600;">{domain}</span>
                <span style="font-size:0.7rem; color:#6b7280;">📅 {date}</span>
                {new_mark}
              </div>
              <div style="font-size:1rem; font-weight:700; color:#111827; margin-bottom:0.3rem;">{tech}</div>
              {_issue_block}
              <div style="margin-top:0.3rem;">{tags_html}</div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander(f"📋 상세 내용 — {tech}"):
                d1, d2 = st.columns(2)
                with d1:
                    st.markdown(f"""
**🔧 기술 특징**

{idea.get('features', '—')}

---
**⚠️ 제한 사항**

{idea.get('constraints', '—')}
                    """)
                with d2:
                    st.markdown(f"""
**🏛️ 적용 가능 분야**

{idea.get('applications', '—')}

---
**📈 기술 동향**

{idea.get('trend', '—')}
                    """)
                st.markdown(f"""
---
**🏢 주요 기업·제품**

{idea.get('companies', '—')}
                """)


# ═══════════════════════════════════════════════════════════
# PAGE 3: RFP 사업기획 — 이슈 중심 자동 기획서 생성
# ═══════════════════════════════════════════════════════════
elif menu == "📄 RFP 사업기획":

    RFP_PATH = "data/rfp_cards.json"

    @st.cache_data(ttl=300)
    def load_rfps():
        if os.path.exists(RFP_PATH):
            with open(RFP_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    rfp_cards = load_rfps()

    st.markdown("## 📄 RFP 사업기획")
    st.markdown("""
    <div style="background:#EAF5D2; border:1px solid #283B51; border-radius:8px;
         padding:0.9rem 1.2rem; margin-bottom:1.2rem;">
      <p style="color:#283B51; font-size:0.87rem; margin:0;">
        📡 누적 치안 이슈를 바탕으로 추진 배경을 설정하고, 관련 기술들을 조합하여 R&amp;D 사업기획서 초안을 생성합니다.<br>
      </p>
    </div>
    """, unsafe_allow_html=True)

    if not rfp_cards:
        st.info("📭 아직 생성된 RFP 초안이 없습니다. 치안 이슈가 누적되면 자동 업데이트됩니다.")
    else:
        _rfp_domains = [
            "전체", "🤖 AI", "🌐 국제 치안", "🧬 과학 수사",
            "🚗 교통", "💊 마약", "📜 법·제도",
            "🔐 사이버 보안", "🏘️ 생활 안전", "🚓 신종 범죄", "🛠️ 장비"
        ]

        if "rfp_domain_filter" not in st.session_state:
            st.session_state.rfp_domain_filter = "전체"

        _rfp_filter_l, _rfp_filter_r = st.columns([3, 2])
        with _rfp_filter_l:
            _rfp_rows = [_rfp_domains[i:i+4] for i in range(0, len(_rfp_domains), 4)]
            for _row in _rfp_rows:
                _btn_cols = st.columns(4)
                for _ci, _opt in enumerate(_row):
                    with _btn_cols[_ci]:
                        _is_sel = st.session_state.rfp_domain_filter == _opt
                        if st.button(_opt, key=f"rfp_dom_{_opt}",
                                     type="primary" if _is_sel else "secondary",
                                     use_container_width=True):
                            st.session_state.rfp_domain_filter = _opt
                            st.rerun()
        with _rfp_filter_r:
            rfp_search = st.text_input("과제명·키워드 검색", placeholder="예: 딥페이크, 포렌식, AI …", label_visibility="collapsed")

        rfp_domain_filter = st.session_state.rfp_domain_filter
        shown_rfps = [r for r in rfp_cards if rfp_domain_filter == "전체" or r.get("domain") == rfp_domain_filter]
        if rfp_search.strip():
            _sq = rfp_search.lower()
            shown_rfps = [r for r in shown_rfps if _sq in r.get("title","").lower()]
        shown_rfps = sorted(shown_rfps, key=lambda x: x.get("date",""), reverse=True)

        for rfp in shown_rfps:
            is_new = rfp.get("date","") == datetime.now().strftime("%Y-%m-%d")
            new_mark = '<span style="background:#e74c3c;color:white;font-size:0.62rem;padding:1px 7px;border-radius:99px;margin-left:6px;">NEW</span>' if is_new else ""
            tags_html = "".join(f'<span class="domain-tag">{t}</span>' for t in rfp.get("tags",[]))

            st.markdown(f"""
            <div style="background:#EAF5D2; border:1px solid #283B51;
                 border-left:5px solid #283B51; border-radius:8px;
                 padding:1rem 1.2rem; margin-bottom:0.8rem;
                 box-shadow:0 1px 3px rgba(0,0,0,0.05);">
              <div style="display:flex; align-items:center; gap:8px; margin-bottom:0.4rem;">
                <span style="font-size:0.75rem; color:#15803d; font-weight:600;">{rfp.get("domain","") or "📂 미분류"}</span>
                <span style="font-size:0.7rem; color:#6b7280;">📅 {rfp.get("date","")}</span>
                {new_mark}
              </div>
              <div style="font-size:1.05rem; font-weight:700; color:#111827; margin-bottom:0.3rem;">
                {rfp.get("title","")}
              </div>
              {f'<div style="font-size:0.82rem;color:#374151;margin-bottom:0.4rem;">'
               f'💰 <span style="font-weight:600;">{rfp.get("budget","")}</span></div>'
               if rfp.get("budget","") else ""}
              <div>{tags_html}</div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander(f"📋 전체 기획서 보기 — {rfp.get('title','')[:40]}"):
                # 추진 배경 및 최종 목표
                st.markdown("### 📌 추진 배경 및 최종 목표")
                st.markdown(f"""
**추진 배경:**

{rfp.get("background","")}

**최종 목표:**

{rfp.get("goal","")}
                """)

                # 주요 기술
                st.markdown("### 🔬 주요 기술")
                techs = rfp.get("core_techs", [])
                for i, tech in enumerate(techs, 1):
                    with st.popover(f"🔬 {i}. {tech.get('name','')}"):
                        st.markdown(f"""
**{tech.get('name','')}**

{tech.get('desc','')}
                        """)

                # 세부 목표
                st.markdown("### 🎯 세부 목표")
                for kpi in rfp.get("kpis", []):
                    st.markdown(f"- **{kpi.get('label','')}**: {kpi.get('value','')} — {kpi.get('reason','')}")

                # 추진 내용
                st.markdown("### 🗓️ 추진 내용")
                for phase in rfp.get("phases", []):
                    with st.expander(f"{phase.get('label','')}"):
                        st.markdown(phase.get("content",""))

                # 기대 효과 — [소제목] 기준으로 초록 블록 분리
                st.markdown("### ✅ 기대 효과")
                _eff = rfp.get("effect","")

                def _render_green_block(text):
                    """줄바꿈을 보존해 초록 박스로 렌더링"""
                    _html = text.replace("\n", "<br>")
                    st.markdown(
                        f'<div style="background:#f0fff4;border:1px solid #c6f6d5;'
                        f'border-radius:8px;padding:0.9rem 1.1rem;margin-bottom:0.6rem;'
                        f'color:#276749;font-size:0.88rem;line-height:1.8;">{_html}</div>',
                        unsafe_allow_html=True
                    )

                if _eff:
                    import re as _re3
                    _eff_parts = _re3.split(r"(?:^|\n)\[([^\]]+)\]", _eff)
                    if len(_eff_parts) == 1:
                        _render_green_block(_eff)
                    else:
                        if _eff_parts[0].strip():
                            _render_green_block(_eff_parts[0].strip())
                        _idx = 1
                        while _idx < len(_eff_parts) - 1:
                            _title = _eff_parts[_idx].strip()
                            _body  = _eff_parts[_idx + 1].strip()
                            _render_green_block(f"<b>{_title}</b><br>{_body}")
                            _idx += 2

                # 아키텍처 다이어그램
                if rfp.get("diagram"):
                    st.markdown("### 📐 사업 구상 아키텍처")
                    st.markdown(f"```mermaid\n{rfp.get('diagram','')}\n```")


# ═══════════════════════════════════════════════════════════
# PAGE 4: 유사 과제 — NTiS 국가 R&D 과제 모니터링
# ═══════════════════════════════════════════════════════════
elif menu == "📋 NTIS 치안 분야 과제":

    NTIS_PATH = "data/ntis_projects.json"

    @st.cache_data(ttl=300)
    def load_ntis_projects():
        if os.path.exists(NTIS_PATH):
            with open(NTIS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    ntis_list = load_ntis_projects()

    st.markdown("## 📋 유사 과제 모니터링")
    st.markdown("""
    <div style="background:#0d1f33; border:1px solid #1e4d7b; border-radius:10px;
         padding:0.9rem 1.2rem; margin-bottom:1.2rem;">
      <p style="color:#74b9ff; font-size:0.87rem; margin:0;">
        🔄 NTiS(국가과학기술지식정보서비스)에 신규 등록되는 치안 관련 국가 R&amp;D 과제를 모니터링합니다.<br>
      </p>
    </div>
    """, unsafe_allow_html=True)

    # 검색 필터
    nc1, nc2, nc3 = st.columns([2, 1, 1])
    with nc1:
        ntis_search = st.text_input("과제명·기관·키워드 검색", placeholder="예: 딥페이크, ETRI, 드론 …", label_visibility="collapsed")
    with nc2:
        ntis_year = st.selectbox("연도", ["전체", "2026"], label_visibility="collapsed")
    with nc3:
        ntis_domain = st.selectbox("도메인", ["전체", "🤖 AI·보안", "🔍 수사", "🚓 신종 범죄", "🧬 과학수사", "🚗 교통", "🛠️ 장비"], label_visibility="collapsed")

    filtered_ntis = ntis_list
    if ntis_search.strip():
        sq = ntis_search.lower()
        filtered_ntis = [n for n in filtered_ntis if
            sq in n.get("title","").lower() or
            sq in n.get("org","").lower() or
            sq in n.get("keywords","").lower()]
    if ntis_year != "전체":
        filtered_ntis = [n for n in filtered_ntis if str(n.get("year","")) == ntis_year]
    if ntis_domain != "전체":
        filtered_ntis = [n for n in filtered_ntis if n.get("domain","") == ntis_domain]

    # 요약 메트릭
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("전체 과제", len(ntis_list))
    m2.metric("신규 (이번주)", sum(1 for n in ntis_list if n.get("is_new", False)))
    m3.metric("표시 중", len(filtered_ntis))
    m4.metric("최근 업데이트", ntis_list[0].get("registered","—") if ntis_list else "—")

    st.divider()

    if not filtered_ntis:
        st.info("조건에 맞는 과제가 없습니다.")
    else:
        # 데이터프레임 표 표시
        df_ntis = pd.DataFrame([{
            "신규": "🆕" if n.get("is_new") else "",
            "과제명": n.get("title",""),
            "주관기관": n.get("org",""),
            "연도": n.get("year",""),
            "예산": n.get("budget",""),
            "도메인": n.get("domain",""),
            "등록일": n.get("registered",""),
        } for n in filtered_ntis])
        st.dataframe(df_ntis, use_container_width=True, hide_index=True)

        st.markdown("### 📋 과제별 상세")
        for ntis in filtered_ntis:
            is_new = ntis.get("is_new", False)
            new_mark = '<span style="background:#e74c3c;color:white;font-size:0.62rem;padding:1px 7px;border-radius:99px;margin-left:6px;">NEW</span>' if is_new else ""
            with st.expander(f"{'🆕 ' if is_new else ''}[{ntis.get('year','')}] {ntis.get('title','')} — {ntis.get('org','')}"):
                # 상단: 기본 정보 가로 4칸
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("주관 기관", ntis.get('org',''))
                m2.metric("총 연구비", ntis.get('budget',''))
                m3.metric("등록일", ntis.get('registered',''))
                m4.metric("도메인", ntis.get('domain',''))
                st.caption("총 연구 기간")
                st.write(ntis.get('total_orgs', ntis.get('org','')))
                st.caption("키워드")
                kw_tags = "  ".join([f"`{k.strip()}`" for k in ntis.get('keywords','').split(',') if k.strip()])
                st.markdown(kw_tags)
                b1, b2 = st.columns(2)
                with b1:
                    st.info(f"**연구 목표**\n\n{ntis.get('goal', ntis.get('summary',''))}")
                with b2:
                    st.info(f"**연구 내용**\n\n{ntis.get('content', ntis.get('summary',''))}")


# ─────────────────────────────────────────────
# 푸터
# ─────────────────────────────────────────────
st.divider()
st.markdown(f"""
<div style="text-align:center; font-size:0.72rem; color:#4a5568; padding:0.5rem 0;">
  🚔 치안 과학기술 동향 플랫폼 v1.0 &nbsp;|&nbsp; Powered by KIPoT (kipot.or.kr)
  &nbsp;|&nbsp; 데이터 기준: {datetime.now().strftime('%Y.%m.%d')} &nbsp;|&nbsp;
  수집 범위: 수정 외
</div>
""", unsafe_allow_html=True)
