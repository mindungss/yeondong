"""
sync_notion.py
Notion DB → JSON 동기화 스크립트
치안 과학기술 동향 플랫폼 | KIPOT

실행:
  NOTION_TOKEN=secret_xxx \
  NOTION_DB_TREND=34b498ee... \
  NOTION_DB_IDEA=e23ed0df... \
  NOTION_DB_RFP=379498ee... \
  NOTION_DB_NTIS=5f3b759c... \
  python sync_notion.py
"""

import os
import json
import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from notion_client import Client
from notion_client.errors import APIResponseError

# ─────────────────────────────────────────────
# 로깅 설정
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 환경변수
# ─────────────────────────────────────────────
NOTION_TOKEN   = os.environ.get("NOTION_TOKEN", "")
DB_TREND       = os.environ.get("NOTION_DB_TREND", "")
DB_IDEA        = os.environ.get("NOTION_DB_IDEA", "")
DB_RFP         = os.environ.get("NOTION_DB_RFP", "")
DB_NTIS        = os.environ.get("NOTION_DB_NTIS", "")

DATA_DIR       = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

KST            = timezone(timedelta(hours=9))
TODAY_KST      = datetime.now(KST).strftime("%Y-%m-%d")

# ─────────────────────────────────────────────
# 유틸: Notion 속성 추출 헬퍼
# ─────────────────────────────────────────────
def get_title(props: dict, key: str) -> str:
    """Title 속성 → 문자열"""
    arr = props.get(key, {}).get("title", [])
    return "".join(b.get("plain_text", "") for b in arr).strip()

def get_rich_text(props: dict, key: str) -> str:
    """Rich text 속성 → 문자열"""
    arr = props.get(key, {}).get("rich_text", [])
    return "".join(b.get("plain_text", "") for b in arr).strip()

def get_select(props: dict, key: str) -> str:
    """Select 속성 → 문자열"""
    sel = props.get(key, {}).get("select")
    return sel.get("name", "") if sel else ""

def get_multi_select(props: dict, key: str) -> list:
    """Multi-select 속성 → 리스트"""
    items = props.get(key, {}).get("multi_select", [])
    return [i.get("name", "") for i in items]

def get_number(props: dict, key: str, default=0):
    """Number 속성 → 숫자"""
    val = props.get(key, {}).get("number")
    return val if val is not None else default

def get_date(props: dict, key: str) -> str:
    """Date 속성 → YYYY-MM-DD 문자열"""
    d = props.get(key, {}).get("date")
    if d and d.get("start"):
        return d["start"][:10]
    return ""

def get_checkbox(props: dict, key: str) -> bool:
    """Checkbox 속성 → bool"""
    return props.get(key, {}).get("checkbox", False)

def get_url(props: dict, key: str) -> str:
    """URL 속성 → 문자열"""
    return props.get(key, {}).get("url") or ""

def get_all_pages(notion: Client, db_id: str, filter_body: dict = None) -> list:
    """페이지네이션을 처리하여 전체 결과 반환"""
    results = []
    cursor = None
    while True:
        params = {"database_id": db_id, "page_size": 100}
        if filter_body:
            params["filter"] = filter_body
        if cursor:
            params["start_cursor"] = cursor
        try:
            resp = notion.databases.query(**params)
        except APIResponseError as e:
            log.error(f"Notion API 오류 (DB: {db_id}): {e}")
            return results
        results.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return results

