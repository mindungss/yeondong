"""
sync_notion.py — Notion DB → JSON 동기화 스크립트
치안 과학기술 동향 플랫폼 | KIPOT v2.0

노션 속성명 매핑 (이미지 기준):
  아이디어 DB: 기술명/날짜/도메인/해결 이슈/태그/기술 특징/적용 분야/제한 사항/주요 기업 및 제품/기술 동향
  유사과제 DB: 과제명/주관 기관/총 연구비/도메인/키워드/등록일/총 연구 기간/연구 목표/연구 내용
  RFP DB: 하위 페이지 구조 파싱 (제안 이력 → 각 페이지)
"""

import os, json, sys, logging, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from notion_client import Client
from notion_client.errors import APIResponseError

# ─────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger(__name__)

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
DB_DAILY     = os.environ.get("NOTION_DB_DAILY", "34b498eef53381b896bafae457a8199e")  # 일일 리포트 페이지 ID
DB_TREND     = os.environ.get("NOTION_DB_TREND", "")
DB_IDEA      = os.environ.get("NOTION_DB_IDEA", "")
DB_RFP       = os.environ.get("NOTION_DB_RFP", "")
DB_NTIS      = os.environ.get("NOTION_DB_NTIS", "")

DATA_DIR     = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
KST          = timezone(timedelta(hours=9))
TODAY_KST    = datetime.now(KST).strftime("%Y-%m-%d")

# ─────────────────────────────────────────────
# 공통 헬퍼
# ─────────────────────────────────────────────
def _text(blocks):
    return "".join(b.get("plain_text", "") for b in (blocks or [])).strip()

def get_title(props, *keys):
    for k in keys:
        v = _text(props.get(k, {}).get("title", []))
        if v: return v
    return ""

def get_rt(props, *keys):
    for k in keys:
        v = _text(props.get(k, {}).get("rich_text", []))
        if v: return v
    return ""

def get_select(props, *keys):
    for k in keys:
        s = props.get(k, {}).get("select")
        if s: return s.get("name", "")
    return ""

def get_multi(props, *keys):
    for k in keys:
        items = props.get(k, {}).get("multi_select", [])
        if items: return [i.get("name","") for i in items]
    return []

def get_date(props, *keys):
    for k in keys:
        d = props.get(k, {}).get("date")
        if d and d.get("start"): return d["start"][:10]
    return ""

def get_num(props, *keys, default=0):
    for k in keys:
        v = props.get(k, {}).get("number")
        if v is not None: return v
    return default

def get_url(props, *keys):
    for k in keys:
        v = props.get(k, {}).get("url")
        if v: return v
    return ""

def get_checkbox(props, *keys):
    for k in keys:
        if props.get(k, {}).get("checkbox"): return True
    return False

def all_pages(notion, db_id, filt=None):
    rows, cursor = [], None
    while True:
        params = {"database_id": db_id, "page_size": 100}
        if filt:   params["filter"]       = filt
        if cursor: params["start_cursor"] = cursor
        try:
            resp = notion.databases.query(**params)
        except APIResponseError as e:
            log.error(f"API 오류 (DB:{db_id}): {e}")
            return rows
        rows.extend(resp.get("results", []))
        if not resp.get("has_more"): break
        cursor = resp.get("next_cursor")
    return rows

def load_json(path):
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return None
        return json.loads(content)
    except (json.JSONDecodeError, ValueError) as e:
        log.warning(f"JSON 파싱 오류 ({path.name}): {e} — 기존 데이터 초기화 후 재수집")
        return None

def save_json(path, data):
    """원자적 쓰기: 임시 파일에 먼저 쓰고 교체 (중간 실패 시 기존 파일 보존)"""
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)   # 원자적 교체
        log.info(f"저장: {path.name} ({len(data) if isinstance(data,(list,dict)) else '?'}건)")
    except Exception as e:
        log.error(f"저장 실패 ({path.name}): {e}")
        if tmp.exists(): tmp.unlink()
        raise

# ─────────────────────────────────────────────
# 노션 페이지 블록 전체 읽기 (하위 페이지용)
# ─────────────────────────────────────────────
def _fetch_children(notion, block_id):
    """한 블록의 직속 자식 블록 목록만 반환 (페이지네이션 처리)"""
    rows, cursor = [], None
    while True:
        params = {"block_id": block_id, "page_size": 100}
        if cursor: params["start_cursor"] = cursor
        try:
            resp = notion.blocks.children.list(**params)
        except APIResponseError as e:
            log.error(f"블록 읽기 오류: {e}")
            break
        rows.extend(resp.get("results", []))
        if not resp.get("has_more"): break
        cursor = resp.get("next_cursor")
    return rows

