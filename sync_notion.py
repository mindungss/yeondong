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
    return json.load(open(path, encoding="utf-8")) if path.exists() else None

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"저장: {path}")

# ─────────────────────────────────────────────
# 노션 페이지 블록 전체 읽기 (하위 페이지용)
# ─────────────────────────────────────────────
def get_all_blocks(notion, block_id):
    """페이지의 모든 블록을 재귀적으로 수집"""
    blocks, cursor = [], None
    while True:
        params = {"block_id": block_id, "page_size": 100}
        if cursor: params["start_cursor"] = cursor
        try:
            resp = notion.blocks.children.list(**params)
        except APIResponseError as e:
            log.error(f"블록 읽기 오류: {e}")
            break
        blocks.extend(resp.get("results", []))
        if not resp.get("has_more"): break
        cursor = resp.get("next_cursor")
    return blocks

def block_text(block):
    """단일 블록에서 텍스트 추출"""
    btype = block.get("type", "")
    content = block.get(btype, {})
    rich = content.get("rich_text", [])
    return _text(rich)

def blocks_to_text(blocks):
    """블록 리스트 → 줄바꿈 연결 텍스트"""
    lines = []
    for b in blocks:
        t = block_text(b)
        if t: lines.append(t)
    return "\n".join(lines)