def load_existing(path: Path) -> object:
    """기존 JSON 파일 로드 (없으면 기본값)"""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_json(path: Path, data: object):
    """JSON 저장"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"저장 완료: {path}")


# ─────────────────────────────────────────────
# 1. trend_data.json 동기화
# ─────────────────────────────────────────────
def sync_trend(notion: Client) -> bool:
    """
    노션 DB에서 오늘 날짜 이슈/기술 데이터를 읽어 trend_data.json에 누적.
    새 데이터가 없으면 False 반환(스킵).
    """
    path = DATA_DIR / "trend_data.json"
    existing = load_existing(path) or {}

    pages = get_all_pages(notion, DB_TREND)
    if not pages:
        log.info("[trend] 노션에서 가져온 데이터 없음 → 스킵")
        return False

    # 날짜별로 분류
    new_data: dict = {}
    for page in pages:
        props = page.get("properties", {})
        record_date = get_date(props, "날짜") or get_date(props, "Date") or TODAY_KST
        rec_type    = get_select(props, "유형") or get_select(props, "Type") or "이슈"

        if record_date not in new_data:
            new_data[record_date] = {"issues": [], "technologies": []}

        record_id  = page.get("id", "").replace("-", "")[:12].upper()
        tags       = get_multi_select(props, "태그") or get_multi_select(props, "Tags")
        domain     = get_select(props, "도메인") or get_select(props, "Domain") or ""
        severity   = get_select(props, "심각도") or get_select(props, "Severity") or "medium"
        title      = (get_title(props, "제목") or get_title(props, "Name") or
                      get_title(props, "Title") or "제목 없음")
        summary    = get_rich_text(props, "요약") or get_rich_text(props, "Summary")
        detail     = get_rich_text(props, "상세") or get_rich_text(props, "Detail")
        source     = get_rich_text(props, "출처") or get_rich_text(props, "Source")
        url        = get_url(props, "URL") or get_url(props, "링크") or get_url(props, "Link")
        trl        = int(get_number(props, "TRL", 1))

        if rec_type in ("기술", "Technology", "Tech"):
            prefix = "T"
            entry = {
                "id":      f"T{record_date.replace('-','')[2:]}{record_id[:4]}",
                "title":   title,
                "domain":  domain,
                "trl":     trl,
                "summary": summary,
                "detail":  detail,
                "url":     url,
                "tags":    tags,
            }
            new_data[record_date]["technologies"].append(entry)
        else:
            entry = {
                "id":       f"I{record_date.replace('-','')[2:]}{record_id[:4]}",
                "title":    title,
                "domain":   domain,
                "severity": severity.lower() if severity else "medium",
                "summary":  summary,
                "detail":   detail,
                "source":   source,
                "url":      url,
                "tags":     tags,
            }
            new_data[record_date]["issues"].append(entry)

    if not new_data:
        log.info("[trend] 처리된 데이터 없음 → 스킵")
        return False

    # 기존 데이터에 병합 (새 날짜 추가, 기존 날짜 덮어쓰기)
    merged = dict(existing)
    merged.update(new_data)
    # 날짜 내림차순 정렬
    sorted_merged = dict(sorted(merged.items(), reverse=True))

    save_json(path, sorted_merged)
    log.info(f"[trend] {len(new_data)}개 날짜 업데이트, 총 {len(sorted_merged)}일치 데이터")
    return True


# ─────────────────────────────────────────────
# 2. idea_cards.json 동기화
# ─────────────────────────────────────────────
def sync_ideas(notion: Client) -> bool:
    path = DATA_DIR / "idea_cards.json"
    existing = load_existing(path) or []

    pages = get_all_pages(notion, DB_IDEA)
    if not pages:
        log.info("[idea] 노션에서 가져온 데이터 없음 → 스킵")
        return False

    existing_ids = {item.get("id") for item in existing}
    new_items = []

    for page in pages:
        props   = page.get("properties", {})
        page_id = page.get("id", "").replace("-", "")[:12]
        date    = get_date(props, "날짜") or get_date(props, "Date") or TODAY_KST
        item_id = f"IDEA-{date.replace('-','')[2:]}{page_id[:4].upper()}"

        if item_id in existing_ids:
            continue  # 이미 있는 항목 스킵

        entry = {
            "id":           item_id,
            "date":         date,
            "domain":       get_select(props, "도메인") or get_select(props, "Domain") or "",
            "tech_name":    (get_title(props, "기술명") or get_title(props, "Name") or
                             get_title(props, "Tech") or ""),
            "target_issue": get_rich_text(props, "해결 이슈") or get_rich_text(props, "Target Issue"),
            "tags":         get_multi_select(props, "태그") or get_multi_select(props, "Tags"),
            "features":     get_rich_text(props, "기술 특징") or get_rich_text(props, "Features"),
            "applications": get_rich_text(props, "적용 분야") or get_rich_text(props, "Applications"),
            "constraints":  get_rich_text(props, "제한 사항") or get_rich_text(props, "Constraints"),
            "companies":    get_rich_text(props, "주요 기업") or get_rich_text(props, "Companies"),
            "trend":        get_rich_text(props, "기술 동향") or get_rich_text(props, "Trend"),
        }
        new_items.append(entry)

    if not new_items:
        log.info("[idea] 신규 항목 없음 → 스킵")
        return False

    merged = new_items + existing  # 새 항목을 앞에 배치
    save_json(path, merged)
    log.info(f"[idea] {len(new_items)}개 신규 항목 추가, 총 {len(merged)}건")
    return True


# ─────────────────────────────────────────────
# 3. rfp_cards.json 동기화
# ─────────────────────────────────────────────
def _parse_json_field(text: str, default) -> object:
    """Rich text에 JSON 문자열이 들어있는 경우 파싱 시도"""
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return text  # 파싱 실패 시 원본 문자열 반환

def sync_rfp(notion: Client) -> bool:
    path = DATA_DIR / "rfp_cards.json"
    existing = load_existing(path) or []

    pages = get_all_pages(notion, DB_RFP)
    if not pages:
        log.info("[rfp] 노션에서 가져온 데이터 없음 → 스킵")
        return False

    existing_ids = {item.get("id") for item in existing}
    new_items = []

    for page in pages:
        props   = page.get("properties", {})
        page_id = page.get("id", "").replace("-", "")[:12]
        date    = get_date(props, "날짜") or get_date(props, "Date") or TODAY_KST
        item_id = f"RFP-{date.replace('-','')[2:]}{page_id[:4].upper()}"

        if item_id in existing_ids:
            continue

        # core_techs, kpis, phases는 JSON 문자열 또는 Rich text로 저장 가능
        core_techs_raw = get_rich_text(props, "핵심기술") or get_rich_text(props, "Core Techs")
        kpis_raw       = get_rich_text(props, "세부목표") or get_rich_text(props, "KPIs")
        phases_raw     = get_rich_text(props, "추진내용") or get_rich_text(props, "Phases")

        entry = {
            "id":         item_id,
            "date":       date,
            "domain":     get_select(props, "도메인") or get_select(props, "Domain") or "",
            "title":      (get_title(props, "과제명") or get_title(props, "Name") or
                           get_title(props, "Title") or ""),
            "budget":     get_select(props, "예산규모") or get_select(props, "Budget") or "",
            "tags":       get_multi_select(props, "태그") or get_multi_select(props, "Tags"),
            "background": get_rich_text(props, "추진배경") or get_rich_text(props, "Background"),
            "goal":       get_rich_text(props, "최종목표") or get_rich_text(props, "Goal"),
            "core_techs": _parse_json_field(core_techs_raw, []),
            "kpis":       _parse_json_field(kpis_raw, []),
            "phases":     _parse_json_field(phases_raw, []),
            "effect":     get_rich_text(props, "기대효과") or get_rich_text(props, "Effect"),
            "diagram":    get_rich_text(props, "다이어그램") or get_rich_text(props, "Diagram"),
        }
        new_items.append(entry)

    if not new_items:
        log.info("[rfp] 신규 항목 없음 → 스킵")
        return False

    merged = new_items + existing
    save_json(path, merged)
    log.info(f"[rfp] {len(new_items)}개 신규 항목 추가, 총 {len(merged)}건")
    return True


# ─────────────────────────────────────────────
# 4. ntis_projects.json 동기화
# ─────────────────────────────────────────────
def sync_ntis(notion: Client) -> bool:
    path = DATA_DIR / "ntis_projects.json"
    existing = load_existing(path) or []

    pages = get_all_pages(notion, DB_NTIS)
    if not pages:
        log.info("[ntis] 노션에서 가져온 데이터 없음 → 스킵")
        return False

    existing_ids = {item.get("id") for item in existing}
    new_items = []
    updated_items = []

    for page in pages:
        props      = page.get("properties", {})
        page_id    = page.get("id", "").replace("-", "")[:8].upper()
        year_raw   = get_select(props, "연도") or get_rich_text(props, "연도") or get_rich_text(props, "Year")
        year       = str(year_raw)[:4] if year_raw else TODAY_KST[:4]
        item_id    = f"NTIS-{year}-{page_id}"
        registered = get_date(props, "등록일") or get_date(props, "Registered") or ""
        is_new     = registered == TODAY_KST or get_checkbox(props, "신규") or get_checkbox(props, "Is New")

        entry = {
            "id":         item_id,
            "title":      (get_title(props, "과제명") or get_title(props, "Name") or
                           get_title(props, "Title") or ""),
            "org":        get_rich_text(props, "주관기관") or get_rich_text(props, "Org"),
            "year":       year,
            "budget":     get_rich_text(props, "총연구비") or get_rich_text(props, "Budget"),
            "domain":     get_select(props, "도메인") or get_select(props, "Domain") or "",
            "keywords":   get_rich_text(props, "키워드") or get_rich_text(props, "Keywords"),
            "summary":    get_rich_text(props, "개요") or get_rich_text(props, "Summary"),
            "registered": registered,
            "is_new":     bool(is_new),
            "url":        get_url(props, "URL") or get_url(props, "링크") or "",
            "total_orgs": get_rich_text(props, "총연구기관") or get_rich_text(props, "Total Orgs"),
            "goal":       get_rich_text(props, "연구목표") or get_rich_text(props, "Goal"),
            "content":    get_rich_text(props, "연구내용") or get_rich_text(props, "Content"),
        }

        if item_id not in existing_ids:
            new_items.append(entry)
        else:
            # 기존 항목 is_new 플래그 업데이트
            updated_items.append(entry)

    if not new_items and not updated_items:
        log.info("[ntis] 신규/변경 항목 없음 → 스킵")
        return False

    # 기존 목록에서 업데이트된 항목 교체
    updated_ids = {e["id"] for e in updated_items}
    kept = [e for e in existing if e.get("id") not in updated_ids]
    merged = new_items + updated_items + kept

    save_json(path, merged)
    log.info(f"[ntis] 신규 {len(new_items)}건, 업데이트 {len(updated_items)}건, 총 {len(merged)}건")
    return True


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
def main():
    # 환경변수 검증
    missing = [k for k, v in {
        "NOTION_TOKEN": NOTION_TOKEN,
        "NOTION_DB_TREND": DB_TREND,
        "NOTION_DB_IDEA": DB_IDEA,
        "NOTION_DB_RFP": DB_RFP,
        "NOTION_DB_NTIS": DB_NTIS,
    }.items() if not v]

    if missing:
        log.error(f"필수 환경변수 누락: {', '.join(missing)}")
        sys.exit(1)

    notion = Client(auth=NOTION_TOKEN)
    log.info(f"동기화 시작 | 기준일: {TODAY_KST} (KST)")

    results = {}
    errors  = []

    # 각 DB 동기화 (에러가 있어도 나머지는 계속 진행)
    for name, func, db_id in [
        ("trend",  sync_trend,  DB_TREND),
        ("idea",   sync_ideas,  DB_IDEA),
        ("rfp",    sync_rfp,    DB_RFP),
        ("ntis",   sync_ntis,   DB_NTIS),
    ]:
        if not db_id:
            log.warning(f"[{name}] DB ID 미설정 → 스킵")
            results[name] = False
            continue
        try:
            results[name] = func(notion)
        except Exception as e:
            log.error(f"[{name}] 예외 발생: {e}")
            errors.append(name)
            results[name] = False

    # 결과 요약
    updated = [k for k, v in results.items() if v]
    skipped = [k for k, v in results.items() if not v]

    log.info("=" * 50)
    log.info(f"동기화 완료 | 업데이트: {updated} | 스킵: {skipped} | 오류: {errors}")
    log.info("=" * 50)

    # GitHub Actions에서 변경 여부를 환경변수로 전달
    changed = len(updated) > 0
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")
        log.info(f"GITHUB_OUTPUT에 changed={changed} 기록")

    # 에러가 있어도 exit 0 (GitHub Actions에서 실패로 처리되지 않도록)
    sys.exit(0)


if __name__ == "__main__":
    main()