def get_all_blocks(notion, block_id, _depth=0):
    """
    페이지/블록의 모든 블록을 수집.
    toggle · bulleted_list_item 등 자식을 가진 블록은
    자식 블록을 함께 수집하되, 부모 블록에 _children 키로 첨부.
    (최대 깊이 5 — 무한 재귀 방지)
    """
    if _depth > 5:
        return []
    blocks = _fetch_children(notion, block_id)
    for block in blocks:
        btype = block.get("type", "")
        has_children = block.get("has_children", False)
        # toggle, bulleted_list_item, numbered_list_item, quote 등 자식 있는 블록 재귀
    if has_children and btype in (
        "toggle", "bulleted_list_item", "numbered_list_item",
        "quote", "callout", "column", "column_list", "table"
    ):
            block["_children"] = get_all_blocks(notion, block["id"], _depth + 1)
    return blocks

def block_text(block):
    """단일 블록에서 텍스트 추출"""
    btype = block.get("type", "")
    content = block.get(btype, {})
    rich = content.get("rich_text", [])
    return _text(rich)

def blocks_to_text(blocks, indent=0):
    """블록 리스트 → 줄바꿈 연결 텍스트 (toggle 자식 포함 재귀)"""
    lines = []
    prefix = "  " * indent
    for b in blocks:
        btype = b.get("type", "")
        t = block_text(b)
        if t:
            bullet = "• " if btype == "bulleted_list_item" else (
                     f"{b.get('numbered_list_item',{}).get('number','')}. " if btype == "numbered_list_item" else "")
            lines.append(f"{prefix}{bullet}{t}")
        # toggle 자식 포함
        children = b.get("_children", [])
        if children:
            lines.append(blocks_to_text(children, indent + 1))
    return "\n".join(l for l in lines if l)

# ─────────────────────────────────────────────
# RFP 하위 페이지 파싱
# ─────────────────────────────────────────────
def parse_rfp_page(notion, page_id, page_title, page_date):
    """하위 호환용 래퍼 — page_id로 블록 읽어서 parse_rfp_page_from_blocks 호출"""
    blocks = get_all_blocks(notion, page_id)
    return parse_rfp_page_from_blocks(notion, blocks, page_title, page_date)