# ─────────────────────────────────────────────
# RFP 하위 페이지 파싱
# ─────────────────────────────────────────────
def parse_rfp_page(notion, page_id, page_title, page_date):
    """
    RFP 노션 하위 페이지 파싱.
    섹션 헤딩 기준으로 분리:
      1/추진 배경 → background
      2/최종 목표 → goal
      3/주요 기술 → core_techs (기술 1, 기술 2 … 각각)
      4/세부 목표 → kpis (표 → 행별 파싱)
      5/추진 내용 → phases (1단계, 2단계 …)
      기대 효과   → effect
    """
    blocks = get_all_blocks(notion, page_id)

    # 섹션별 블록 분류
    sections = {
        "background": [], "goal": [], "core_techs_raw": [],
        "kpis_raw": [], "phases_raw": [], "effect": []
    }
    current = None
    SECTION_MAP = {
        "추진 배경": "background", "배경": "background",
        "최종 목표": "goal", "목표": "goal",
        "주요 기술": "core_techs_raw",
        "세부 목표": "kpis_raw",
        "추진 내용": "phases_raw",
        "기대 효과": "effect",
    }

    for block in blocks:
        btype = block.get("type", "")
        txt   = block_text(block).strip()

        # 헤딩 감지
        if btype in ("heading_1", "heading_2", "heading_3"):
            # 숫자 접두사 제거 후 매핑
            clean = re.sub(r"^\d+[\.\s]+", "", txt).strip()
            matched = next((v for k, v in SECTION_MAP.items() if k in clean), None)
            current = matched
            continue

        if current and txt:
            sections[current].append(block)

    # ── background / goal / effect: 텍스트 그대로
    background = blocks_to_text(sections["background"])
    goal       = blocks_to_text(sections["goal"])
    effect     = blocks_to_text(sections["effect"])

    # ── core_techs: [기술 N] 헤딩으로 분리
    core_techs = []
    cur_tech_name, cur_tech_lines = None, []
    for block in sections["core_techs_raw"]:
        btype = block.get("type", "")
        txt   = block_text(block).strip()
        # [기술 N] 패턴 감지 (heading 또는 bold paragraph)
        tech_match = re.match(r"\[기술\s*\d+\]\s*(.*)", txt)
        if tech_match or (btype in ("heading_2","heading_3") and "기술" in txt):
            if cur_tech_name:
                core_techs.append({"name": cur_tech_name, "desc": "\n".join(cur_tech_lines).strip()})
            cur_tech_name = tech_match.group(1).strip() if tech_match else txt
            cur_tech_lines = []
        elif cur_tech_name and txt:
            cur_tech_lines.append(txt)
    if cur_tech_name:
        core_techs.append({"name": cur_tech_name, "desc": "\n".join(cur_tech_lines).strip()})

    # ── kpis: 표(table) 블록 파싱 → 행별 {"label","value","reason"}
    kpis = []
    for block in sections["kpis_raw"]:
        if block.get("type") == "table":
            try:
                rows_resp = notion.blocks.children.list(block_id=block["id"])
                table_rows = rows_resp.get("results", [])
                # 첫 행은 헤더 스킵
                for row_block in table_rows[1:]:
                    cells = row_block.get("table_row", {}).get("cells", [])
                    if len(cells) >= 2:
                        label  = _text(cells[0]) if cells[0] else ""
                        value  = _text(cells[1]) if len(cells) > 1 else ""
                        reason = _text(cells[2]) if len(cells) > 2 else ""
                        if label:
                            kpis.append({"label": label, "value": value, "reason": reason})
            except Exception as e:
                log.warning(f"표 파싱 오류: {e}")
        else:
            # 표가 아닌 일반 텍스트도 kpi로 저장
            txt = block_text(block).strip()
            if txt:
                # "지표명: 목표값" 형식 파싱 시도
                m = re.match(r"(.+?)[:：]\s*(.+)", txt)
                if m:
                    kpis.append({"label": m.group(1).strip(), "value": m.group(2).strip(), "reason": ""})

    # ── phases: 1단계, 2단계 … 기준으로 분리
    phases = []
    cur_phase_label, cur_phase_lines = None, []
    for block in sections["phases_raw"]:
        txt   = block_text(block).strip()
        btype = block.get("type", "")
        # "N단계" 또는 "1단계 (…)" 패턴
        phase_match = re.match(r"(\d+단계[^:：]*)", txt)
        if phase_match and btype in ("heading_2","heading_3","paragraph","bulleted_list_item"):
            if cur_phase_label:
                phases.append({"label": cur_phase_label, "content": "\n".join(cur_phase_lines).strip()})
            cur_phase_label = txt
            cur_phase_lines = []
        elif cur_phase_label and txt:
            cur_phase_lines.append(("• " if btype == "bulleted_list_item" else "") + txt)
    if cur_phase_label:
        phases.append({"label": cur_phase_label, "content": "\n".join(cur_phase_lines).strip()})

    # 날짜에서 ID 생성
    date_compact = (page_date or TODAY_KST).replace("-","")[2:]
    page_short   = page_id.replace("-","")[:4].upper()

    return {
        "id":         f"RFP-{date_compact}{page_short}",
        "date":       page_date or TODAY_KST,
        "domain":     "",          # DB 수준 속성이 없으면 빈값
        "title":      page_title,
        "budget":     "",
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
# 1. trend_data.json
# ─────────────────────────────────────────────
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
    pages    = all_pages(notion, DB_IDEA)
    if not pages: log.info("[idea] 데이터 없음 → 스킵"); return False

    exist_ids = {i.get("id") for i in existing}
    new_items = []
    for page in pages:
        props  = page.get("properties", {})
        pid    = page.get("id","").replace("-","")[:4]
        date   = get_date(props, "날짜", "Date") or TODAY_KST
        iid    = f"IDEA-{date.replace('-','')[2:]}{pid.upper()}"
        if iid in exist_ids: continue

        new_items.append({
            "id":           iid,
            "date":         date,
            "domain":       get_select(props, "도메인", "Domain"),
            # ▼ 이미지 기준: 기술명
            "tech_name":    get_title(props, "기술명", "Name", "Tech"),
            # ▼ 이미지 기준: 해결 이슈 (없으면 Target Issue)
            "target_issue": get_rt(props, "해결 이슈", "Target Issue"),
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
def sync_rfp(notion):
    """
    RFP DB = 상위 페이지 목록 (제안 이력).
    각 행의 실제 내용은 하위 페이지에 작성되어 있음.
    → 각 페이지를 열어 블록 파싱.
    """
    path     = DATA_DIR / "rfp_cards.json"
    existing = load_json(path) or []
    pages    = all_pages(notion, DB_RFP)
    if not pages: log.info("[rfp] 데이터 없음 → 스킵"); return False

    exist_ids = {r.get("id") for r in existing}
    new_items = []

    for page in pages:
        props      = page.get("properties", {})
        page_id    = page.get("id", "")
        page_title = get_title(props, "과제명", "Name", "Title") or "제목 없음"
        page_date  = get_date(props, "날짜", "제안 일자", "Date") or TODAY_KST
        pid_short  = page_id.replace("-","")[:4].upper()
        rfp_id     = f"RFP-{page_date.replace('-','')[2:]}{pid_short}"

        if rfp_id in exist_ids:
            continue

        log.info(f"[rfp] 하위 페이지 파싱: {page_title}")
        try:
            entry = parse_rfp_page(notion, page_id, page_title, page_date)
            # DB 수준 속성으로 덮어쓰기 (있는 경우)
            entry["id"]     = rfp_id
            entry["domain"] = get_select(props, "도메인", "Domain") or entry["domain"]
            entry["budget"] = get_select(props, "예산규모", "Budget") or entry["budget"]
            entry["tags"]   = get_multi(props, "태그", "Tags") or entry["tags"]
            new_items.append(entry)
        except Exception as e:
            log.error(f"[rfp] 페이지 파싱 오류 ({page_title}): {e}")

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
