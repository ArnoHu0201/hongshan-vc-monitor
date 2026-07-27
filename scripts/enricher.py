"""
红杉中国投资监控 - 公司详情补充模块
负责并发抓取公司详情页并管理本地缓存
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import COMPANY_CACHE_FILE, COMPANY_DETAIL_BASE
from scraper import fetch_page

import re
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)


def load_company_cache():
    """加载公司详情本地缓存"""
    if COMPANY_CACHE_FILE.exists():
        try:
            return json.loads(COMPANY_CACHE_FILE.read_text(encoding="utf-8"))
        except:
            return {}
    return {}


def save_company_cache(cache):
    """保存公司详情缓存"""
    COMPANY_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_company_detail(session, company_id):
    """抓取公司详情页，提取成立日期、所在地、全称等"""
    url = f"{COMPANY_DETAIL_BASE}{company_id}.html"
    html = fetch_page(session, url, sleep_range=(0.3, 0.8), retry_sleep=(1.5, 3))
    if not html:
        return {}

    soup = BeautifulSoup(html, "lxml")
    full_text = soup.get_text(separator="\n", strip=True)
    detail = {}

    # 成立日期
    founded_patterns = [
        r"成立于\s*(\d{4}-\d{1,2}-\d{1,2})",
        r"成立于\s*(\d{4}年\d{1,2}月\d{1,2}日)",
        r"成立时间[：:]\s*(\d{4}[年\-/]\d{1,2}[月\-/]\d{1,2}日?)",
        r"成立\s*(\d{4}-\d{2}-\d{2})",
    ]
    for pattern in founded_patterns:
        founded_match = re.search(pattern, full_text)
        if founded_match:
            founded_str = founded_match.group(1)
            for fmt in ("%Y年%m月%d日", "%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d"):
                try:
                    detail["founded_date"] = datetime.strptime(founded_str, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            if not detail.get("founded_date"):
                detail["founded_date"] = founded_str
            break

    # 公司全称
    fullname_patterns = [
        r'工商信息显示[，,]\s*[\u300c\u300e\u201c]([^\u300d\u300f\u201d]{5,40})[\u300d\u300f\u201d]',
        r'[\u300c\u300e\u201c]([^\u300d\u300f\u201d]{5,40}(?:有限公司|公司))[\u300d\u300f\u201d]',
        r"([^，,\n\s]{5,40}(?:有限公司|科技公司|公司))",
    ]
    for pattern in fullname_patterns:
        fullname_match = re.search(pattern, full_text)
        if fullname_match:
            detail["full_name"] = fullname_match.group(1).strip()
            break

    # 所在地
    location_patterns = [
        r"所在地\s*([^；;\n，,]{2,20})",
        r"注册地址位于\s*([^，,\n]{2,20})",
    ]
    for pattern in location_patterns:
        loc_match = re.search(pattern, full_text)
        if loc_match:
            loc = loc_match.group(1).strip()
            loc_match2 = re.search(r"(^(?:北京|上海|天津|重庆|[^省]+省|[^市]+市|[^区]+区))", loc)
            detail["location"] = loc_match2.group(1) if loc_match2 else loc[:15]
            break

    # 从全称中提取城市
    if not detail.get("location") and detail.get("full_name"):
        loc_from_name = re.search(r"[（(]([^）)]{2,10})[）)]", detail["full_name"])
        if loc_from_name:
            detail["location"] = loc_from_name.group(1)

    # 公司简介
    intro_patterns = [
        r"简介[：:]\s*([^\n]{10,200})",
        r"([^，,\n]{10,100}(?:研发商|服务商|平台|技术|方案提供商))",
    ]
    for pattern in intro_patterns:
        intro_match = re.search(pattern, full_text)
        if intro_match:
            detail["intro"] = intro_match.group(1).strip()[:100]
            break

    # 行业详情
    industry_match = re.search(r"所属行业为\s*([^，,\n；;]{2,30})", full_text)
    if industry_match:
        detail["industry_detail"] = industry_match.group(1).strip()

    # 投后估值
    valuation_match = re.search(r"投后估值\s*([^，,\n]{3,30})", full_text)
    if valuation_match:
        detail["post_valuation"] = valuation_match.group(1).strip()

    logger.info(f"公司详情: {company_id} → founded={detail.get('founded_date','')}, loc={detail.get('location','')}")
    return detail


def enrich_events(events, session):
    """为有 company_id 的事件补充字段，优先使用缓存，未缓存的并发抓取"""
    from processor import deduplicate_events

    cache = load_company_cache()

    # 去重后识别需要抓取的 company_id
    unique_events = deduplicate_events(events)
    ids_to_fetch = []
    for event in unique_events:
        cid = event.get("company_id", "")
        if cid and cid not in cache:
            ids_to_fetch.append(cid)

    if ids_to_fetch:
        logger.info(f"并发抓取 {len(ids_to_fetch)} 家公司详情（已有缓存 {len(cache)} 家）")
        with ThreadPoolExecutor(max_workers=4) as pool:
            future_map = {pool.submit(fetch_company_detail, session, cid): cid for cid in ids_to_fetch}
            for future in as_completed(future_map):
                cid = future_map[future]
                try:
                    detail = future.result()
                    cache[cid] = detail
                except Exception as e:
                    logger.warning(f"并发抓取公司 {cid} 失败: {e}")
                    cache[cid] = {}
        save_company_cache(cache)

    enriched = []
    for event in events:
        cid = event.get("company_id", "")
        detail = cache.get(cid, {}) if cid else {}

        # 保留并丰富 sources 字段
        sources = event.get("sources", [])
        company_url = event.get("company_url", "")
        if company_url and not any(s.get("url") == company_url for s in sources):
            sources.append({"name": "投资界(详情)", "url": company_url})

        enriched.append({
            "company_name": event["company_name"],
            "full_name": detail.get("full_name", event["company_name"]),
            "intro": detail.get("intro", "") or event.get("description", "")[:100],
            "founded_date": detail.get("founded_date", ""),
            "location": detail.get("location", ""),
            "industry": detail.get("industry_detail", "") or event.get("industry", ""),
            "round_type": event["round_type"],
            "hongshan_role": event.get("hongshan_role", ""),
            "investors": "、".join(event.get("investors", [])),
            "amount": event.get("amount", "未披露"),
            "post_valuation": detail.get("post_valuation", ""),
            "event_date": event.get("event_date", ""),
            "sources": sources,
            "is_new": event.get("is_new", False),
        })

    return enriched