def parse_rfp_page_from_blocks(notion, blocks, page_title, page_date):
    """
    노션 RFP 페이지 블록 파싱.

    실제 노션 구조:
      - heading_1 : "1. 추진 배경" 등 대섹션 → 섹션 전환
      - heading_2 : "[기술 N] 기술명" (주요기술 항목) 또는 "1단계 ..." (추진내용 단계)
                    또는 "정량적/정성적 기대 효과" (기대효과 소제목)
      - paragraph : 기술 설명 본문 / 배경 / 목표 텍스트
      - table     : 세부목표 표
      - bulleted_list_item : 기대효과 항목 / 추진내용 세부항목
      - toggle    : 추진내용 단계 (toggle 형태인 경우)

    핵심 전략:
      heading_1 → 대섹션 전환 (background/goal/core_techs_raw/kpis_raw/phases_raw/effect)
      heading_2 → 소섹션 (기술항목 / 단계) : 대섹션 안에서만 소섹션 역할
      나머지 블록 → 현재 대섹션 또는 소섹션에 적재
    """
    # 대섹션 매핑 (heading_1 기준, 숫자 제거 후 매칭)
    # ── 과제 개요 테이블에서 budget + 과제 분류(domain) 추출
    budget = ""
    raw_domain = ""
    _in_overview = False
    for block in blocks:
        btype = block.get("type","")
        txt   = block_text(block).strip()
        if btype in ("heading_1","heading_2","heading_3"):
            _in_overview = "과제 개요" in txt
            if _in_overview:
                log.info(f"[rfp] 과제 개요 섹션 진입: {txt[:30]}")
            continue
        if _in_overview and btype == "table":
            log.info(f"[rfp] 과제 개요 table 블록 발견: {block.get('id','')[:8]}")
            children = block.get("_children") or []
            if not children:
                try:
                    resp = notion.blocks.children.list(block_id=block["id"])
                    children = resp.get("results", [])
                except Exception as e:
                    log.warning(f"[rfp] table 행 읽기 실패: {e}")
            log.info(f"[rfp] table 행 수: {len(children)}")
            for row in children:
                cells = row.get("table_row", {}).get("cells", [])
                if len(cells) >= 2:
                    label = _text(cells[0])
                    value = _text(cells[1])
                    log.info(f"[rfp]   행: label={repr(label)} value={repr(value)}")
                    if "연구 비용" in label or "연구비" in label or "예산" in label:
                        budget = value
                    elif "과제 분류" in label or "분류" in label:
                        raw_domain = value
            if budget and raw_domain:
                break

    log.info(f"[rfp] 추출된 budget={repr(budget)} raw_domain={repr(raw_domain)}")

    # 노션 자유 텍스트 도메인 → 표준 10개 도메인으로 정규화
    DOMAIN_NORMALIZE = {
        "AI":       "🤖 AI",
        "보안":     "🔐 사이버 보안",
        "국제":     "🌐 국제 치안",
        "과학수사": "🧬 과학 수사",
        "과학 수사":"🧬 과학 수사",
        "교통":     "🚗 교통",
        "마약":     "💊 마약",
        "법":       "📜 법·제도",
        "제도":     "📜 법·제도",
        "생활":     "🏘️ 생활 안전",
        "신종":     "🚓 신종 범죄",
        "장비":     "🛠️ 장비",
    }
    domain = ""
    _clean_domain = re.sub(r"[^\w가-힣]", "", raw_domain)
    for kw, std in DOMAIN_NORMALIZE.items():
        if kw in _clean_domain:
            domain = std
            break
    if not domain and raw_domain:
        domain = raw_domain  # 매칭 안 되면 원본 그대로

    MAJOR_MAP = {
        "추진 배경":  "background",
        "최종 목표":  "goal",
        "주요 기술":  "core_techs_raw",
        "세부 목표":  "kpis_raw",
        "추진 내용":  "phases_raw",
        "기대 효과":  "effect_raw",
    }

    major    = None   # 현재 대섹션
    sections = {v: [] for v in MAJOR_MAP.values()}

    for block in blocks:
        btype = block.get("type", "")
        txt   = block_text(block).strip()

        # divider 만나면 effect 섹션 종료 (마지막 안내문/구분선 이후 텍스트 제외)
        if btype == "divider":
            if major == "effect_raw":
                major = None
            continue

        # heading_1 → 대섹션 전환
        if btype == "heading_1":
            clean   = re.sub(r"^\d+[\.\s]+", "", txt).strip()
            matched = next((v for k, v in MAJOR_MAP.items() if clean.startswith(k)), None)
            if matched:
                major = matched
            continue  # heading_1 자체는 저장 안 함

        # heading_2/3 처리
        if btype in ("heading_2", "heading_3"):
            clean   = re.sub(r"^\d+[\.\s]+", "", txt).strip()
            # 대섹션 키워드는 heading_2에서만, 그리고 정확히 "숫자.제목" 형태로 시작할 때만 매칭
            # (예: "정량적 기대 효과"가 "기대 효과"를 부분 포함하는 오인식 방지)
            matched = None
            if btype == "heading_2":
                matched = next((v for k, v in MAJOR_MAP.items() if clean.startswith(k)), None)
            if matched:
                # 대섹션 키워드 → 섹션 전환만 (저장 안 함)
                major = matched
                continue
            else:
                # 대섹션 키워드 아닌 heading_2/3 → 현재 섹션에 저장 (기술항목/단계/소제목)
                if major:
                    sections[major].append(block)
                continue

        # 나머지 블록은 현재 대섹션에 저장
        if major:
            sections[major].append(block)

    # ─────────────────────────
    # background / goal : 전체 텍스트
    # ─────────────────────────
    background = blocks_to_text(sections["background"])
    goal       = blocks_to_text(sections["goal"])

    # ─────────────────────────
    # core_techs : heading_2([기술 N]) + 이후 paragraph 묶음
    # ─────────────────────────
    core_techs = []
    cur_name, cur_lines = None, []

    for block in sections["core_techs_raw"]:
        btype = block.get("type", "")
        txt   = block_text(block).strip()

        is_tech_heading = (
            btype in ("heading_2", "heading_3") or
            btype == "toggle"
        ) and bool(re.search(r"\[?기술\s*\d+\]?", txt))

        if is_tech_heading:
            # 직전 기술 저장
            if cur_name:
                core_techs.append({"name": cur_name, "desc": "\n".join(cur_lines).strip()})
            # 새 기술 시작 — "[기술 N] " 접두사 제거
            cur_name  = re.sub(r"^\[기술\s*\d+\]\s*", "", txt).strip()
            cur_lines = []
            # toggle이면 _children이 desc
            if btype == "toggle":
                children = block.get("_children", [])
                if children:
                    cur_lines.append(blocks_to_text(children))

        elif cur_name:
            # paragraph / bulleted 등 → 현재 기술 설명에 추가
            if btype == "bulleted_list_item":
                cur_lines.append("• " + txt)
            elif txt:
                cur_lines.append(txt)

    if cur_name:
        core_techs.append({"name": cur_name, "desc": "\n".join(cur_lines).strip()})

    # ─────────────────────────
    # kpis : table 블록 파싱 (첫 행 헤더 스킵)
    # ─────────────────────────
    kpis = []
    for block in sections["kpis_raw"]:
        if block.get("type") == "table":
            # _children에 이미 있거나 API 재호출
            children = block.get("_children") or []
            if not children:
                try:
                    resp     = notion.blocks.children.list(block_id=block["id"])
                    children = resp.get("results", [])
                except Exception as e:
                    log.warning(f"KPI 표 행 읽기 오류: {e}")
            for row in children[1:]:  # 첫 행(헤더) 스킵
                cells = row.get("table_row", {}).get("cells", [])
                if len(cells) >= 2:
                    label  = _text(cells[0])
                    value  = _text(cells[1]) if len(cells) > 1 else ""
                    reason = _text(cells[2]) if len(cells) > 2 else ""
                    if label:
                        kpis.append({"label": label, "value": value, "reason": reason})
        else:
            # 표 없는 경우 "항목: 값" 형식 텍스트 파싱
            txt = block_text(block).strip()
            if txt:
                m = re.match(r"^(.+?)[:：]\s*(.+)", txt)
                if m:
                    kpis.append({"label": m.group(1).strip(),
                                 "value": m.group(2).strip(), "reason": ""})

    # ─────────────────────────
    # phases : heading_2(N단계...) + 이후 bulleted/paragraph 묶음
    #          또는 toggle(N단계) + _children
    # ─────────────────────────
    phases = []
    cur_phase, cur_phase_lines = None, []

    for block in sections["phases_raw"]:
        btype = block.get("type", "")
        txt   = block_text(block).strip()

        is_phase_heading = bool(re.match(r"\d+단계", txt))

        if is_phase_heading and btype in ("heading_2", "heading_3", "toggle", "paragraph"):
            if cur_phase:
                phases.append({"label": cur_phase, "content": "\n".join(cur_phase_lines).strip()})
            cur_phase       = txt
            cur_phase_lines = []
            # toggle이면 _children을 즉시 content로
            if btype == "toggle":
                children = block.get("_children", [])
                if children:
                    cur_phase_lines.append(blocks_to_text(children))

        elif cur_phase:
            if btype == "bulleted_list_item":
                cur_phase_lines.append("• " + txt)
            elif txt:
                cur_phase_lines.append(txt)

    if cur_phase:
        phases.append({"label": cur_phase, "content": "\n".join(cur_phase_lines).strip()})

    # ─────────────────────────
    # effect : 모든 텍스트 (heading_2 소제목 포함)
    # ─────────────────────────
    effect_lines = []
    for block in sections["effect_raw"]:
        btype = block.get("type", "")
        txt   = block_text(block).strip()
        if not txt:
            continue
        if btype in ("heading_2", "heading_3"):
            effect_lines.append(f"\n[{txt}]")
        elif btype == "bulleted_list_item":
            effect_lines.append("• " + txt)
            # bulleted 자식도 포함 (들여쓰기)
            for child in block.get("_children", []):
                ct = block_text(child).strip()
                if ct:
                    effect_lines.append("  - " + ct)
        else:
            effect_lines.append(txt)
    effect = "\n".join(effect_lines).strip()

    date_compact = (page_date or TODAY_KST).replace("-","")[2:]
    return {
        "id":         f"RFP-{date_compact}TEMP",
        "date":       page_date or TODAY_KST,
        "domain":     domain,
        "title":      page_title,
        "budget":     budget,
        "tags":       [],
        "background": background,
        "goal":       goal,
        "core_techs": core_techs,
        "kpis":       kpis,
        "phases":     phases,
        "effect":     effect,
        "diagram":    "",
    }

