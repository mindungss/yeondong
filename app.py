"""
치안 과학기술 동향 분석 플랫폼
Korean Policing Science & Technology Trend Intelligence System
Version 1.0 | 경찰청 R&D 기획 지원 전문 시스템
"""

import streamlit as st
import pandas as pd
import json
import os
import re
import math
from datetime import datetime, timedelta
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
DB_PATH   = "data/existing_db.txt"

@st.cache_data(ttl=300)
def load_trend_data() -> dict:
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

@st.cache_data(ttl=600)
def load_existing_db() -> list:
    entries = []
    if not os.path.exists(DB_PATH):
        return entries
    with open(DB_PATH, "r", encoding="utf-8") as f:
        raw = f.read()
    blocks = [b.strip() for b in raw.split("\n\n") if b.strip()]
    for block in blocks:
        entry = {}
        for line in block.split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                entry[k.strip()] = v.strip()
        if entry:
            entries.append(entry)
    return entries

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
    st.markdown("# 🚔 치안 과학기술 동향")
    st.caption("KIPOT Intelligence Platform")
    st.divider()

    # 세션에서 메뉴 상태 관리
    if "menu" not in st.session_state:
        st.session_state.menu = "🏢 메인 대시보드"

    MENU_ITEMS = [
        ("🏢", "메인 대시보드"),
        ("💡", "아이디어"),
        ("📄", "RFP 사업기획"),
        ("📋", "유사 과제"),
    ]
    for icon, label in MENU_ITEMS:
        full = f"{icon} {label}"
        is_active = st.session_state.menu == full
        btn_style = (
            "background:#1a56db; color:white; border:none; border-radius:8px; "
            "padding:0.65rem 1rem; width:100%; text-align:left; font-size:1.05rem; "
            "font-weight:600; margin-bottom:4px; cursor:pointer;"
            if is_active else
            "background:transparent; color:#1a202c; border:1px solid #e2e8f0; border-radius:8px; "
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

    _today_str = datetime.now().strftime("%Y-%m-%d")
    _latest    = avail_dates[0] if avail_dates else "-"
    _has_today = _latest == _today_str
    st.caption(f"🕐 데이터 기준일: {_latest}")
    if _has_today:
        st.success("✅ 오늘 업데이트됨", icon=None)
    else:
        st.warning("⚠️ 오늘 데이터 미수집", icon=None)


# ─────────────────────────────────────────────
# 4. 메인 헤더
# ─────────────────────────────────────────────
st.title("🚔 치안 과학기술 동향 인텔리전스 플랫폼")
st.caption("경찰청 R&D 예산 확보 및 사업기획 전문 지원 시스템 · 국내외 치안·공공안전 기술 동향 메타 분석")
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
        ("🧬 과학수사",      "#16a085"),
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
                    trl   = tech.get("trl", 1)
                    trl_c = trl_color(trl)
                    trl_bar = min(trl / 9 * 100, 100)
                    tags_html = "".join(f'<span class="domain-tag">{t}</span>' for t in tech.get("tags",[]))
                    is_today_item = tech.get("_date") == TODAY
                    today_mark = '<span style="background:#e53e3e;color:white;font-size:0.65rem;padding:2px 7px;border-radius:4px;margin-left:6px;">NEW</span>' if is_today_item else ""
                    st.markdown(f"""
                    <div class="tech-card">
                      <div class="card-title">
                        {tech.get('title','')} {today_mark}
                        <span class="trl-badge">TRL {trl}</span>
                      </div>
                      <div class="card-meta">📅 {tech.get('_date','')} </div>
                      <div style="margin:6px 0 4px;">
                        <div style="font-size:0.68rem; color:#7f8c8d; margin-bottom:3px;">기술 성숙도 (TRL {trl}/9)</div>
                        <div class="progress-outer">
                          <div class="progress-inner" style="width:{trl_bar:.0f}%; background:linear-gradient(90deg,{trl_c}88,{trl_c});">TRL {trl}</div>
                        </div>
                      </div>
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
                        c1, c2, c3 = st.columns(3)
                        c1.metric("기술 성숙도(TRL)", f"{trl} / 9")
                        c2.metric("수집 날짜", tech.get('_date',''))
                        c3.metric("분류 태그 수", len(tech.get('tags',[])))
                        st.markdown(f"""
**기술 상세 설명:**
{tech.get('detail','')}

**🔗 [원문/관련 기관 링크]({tech.get('url','#')})**
                        """)

    # ════════════════════════════════════════
    # 메인: 도메인 블록 그리드
    # ════════════════════════════════════════
    else:
        # 날짜 필터 — 오른쪽 정렬
        _, _, filt_col_main = st.columns([2, 2, 2])
        with filt_col_main:
            filter_opts = ["📊 전체 누적"] + [f"📅 {d}" for d in avail_dates]
            filter_sel  = st.selectbox("날짜 필터", options=filter_opts,
                                       label_visibility="collapsed",
                                       help="특정 날짜를 선택하면 해당 날짜 데이터만 블록에 표시됩니다.")

        # 필터 적용
        if filter_sel == "📊 전체 누적":
            block_items = all_items
            block_label = "누적 전체"
        else:
            chosen_date = filter_sel.replace("📅 ", "")
            chosen_day  = trend_data.get(chosen_date, {})
            block_items = []
            for item in chosen_day.get("issues", []):
                item = dict(item); item["_date"] = chosen_date; block_items.append(item)
            for item in chosen_day.get("technologies", []):
                item = dict(item); item["_date"] = chosen_date; block_items.append(item)
            block_label = chosen_date

        # 오늘 신규 이슈/기술 수
        _new_issues = sum(1 for it in all_items if it.get("_date") == TODAY and it.get("id","").startswith("I"))
        _new_techs  = sum(1 for it in all_items if it.get("_date") == TODAY and it.get("id","").startswith("T"))
        _c1, _c2, _c3, _c4 = st.columns(4)
        _c1.metric("📅 날짜", DISPLAY_DATE)
        _c2.metric("🚨 새 이슈", f"{_new_issues}개")
        _c3.metric("🔬 새 기술", f"{_new_techs}개")
        _c4.metric("📊 총합", f"{_new_issues + _new_techs}개")

        row1 = st.columns(3)
        row2 = st.columns(3)
        row3 = st.columns(3)
        row4_col = st.columns(1)[0]
        grid_cols = list(row1) + list(row2) + list(row3) + [row4_col]

        for col, (domain, color) in zip(grid_cols, DOMAINS):
            # 날짜 필터 적용된 블록 카운트 (블록 숫자 표시용)
            domain_items  = [it for it in block_items if it.get("domain") == domain]
            is_new        = domain in today_domains
            issue_cnt     = sum(1 for it in domain_items if it.get("id","").startswith("I"))
            tech_cnt      = sum(1 for it in domain_items if it.get("id","").startswith("T"))
            total_cnt     = len(domain_items)
            today_cnt     = sum(1 for it in domain_items if it.get("_date") == TODAY)

            with col:
                dot = '<span style="display:inline-block;width:7px;height:7px;background:#ef4444;border-radius:50%;margin-left:5px;vertical-align:super;"></span>' if is_new else ""
                st.markdown(f"""
                <div style="background:#fff; border:1px solid #e5e7eb;
                     border-top:3px solid {color}; border-radius:8px;
                     padding:0.8rem 1rem 0.7rem; margin-bottom:0rem;
                     box-shadow:0 1px 3px rgba(0,0,0,0.05);">
                  <div style="font-size:0.85rem; font-weight:600; color:#111827;
                       margin-bottom:0.65rem; line-height:1.3;">{domain}{dot}</div>
                  <div style="display:flex; border-top:1px solid #f3f4f6; padding-top:0.5rem;">
                    <div style="flex:1; text-align:center;">
                      <div style="font-size:1.45rem; font-weight:700; color:#111827;">{issue_cnt}</div>
                      <div style="font-size:0.7rem; color:#9ca3af; margin-top:2px;">이슈</div>
                    </div>
                    <div style="width:1px; background:#f3f4f6;"></div>
                    <div style="flex:1; text-align:center;">
                      <div style="font-size:1.45rem; font-weight:700; color:#111827;">{tech_cnt}</div>
                      <div style="font-size:0.7rem; color:#9ca3af; margin-top:2px;">기술</div>
                    </div>
                    <div style="width:1px; background:#f3f4f6;"></div>
                    <div style="flex:1; text-align:center;">
                      <div style="font-size:1.45rem; font-weight:700; color:{color};">{total_cnt}</div>
                      <div style="font-size:0.7rem; color:#9ca3af; margin-top:2px;">합계</div>
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
                bc1, bc2, bc3 = st.columns(3)
                with bc1:
                    if st.button("이슈", key=f"btn_iss_{domain}", use_container_width=True,
                                 disabled=(issue_cnt==0)):
                        st.session_state.dash_domain = domain
                        st.session_state.dash_filter = "issues"
                        st.rerun()
                with bc2:
                    if st.button("기술", key=f"btn_tec_{domain}", use_container_width=True,
                                 disabled=(tech_cnt==0)):
                        st.session_state.dash_domain = domain
                        st.session_state.dash_filter = "techs"
                        st.rerun()
                with bc3:
                    if st.button("전체", key=f"btn_all_{domain}", use_container_width=True,
                                 disabled=(total_cnt==0)):
                        st.session_state.dash_domain = domain
                        st.session_state.dash_filter = "all"
                        st.rerun()
                st.markdown("<div style='margin-bottom:0.4rem;'></div>", unsafe_allow_html=True)


    # ─────────────────────────────────────────────
    # TODAY 브리핑 섹션
    # ─────────────────────────────────────────────
    st.subheader(f"📡 TODAY 브리핑  —  {DISPLAY_DATE}")
    if DISPLAY_DATE != TODAY:
        st.caption("⚠️ 오늘 데이터 미수집 · 최근 날짜 표시")

    if not today_all:
        st.info(f"📭 오늘({TODAY}) 수집된 데이터가 없습니다. 수집 파이프라인 상태를 확인하세요.")
    else:
        # 이슈 파트
        if today_issues:
            st.markdown("""
            <div class="section-divider">
              <span class="divider-label">🚨 오늘의 치안 이슈</span>
            </div>
            """, unsafe_allow_html=True)
            for issue in today_issues:
                sev = severity_label(issue.get("severity", ""))
                tags_html = "".join(f'<span class="domain-tag">{t}</span>' for t in issue.get("tags", []))
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
> ⚠️ 외부 링크는 해당 기관 공식 페이지로 연결됩니다.
                    """)

        # 기술 파트
        if today_techs:
            st.markdown("""
            <div class="section-divider">
              <span class="divider-label">🔬 오늘의 치안 기술</span>
            </div>
            """, unsafe_allow_html=True)
            for tech in today_techs:
                trl   = tech.get("trl", 1)
                trl_c = trl_color(trl)
                tags_html = "".join(f'<span class="domain-tag">{t}</span>' for t in tech.get("tags",[]))
                trl_bar   = min(trl / 9 * 100, 100)
                st.markdown(f"""
                <div class="tech-card">
                  <div class="card-title">
                    {tech.get('title','')}
                    <span class="trl-badge">TRL {trl}</span>
                  </div>
                  <div class="card-meta">{tech.get('domain','')}</div>
                  <div style="margin:6px 0 4px;">
                    <div style="font-size:0.68rem; color:#7f8c8d; margin-bottom:3px;">기술 성숙도 (TRL {trl}/9)</div>
                    <div class="progress-outer">
                      <div class="progress-inner" style="width:{trl_bar:.0f}%; background:linear-gradient(90deg,{trl_c}88,{trl_c});">
                        TRL {trl}
                      </div>
                    </div>
                  </div>
                  <div class="card-body">{tech.get('summary','')}</div>
                  <div style="margin-top:0.5rem;">{tags_html}</div>
                </div>
                """, unsafe_allow_html=True)
                with st.expander(f"📂 기술 심층 데이터 — {tech.get('title','')[:35]}…"):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("기술 성숙도(TRL)", f"{trl} / 9")
                    c2.metric("분류 도메인", tech.get('domain',''))
                    c3.metric("분류 태그 수", len(tech.get('tags',[])))
                    st.markdown(f"""
**기술 상세 설명:**
{tech.get('detail','')}

**🔗 [원문/관련 기관 링크]({tech.get('url','#')})**
                    """)


# ═══════════════════════════════════════════════════════════
# PAGE 2: 아이디어 — 누적 동향 기반 과학기술 치안 접목 카드
# ═══════════════════════════════════════════════════════════
elif menu == "💡 아이디어":

    IDEA_PATH = "data/idea_cards.json"

    @st.cache_data(ttl=300)
    def load_ideas():
        if os.path.exists(IDEA_PATH):
            with open(IDEA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    ideas = load_ideas()

    st.markdown("## 💡 치안 접목 가능 과학기술 아이디어")
    st.markdown("""
    <div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px;
         padding:0.9rem 1.2rem; margin-bottom:1.2rem;">
      <p style="color:#1e40af; font-size:0.87rem; margin:0;">
        📡 일반 과학기술 뉴스·동향을 분석하여 치안 현장에 접목 가능한 기술 아이디어를 정리합니다.<br>
        <b>기술 중심</b>으로 해결 가능한 치안 이슈를 도출합니다. 매일 09:00 업데이트.
      </p>
    </div>
    """, unsafe_allow_html=True)

    DOMAIN_OPTS_9 = [
        "전체", "🤖 AI·보안", "🔍 수사", "📜 법·제도",
        "🌐 국제 치안", "🚓 신종 범죄", "🏘️ 생활 안전",
        "🚗 교통", "🛠️ 장비", "🧬 과학수사"
    ]

    fc1, fc2 = st.columns([2, 4])
    with fc1:
        idea_domain_filter = st.selectbox("도메인 필터", DOMAIN_OPTS_9, label_visibility="collapsed")
    with fc2:
        idea_search = st.text_input("기술명·키워드 검색", placeholder="예: 양자암호, 연합학습, 위성 …", label_visibility="collapsed")

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
        st.info("조건에 맞는 아이디어가 없습니다. 데이터가 매일 09:00에 업데이트됩니다.")
    else:
        for idea in filtered_ideas:
            domain   = idea.get("domain", "")
            tech     = idea.get("tech_name", "")
            date     = idea.get("date", "")
            issue    = idea.get("target_issue", "")
            tags     = idea.get("tags", [])
            tags_html = "".join(f'<span class="domain-tag">{t}</span>' for t in tags)
            is_new   = date == datetime.now().strftime("%Y-%m-%d")
            new_mark = '<span style="background:#e74c3c;color:white;font-size:0.62rem;font-weight:700;padding:1px 7px;border-radius:99px;margin-left:6px;">NEW</span>' if is_new else ""

            st.markdown(f"""
            <div style="background:#f0f7ff; border:1px solid #bfdbfe;
                 border-left:4px solid #2563eb; border-radius:8px;
                 padding:0.9rem 1.1rem; margin-bottom:0.6rem;
                 box-shadow:0 1px 3px rgba(0,0,0,0.05);">
              <div style="display:flex; align-items:center; gap:8px; margin-bottom:0.4rem;">
                <span style="font-size:0.78rem; color:#1d4ed8; font-weight:600;">{domain}</span>
                <span style="font-size:0.7rem; color:#6b7280;">📅 {date}</span>
                {new_mark}
              </div>
              <div style="font-size:1rem; font-weight:700; color:#111827; margin-bottom:0.3rem;">{tech}</div>
              <div style="font-size:0.82rem; color:#374151; margin-bottom:0.5rem;">
                🎯 해결 가능 치안 이슈: <b>{issue}</b>
              </div>
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
    <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px;
         padding:0.9rem 1.2rem; margin-bottom:1.2rem;">
      <p style="color:#14532d; font-size:0.87rem; margin:0;">
        📡 누적 치안 이슈를 바탕으로 추진 배경을 설정하고, 관련 기술들을 조합하여 R&amp;D 사업기획서 초안을 생성합니다.<br>
        <b>이슈 → 기술</b> 방향으로 기획. 좋은 조합이 형성될 때마다 업데이트됩니다.
      </p>
    </div>
    """, unsafe_allow_html=True)

    if not rfp_cards:
        st.info("📭 아직 생성된 RFP 초안이 없습니다. 치안 이슈가 누적되면 자동 업데이트됩니다.")
    else:
        rfp_domain_filter = st.selectbox(
            "도메인 필터",
            ["전체"] + list({r.get("domain","") for r in rfp_cards}),
            label_visibility="collapsed"
        )
        shown_rfps = [r for r in rfp_cards if rfp_domain_filter == "전체" or r.get("domain") == rfp_domain_filter]

        for rfp in shown_rfps:
            is_new = rfp.get("date","") == datetime.now().strftime("%Y-%m-%d")
            new_mark = '<span style="background:#e74c3c;color:white;font-size:0.62rem;padding:1px 7px;border-radius:99px;margin-left:6px;">NEW</span>' if is_new else ""
            tags_html = "".join(f'<span class="domain-tag">{t}</span>' for t in rfp.get("tags",[]))

            st.markdown(f"""
            <div style="background:#f0fdf4; border:1px solid #bbf7d0;
                 border-left:5px solid #16a34a; border-radius:8px;
                 padding:1rem 1.2rem; margin-bottom:0.8rem;
                 box-shadow:0 1px 3px rgba(0,0,0,0.05);">
              <div style="display:flex; align-items:center; gap:8px; margin-bottom:0.4rem;">
                <span style="font-size:0.75rem; color:#15803d; font-weight:600;">{rfp.get("domain","")}</span>
                <span style="font-size:0.7rem; color:#6b7280;">📅 {rfp.get("date","")}</span>
                {new_mark}
              </div>
              <div style="font-size:1.05rem; font-weight:700; color:#111827; margin-bottom:0.3rem;">
                {rfp.get("title","")}
              </div>
              <div style="font-size:0.82rem; color:#374151; margin-bottom:0.5rem;">
                💰 {rfp.get("budget","")}
              </div>
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

                # 기대 효과
                st.markdown("### ✅ 기대 효과")
                st.success(rfp.get("effect",""))

                # 아키텍처 다이어그램
                if rfp.get("diagram"):
                    st.markdown("### 📐 사업 구상 아키텍처")
                    st.markdown(f"```mermaid\n{rfp.get('diagram','')}\n```")


# ═══════════════════════════════════════════════════════════
# PAGE 4: 유사 과제 — NTiS 국가 R&D 과제 모니터링
# ═══════════════════════════════════════════════════════════
elif menu == "📋 유사 과제":

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
        새로운 과제가 등록되면 자동으로 리스트업됩니다.
      </p>
    </div>
    """, unsafe_allow_html=True)

    # 검색 필터
    nc1, nc2, nc3 = st.columns([2, 1, 1])
    with nc1:
        ntis_search = st.text_input("과제명·기관·키워드 검색", placeholder="예: 딥페이크, ETRI, 드론 …", label_visibility="collapsed")
    with nc2:
        ntis_year = st.selectbox("연도", ["전체", "2025", "2024", "2023", "2022"], label_visibility="collapsed")
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
                st.caption("총 연구기관")
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
  🚔 치안 과학기술 동향 인텔리전스 플랫폼 v1.0 &nbsp;|&nbsp; Powered by KIPOT (kipot.or.kr)
  &nbsp;|&nbsp; 데이터 기준: {datetime.now().strftime('%Y.%m.%d')} &nbsp;|&nbsp;
  수집 범위: 경찰청·국과수·NIJ·INTERPOL·Europol·EU AI Act 외
</div>
""", unsafe_allow_html=True)