# ─────────────────────────────────────────────
# 0. daily_reports.json  ← 일일 리포트 페이지
#    노션 구조: 페이지(DB_DAILY) 안의 child_database 또는 database rows
#    DB_DAILY = 34b498ee... 는 page이므로 blocks.children으로 DB 찾기
# ─────────────────────────────────────────────
def sync_daily(notion):
    """
    메인 페이지 구조:
      ## 📅 일자별 분석
        <page>2026-06-15 (월요일)</page>   ← link_to_page 또는 child_page
        <page>2026-06-12 (금요일)</page>

    날짜 페이지 내부:
      #### 📰 치안 이슈 동향
      #### 🤖 AI
      - **제목**
          - 주요 내용: ...
          - 출처: [링크](url)
          - 태그: `#a` `#b`
          - 시사점: ...
      #### 🔬 치안 기술 동향
      ...
    """
    path     = DATA_DIR / "daily_reports.json"
    existing = load_json(path) or {}

    if not DB_DAILY:
        log.info("[daily] DB_DAILY 미설정 → 스킵"); return False

    # ── 1단계: 메인 페이지 블록 전체 읽기
    try:
        top_blocks = _fetch_children(notion, DB_DAILY)
    except Exception as e:
        log.error(f"[daily] 페이지 읽기 실패: {e}"); return False

    log.info(f"[daily] 메인 페이지 블록 수: {len(top_blocks)}")
    for i, b in enumerate(top_blocks[:20]):
        log.info(f"[daily] [{i:02d}] type={b.get('type','')} / {block_text(b)[:50]}")

    # ── 2단계: 날짜 페이지 ID 수집
    # 방법1: child_page 블록 (제목에 날짜 포함)
    # 방법2: link_to_page 블록
    # 방법3: "일자별 분석" heading의 자식 블록
    date_page_map = {}  # {날짜: page_id}

    def extract_date_pages(blocks):
        for b in blocks:
            btype = b.get("type","")
            # child_page: 제목에 날짜 포함
            if btype == "child_page":
                title = b.get("child_page", {}).get("title", "")
                dm = re.search(r"(\d{4}-\d{2}-\d{2})", title)
                if dm:
                    date_page_map[dm.group(1)] = b.get("id","")
                    log.info(f"[daily] child_page 날짜: {dm.group(1)}")
            # link_to_page
            elif btype == "link_to_page":
                pid = b.get("link_to_page", {}).get("page_id","")
                if pid:
                    # 페이지 제목 조회
                    try:
                        p = notion.pages.retrieve(page_id=pid)
                        title = ""
                        props = p.get("properties",{})
                        for v in props.values():
                            if v.get("type") == "title":
                                title = "".join(t.get("plain_text","") for t in v.get("title",[]))
                                break
                        dm = re.search(r"(\d{4}-\d{2}-\d{2})", title)
                        if dm:
                            date_page_map[dm.group(1)] = pid
                            log.info(f"[daily] link_to_page 날짜: {dm.group(1)}")
                    except Exception as e:
                        log.warning(f"[daily] link_to_page 조회 실패: {e}")

    # 직속 블록에서 찾기
    extract_date_pages(top_blocks)

    # 못 찾으면 "일자별 분석" heading 자식에서 찾기
    if not date_page_map:
        for b in top_blocks:
            btype = b.get("type","")
            txt   = block_text(b).strip()
            if btype in ("heading_1","heading_2","heading_3") and "일자별" in txt and b.get("has_children"):
                try:
                    sub = _fetch_children(notion, b["id"])
                    log.info(f"[daily] '일자별 분석' 자식 블록 수: {len(sub)}")
                    for sb in sub[:10]:
                        log.info(f"[daily]   자식 type={sb.get('type','')} / {block_text(sb)[:50]}")
                    extract_date_pages(sub)
                except Exception as e:
                    log.warning(f"[daily] 일자별 자식 읽기 실패: {e}")
                break

    log.info(f"[daily] 발견된 날짜 페이지: {list(date_page_map.keys())}")

    if not date_page_map:
        log.info("[daily] 날짜 페이지 없음 → 스킵"); return False

    latest_date = max(date_page_map.keys())
    log.info(f"[daily] 최신 날짜: {latest_date}")

    if latest_date != TODAY_KST:
        log.info(f"[daily] {latest_date} ≠ 오늘({TODAY_KST}) → 신규 없음 스킵")
        trend_path = DATA_DIR / "trend_data.json"
        if trend_path.exists():
            trend = load_json(trend_path) or {}
            added = {k:v for k,v in trend.items() if k not in existing}
            if added:
                merged = dict(sorted({**existing, **added}.items(), reverse=True))
                save_json(path, merged)
                log.info(f"[daily] fallback trend_data {len(added)}일 추가")
                return True
        return False

    if latest_date in existing:
        log.info(f"[daily] {latest_date} 이미 존재 → 스킵"); return False

    # ── 3단계: 날짜 페이지 블록 읽기 (재귀)
    target_id = date_page_map[latest_date]
    log.info(f"[daily] 날짜 페이지 읽기: {target_id}")

    def fetch_all(block_id, depth=0):
        if depth > 6: return []
        result = []
        try:
            children = _fetch_children(notion, block_id)
        except Exception as e:
            log.warning(f"[daily] 블록 읽기 오류: {e}"); return []
        for b in children:
            result.append(b)
            if b.get("has_children"):
                subs = fetch_all(b["id"], depth+1)
                b["_children"] = subs
        return result

    page_blocks = fetch_all(target_id)
    log.info(f"[daily] 날짜 페이지 블록 수: {len(page_blocks)}")
    for i, b in enumerate(page_blocks[:15]):
        log.info(f"[daily] [{i:02d}] type={b.get('type','')} / {block_text(b)[:60]}")

    # ── 4단계: 이슈/기술 파싱
    issues, techs = [], []
    cur_section = None
    cur_domain  = None
    issue_cnt = tech_cnt = 1

    for b in page_blocks:
        btype = b.get("type","")
        txt   = block_text(b).strip()

        if btype in ("heading_1","heading_2","heading_3","heading_4"):
            clean = txt.replace(" ","")
            if any(kw in txt for kw in SKIP_HEADINGS):
                cur_section = "skip"; continue
            if "치안이슈" in clean or "이슈동향" in clean:
                cur_section = "issue"; cur_domain = None
                log.info(f"[daily] → 이슈 섹션")
            elif "치안기술" in clean or "기술동향" in clean:
                cur_section = "tech"; cur_domain = None
                log.info(f"[daily] → 기술 섹션")
            elif cur_section in ("issue","tech") and txt:
                cur_domain = txt
                log.info(f"[daily] 도메인: {cur_domain}")
            continue

        if cur_section not in ("issue","tech") or not cur_domain:
            continue

        if btype == "bulleted_list_item":
            if "금일 주요 동향 없음" in txt: continue
            title = re.sub(r"\*\*(.+?)\*\*", r"\1", txt).strip()

            summary, source, tags, detail, url = "", "", [], "", ""
            for sub in b.get("_children", []):
                st = block_text(sub).strip()
                if st.startswith("요약"):
                    summary = re.sub(r"^요약\s*[:：]?\s*", "", st).strip()
                elif st.startswith("출처"):
                    source = re.sub(r"^출처\s*[:：]?\s*", "", st).strip()
                    um = re.search(r"\((https?://[^\)]+)\)", source)
                    if um: url = um.group(1)
                    source = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", source)
                elif st.startswith("태그") or "#" in st:
                    raw_t = re.sub(r"^태그\s*[:：]?\s*", "", st)
                    tags  = re.findall(r"#([^\s`#]+)", raw_t)
                elif st.startswith("주요 내용") or st.startswith("주요내용"):
                    detail = re.sub(r"^주요\s*내용\s*[:：]?\s*", "", st).strip()

            if not title: continue
            entry = {"domain": cur_domain, "title": title,
                     "summary": summary or title,
                     "detail": detail, "source": source, "url": url, "tags": tags}

            if cur_section == "issue":
                entry["id"] = f"I{latest_date.replace('-','')[2:]}{issue_cnt:04d}"
                entry["severity"] = "high" if any(w in title for w in
                    ["급증","적발","최초","위기","사망","테러","피해","유출"]) else "medium"
                issues.append(entry); issue_cnt += 1
                log.info(f"[daily] 이슈: [{cur_domain}] {title[:40]}")
            else:
                entry["id"] = f"T{latest_date.replace('-','')[2:]}{tech_cnt:04d}"
                entry["trl"] = 1
                techs.append(entry); tech_cnt += 1
                log.info(f"[daily] 기술: [{cur_domain}] {title[:40]}")

    if not issues and not techs:
        log.info("[daily] 파싱 항목 0건 → 스킵"); return False

    merged = dict(sorted({**existing, latest_date: {"issues": issues, "technologies": techs}}.items(), reverse=True))
    save_json(path, merged)
    log.info(f"[daily] 저장: {latest_date} | 이슈 {len(issues)}건, 기술 {len(techs)}건")
    return True


def sync_trend(notion):
    path     = DATA_DIR / "trend_data.json"
    existing = load_json(path) or {}
    pages    = all_pages(notion, DB_TREND)
    if not pages:
        log.info("[trend] 데이터 없음 → 스킵"); return False

    new_data = {}
    for page in pages:
        props  = page.get("properties", {})
        date   = get_date(props, "날짜", "Date") or TODAY_KST
        rtype  = get_select(props, "유형", "Type") or "이슈"
        pid    = page.get("id","").replace("-","")[:4].upper()
        if date not in new_data:
            new_data[date] = {"issues": [], "technologies": []}

        common = dict(
            title   = get_title(props, "제목", "Name", "Title") or "제목 없음",
            domain  = get_select(props, "도메인", "Domain"),
            summary = get_rt(props, "요약", "Summary"),
            detail  = get_rt(props, "상세", "Detail"),
            url     = get_url(props, "URL", "링크", "Link"),
            tags    = get_multi(props, "태그", "Tags"),
        )
        if rtype in ("기술","Technology","Tech"):
            new_data[date]["technologies"].append({
                "id": f"T{date.replace('-','')[2:]}{pid}", **common,
                "trl": int(get_num(props, "TRL", default=1)),
            })
        else:
            new_data[date]["issues"].append({
                "id":       f"I{date.replace('-','')[2:]}{pid}", **common,
                "severity": (get_select(props,"심각도","Severity") or "medium").lower(),
                "source":   get_rt(props, "출처","Source"),
            })

    if not new_data: log.info("[trend] 처리된 데이터 없음 → 스킵"); return False
    merged = dict(sorted({**existing, **new_data}.items(), reverse=True))
    save_json(path, merged)
    log.info(f"[trend] {len(new_data)}일 업데이트, 총 {len(merged)}일")
    return True

# ─────────────────────────────────────────────
# 2. idea_cards.json  ← 속성명 이미지 기준 재매핑
# ─────────────────────────────────────────────
def sync_ideas(notion):
    path     = DATA_DIR / "idea_cards.json"
    existing = load_json(path) or []
    log.info(f"[idea] DB_IDEA={DB_IDEA}")
    pages    = all_pages(notion, DB_IDEA)
    if not pages: log.info("[idea] 데이터 없음 → 스킵"); return False

    # 첫 페이지의 속성 키 목록을 로그에 출력 (디버그)
    if pages:
        _first_props = pages[0].get("properties", {})
        log.info(f"[idea] 속성 키 목록: {list(_first_props.keys())}")
        _pi_raw = _first_props.get("해결 가능 치안 이슈", {})
        log.info(f"[idea] '해결 가능 치안 이슈' 원본: {_pi_raw}")

    # ── 중복 체크: notion_id + id + tech_name 3중 방어
    exist_notion_ids = {i.get("notion_id") for i in existing if i.get("notion_id")}
    exist_ids        = {i.get("id") for i in existing}
    exist_names      = {i.get("tech_name","").strip() for i in existing if i.get("tech_name")}
    new_items = []
    for page in pages:
        props      = page.get("properties", {})
        notion_pid = page.get("id","").replace("-","")   # 32자 전체
        date       = get_date(props, "날짜", "Date") or TODAY_KST
        iid        = f"IDEA-{notion_pid[:12].upper()}"
        tech_name  = get_title(props, "기술명", "Name", "Tech")

        # 3중 중복 체크 — notion_id / id / tech_name 중 하나라도 있으면 스킵
        if (notion_pid in exist_notion_ids
                or iid in exist_ids
                or (tech_name and tech_name.strip() in exist_names)):
            continue

        new_items.append({
            "id":           iid,
            "notion_id":    notion_pid,   # 중복 방지용 영구 키
            "date":         date,
            "domain":       get_select(props, "도메인", "Domain"),
            # ▼ 이미지 기준: 기술명
            "tech_name":    get_title(props, "기술명", "Name", "Tech"),
            # ▼ 이미지 기준: 해결 이슈 (없으면 Target Issue)
            "policing_issues": get_rt(props, "해결 가능 치안 이슈"),
            "target_issue":    get_rt(props, "해결 이슈", "Target Issue"),
            "tags":         get_multi(props, "태그", "Tags"),
            # ▼ 이미지 기준: 기술 특징
            "features":     get_rt(props, "기술 특징", "Features"),
            # ▼ 이미지 기준: 적용 분야
            "applications": get_rt(props, "적용 분야", "Applications"),
            # ▼ 이미지 기준: 제한 사항
            "constraints":  get_rt(props, "제한 사항", "Constraints"),
            # ▼ 이미지 기준: 주요 기업 및 제품
            "companies":    get_rt(props, "주요 기업 및 제품", "주요 기업", "Companies"),
            # ▼ 이미지 기준: 기술 동향
            "trend":        get_rt(props, "기술 동향", "Trend"),
        })

    if not new_items: log.info("[idea] 신규 없음 → 스킵"); return False
    merged = new_items + existing
    save_json(path, merged)
    log.info(f"[idea] +{len(new_items)}건, 총 {len(merged)}건")
    return True

# ─────────────────────────────────────────────
# 3. rfp_cards.json  ← 하위 페이지 구조 파싱
# ─────────────────────────────────────────────
def _parse_date_from_title(raw_title: str):
    """
    "[2026-06-08] 과제명" 형식에서 날짜와 제목 분리.
    날짜가 없으면 (None, raw_title) 반환.
    """
    m = re.match(r"\[(\d{4}-\d{2}-\d{2})\]\s*(.*)", raw_title.strip())
    if m:
        return m.group(1), m.group(2).strip()
    return None, raw_title.strip()

def sync_rfp(notion):
    """
    RFP 노션 구조:
      NOTION_DB_RFP는 데이터베이스가 아니라 일반 페이지(page)임.
      그 페이지 안의 child_page 블록들이 각 RFP 항목.
      각 child_page 블록의 title = "[날짜] 과제명" 형식.
      child_page 블록의 id로 본문 블록을 읽어 파싱.

    접근 방식:
      1. DB_RFP page_id의 직속 블록 목록 조회 (blocks.children.list)
      2. type == "child_page" 인 블록만 필터링
      3. 각 child_page 의 id로 본문 블록 읽기
      4. parse_rfp_page_from_blocks() 로 내용 파싱
    """
    path     = DATA_DIR / "rfp_cards.json"
    existing = load_json(path) or []

    # DB_RFP = 상위 페이지 ID (데이터베이스 아님)
    # 직속 블록에서 child_page 목록 수집
    log.info(f"[rfp] 상위 페이지 블록 목록 조회: {DB_RFP}")
    top_blocks = get_all_blocks(notion, DB_RFP)
    child_pages = [b for b in top_blocks if b.get("type") == "child_page"]
    log.info(f"[rfp] child_page 발견: {len(child_pages)}개")

    if not child_pages:
        log.info("[rfp] child_page 없음 → 스킵")
        return False

    exist_ids = {r.get("id") for r in existing}
    new_items = []

    for block in child_pages:
        child_id    = block.get("id", "")
        raw_title   = block.get("child_page", {}).get("title", "") or ""

        # "[날짜] 제목" 파싱
        parsed_date, parsed_title = _parse_date_from_title(raw_title)
        page_date  = parsed_date or TODAY_KST
        page_title = parsed_title or raw_title or "제목 없음"
        pid_short  = child_id.replace("-","")[:4].upper()
        rfp_id     = f"RFP-{page_date.replace('-','')[2:]}{pid_short}"

        log.info(f"[rfp] 발견: id={rfp_id} title={page_title} child_id={child_id}")

        # id 기준 중복 체크만
        if rfp_id in exist_ids:
            log.info(f"[rfp] 이미 존재 → 스킵: {rfp_id}")
            continue

        log.info(f"[rfp] 파싱 시작: [{page_date}] {page_title}")
        try:
            content_blocks = get_all_blocks(notion, child_id)
            entry = parse_rfp_page_from_blocks(notion, content_blocks, page_title, page_date)
            entry["id"]     = rfp_id
            new_items.append(entry)
            log.info(f"  ✅ 기술 {len(entry['core_techs'])}개, KPI {len(entry['kpis'])}개, 단계 {len(entry['phases'])}개")
        except Exception as e:
            log.error(f"[rfp] 파싱 오류 ({page_title}): {e}")

    if not new_items: log.info("[rfp] 신규 없음 → 스킵"); return False
    merged = new_items + existing
    save_json(path, merged)
    log.info(f"[rfp] +{len(new_items)}건, 총 {len(merged)}건")
    return True

# ─────────────────────────────────────────────
# 4. ntis_projects.json  ← 속성명 이미지 기준 재매핑
# ─────────────────────────────────────────────
def sync_ntis(notion):
    path     = DATA_DIR / "ntis_projects.json"
    existing = load_json(path) or []
    pages    = all_pages(notion, DB_NTIS)
    if not pages: log.info("[ntis] 데이터 없음 → 스킵"); return False

    exist_ids  = {i.get("id") for i in existing}
    new_items, updated = [], []

    for page in pages:
        props      = page.get("properties", {})
        pid        = page.get("id","").replace("-","")[:8].upper()
        year_raw   = get_select(props, "연도", "Year") or get_rt(props, "연도", "Year")
        year       = str(year_raw)[:4] if year_raw else TODAY_KST[:4]
        iid        = f"NTIS-{year}-{pid}"
        registered = get_date(props, "등록일", "Registered") or ""
        is_new     = (registered == TODAY_KST) or get_checkbox(props, "신규", "Is New")

        entry = {
            "id":         iid,
            "title":      get_title(props, "과제명", "Name", "Title") or "",
            # ▼ 이미지 기준: 주관 기관
            "org":        get_rt(props, "주관 기관", "주관기관", "Org"),
            "year":       year,
            # ▼ 이미지 기준: 총 연구비
            "budget":     get_rt(props, "총 연구비", "총연구비", "Budget"),
            "domain":     get_select(props, "도메인", "Domain"),
            "keywords":   get_rt(props, "키워드", "Keywords"),
            "summary":    get_rt(props, "개요", "Summary"),
            "registered": registered,
            "is_new":     bool(is_new),
            "url":        get_url(props, "URL", "링크"),
            # ▼ 이미지 기준: 총 연구 기간 (참여기관 목록)
            "total_orgs": get_rt(props, "총 연구 기간", "총 연구 기간", "Total Orgs"),
            # ▼ 이미지 기준: 연구 목표
            "goal":       get_rt(props, "연구 목표", "연구목표", "Goal"),
            # ▼ 이미지 기준: 연구 내용
            "content":    get_rt(props, "연구 내용", "연구내용", "Content"),
        }
        if iid not in exist_ids:
            new_items.append(entry)
        else:
            updated.append(entry)

    if not new_items and not updated:
        log.info("[ntis] 신규/변경 없음 → 스킵"); return False

    upd_ids = {e["id"] for e in updated}
    kept    = [e for e in existing if e.get("id") not in upd_ids]
    merged  = new_items + updated + kept
    save_json(path, merged)
    log.info(f"[ntis] 신규 {len(new_items)}건, 업데이트 {len(updated)}건, 총 {len(merged)}건")
    return True

# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
def main():
    missing = [k for k,v in {
        "NOTION_TOKEN": NOTION_TOKEN, "NOTION_DB_TREND": DB_TREND,
        "NOTION_DB_IDEA": DB_IDEA,   "NOTION_DB_RFP":   DB_RFP,
        "NOTION_DB_NTIS": DB_NTIS,
    }.items() if not v]
    if missing:
        log.error(f"필수 환경변수 누락: {', '.join(missing)}")
        sys.exit(1)

    notion = Client(auth=NOTION_TOKEN)
    log.info(f"동기화 시작 | {TODAY_KST} KST")

    results, errors = {}, []
    for name, func, db_id in [
        ("daily", sync_daily, DB_DAILY),
        ("trend", sync_trend, DB_TREND), ("idea",  sync_ideas, DB_IDEA),
        ("rfp",   sync_rfp,   DB_RFP),   ("ntis",  sync_ntis,  DB_NTIS),
    ]:
        if not db_id:
            log.warning(f"[{name}] DB ID 미설정 → 스킵"); results[name] = False; continue
        try:
            results[name] = func(notion)
        except Exception as e:
            log.error(f"[{name}] 예외: {e}"); errors.append(name); results[name] = False

    updated = [k for k,v in results.items() if v]
    skipped = [k for k,v in results.items() if not v]
    log.info(f"완료 | 업데이트: {updated} | 스킵: {skipped} | 오류: {errors}")

    gout = os.environ.get("GITHUB_OUTPUT","")
    if gout:
        with open(gout,"a") as f:
            f.write(f"changed={'true' if updated else 'false'}\n")
    sys.exit(0)

if __name__ == "__main__":
    main()
