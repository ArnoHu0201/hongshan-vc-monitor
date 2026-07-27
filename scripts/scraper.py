"""
红杉中国投资监控 - 数据抓取与解析模块
负责从投资界(pedaily.cn)抓取原始投资事件数据
"""

import re
import time
import random
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from config import HONGSHAN_VC_URL, HEADERS, UA_POOL

logger = logging.getLogger(__name__)


def get_session():
    """创建带 UA 旋转的 HTTP Session"""
    session = requests.Session()
    session.headers.update(HEADERS)
    session.headers["User-Agent"] = random.choice(UA_POOL)
    return session


def fetch_page(session, url, retry=3, sleep_range=(0.5, 1.5), retry_sleep=(2, 4)):
    """抓取页面，sleep_range/retry_sleep 可自定义"""
    for attempt in range(retry):
        try:
            time.sleep(random.uniform(*sleep_range))
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            logger.info(f"成功抓取: {url} (状态码 {resp.status_code})")
            return resp.text
        except requests.RequestException as e:
            logger.warning(f"抓取失败 (第{attempt+1}次): {url} - {e}")
            if attempt < retry - 1:
                time.sleep(random.uniform(*retry_sleep))
    logger.error(f"抓取彻底失败: {url}")
    return None


def get_data_url():
    """根据当前年份生成移动端年度汇总页 URL"""
    year = datetime.now().year
    return f"https://m.pedaily.cn/data/gp/{year}/3067"


# ============================================================
# 数据源1: 机构页面 vc.pedaily.cn/vc/106728.html
# ============================================================
def parse_vc_page(html):
    """
    解析红杉中国机构页面，提取投资事件列表。
    DOM: <div class="item"> 内含 .t(轮次+金额) .d(日期) .name(公司+行业) .s(投资方) .ai-summary
    """
    soup = BeautifulSoup(html, "lxml")
    events = []

    for item_div in soup.find_all("div", class_="item"):
        top_div = item_div.find("div", class_="t")
        if not top_div:
            continue
        spans = top_div.find_all("span")
        round_type = spans[0].get_text(strip=True) if len(spans) >= 1 else ""
        amount = spans[1].get_text(strip=True) if len(spans) >= 2 else ""

        if any(ex in round_type for ex in ["证券交易所", "上市", "IPO"]):
            continue

        date_div = item_div.find("div", class_="d")
        event_date = date_div.get_text(strip=True) if date_div else ""

        name_div = item_div.find("div", class_="name")
        if not name_div:
            continue
        company_link = name_div.find("a", href=re.compile(r"/company/\d+\.html"))
        company_name = company_link.get_text(strip=True) if company_link else ""
        company_id = ""
        company_url = ""
        if company_link:
            href = company_link.get("href", "")
            cid_match = re.search(r"/company/(\d+)\.html", href)
            if cid_match:
                company_id = cid_match.group(1)
                company_url = f"https://vc.pedaily.cn/company/{company_id}.html"

        ind_link = name_div.find("a", href=re.compile(r"/invest/"))
        industry = ind_link.get_text(strip=True) if ind_link else ""
        if industry == "-":
            industry = ""

        investors = []
        vcs_div = item_div.find("div", class_="s")
        if vcs_div:
            for tag in vcs_div.find_all(["a", "span"]):
                inv_name = tag.get_text(strip=True)
                if inv_name and inv_name not in investors:
                    investors.append(inv_name)

        hongshan_role = ""
        ai_summary = item_div.find("div", class_="ai-summary")
        summary_text = ai_summary.get_text(strip=True) if ai_summary else ""
        full_block_text = item_div.get_text(strip=True)

        if "领投" in summary_text or "领投" in full_block_text:
            if "红杉" in full_block_text:
                hongshan_role = "领投"
        elif "跟投" in summary_text or "跟投" in full_block_text:
            if "红杉" in full_block_text:
                hongshan_role = "跟投"
        elif any("红杉" in inv or "HongShan" in inv for inv in investors):
            hongshan_role = "参与"

        description = summary_text[:150] if summary_text else ""

        events.append({
            "company_name": company_name,
            "company_id": company_id,
            "company_url": company_url,
            "round_type": round_type,
            "amount": amount,
            "event_date": event_date,
            "industry": industry,
            "investors": investors,
            "hongshan_role": hongshan_role,
            "description": description,
        })

    return events


# ============================================================
# 数据源2: 移动端年度汇总页
# ============================================================
def parse_data_summary_page(html):
    """
    解析移动端年度汇总页面。
    DOM: <li> 内含 <div class="txt">(描述) <span class="date">(日期)
    <a href="/news/xxx" class="more">详情</a> (具体新闻页链接)
    """
    soup = BeautifulSoup(html, "lxml")
    events = []

    for li_tag in soup.find_all("li"):
        date_span = li_tag.find("span", class_="date")
        event_date = date_span.get_text(strip=True) if date_span else ""
        if not event_date:
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", li_tag.get_text())
            event_date = date_match.group(1) if date_match else ""

        txt_div = li_tag.find("div", class_="txt")
        if not txt_div:
            continue
        desc_text = txt_div.get_text(strip=True)

        # 提取具体新闻页URL - 在 div.desc 内找 a.more 链接
        news_url = ""
        desc_div = li_tag.find("div", class_="desc")
        if desc_div:
            more_link = desc_div.find("a", class_="more")
            if more_link and more_link.get("href"):
                href = more_link["href"]
                if href.startswith("https://m.pedaily.cn/news/"):
                    news_url = href
                elif href.startswith("/news/"):
                    news_url = f"https://m.pedaily.cn{href}"

        # 仅保留包含红杉的事件
        if "红杉" not in desc_text and "HongShan" not in desc_text:
            continue

        round_match = re.search(
            r"(种子轮|天使轮|天使\+轮|Pre-A轮|Pre-A\+轮|A轮|A\+轮|A\+\+轮|B轮|B\+轮|B\+\+轮|C轮|C\+轮|D轮|D\+轮|战略融资|出资设立轮)",
            desc_text
        )
        round_type = round_match.group(1) if round_match else ""

        amount_patterns = [
            r"(超[\s]?[\d.]+\s?(?:亿|千万|百万)(?:人民币|美元|美金|元))",
            r"(近[\d.]+\s?(?:亿|千万|百万)(?:人民币|美元|美金|元))",
            r"([\d.]+亿(?:人民币|美元|美金|元))",
            r"(数(?:千万|亿|百万|十万)(?:人民币|美元|美金|元))",
            r"(数千万元(?:人民币|美元|美金))",
            r"(数亿元(?:人民币|美元|美金))",
            r"(亿元级(?:人民币|美元|美金))",
            r"(亿级(?:人民币|美元|美金))",
            r"(超亿元(?:人民币|美元|美金))",
            r"(近亿元(?:人民币|美元|美金))",
            r"([\d.]+千万(?:人民币|美元|美金|元))",
        ]
        amount = ""
        for pattern in amount_patterns:
            amount_match = re.search(pattern, desc_text)
            if amount_match:
                amount = amount_match.group(1)
                break

        company_name = ""
        company_match1 = re.search(r'[\u300c\u300e\u201c]([^\u300d\u300f\u201d]{2,20})[\u300d\u300f\u201d]', desc_text)
        if company_match1:
            company_name = company_match1.group(1).strip()
        else:
            company_match2 = re.search(r'[下简]称[：:\u300c\u300e\u201c]([^\u300d\u300f\u201d\s]{2,20})', desc_text)
            if company_match2:
                company_name = company_match2.group(1).strip()
            else:
                company_match3 = re.search(r"([^，,\n\s]{2,15})(?:完成|获|宣布)", desc_text)
                if company_match3:
                    candidate = company_match3.group(1).strip()
                    candidate = re.sub(r"^(近日[，,]?|近日|正式|刚|已)", "", candidate).strip()
                    candidate = re.sub(r"(近日|正式|刚|已)$", "", candidate).strip()
                    if len(candidate) >= 2 and candidate not in ["消息", "投资界"]:
                        company_name = candidate

        industry = ""
        industry_keywords = [
            "AI", "人工智能", "具身智能", "机器人", "芯片", "半导体",
            "医疗", "医药", "生物", "金融", "消费", "教育", "新能源",
            "航天", "航空", "核聚变", "脑机接口", "智能装备", "物联网",
            "大模型", "自动驾驶", "3D", "SaaS", "云计算", "网络安全",
        ]
        for kw in industry_keywords:
            if kw in desc_text:
                industry = kw
                break

        investors = []
        investor_patterns = [
            r"由([^，,。\.]+(?:领投|跟投))",
            r"投资方(?:包括|为)[：:]([^。\.]+)",
            r"((?:红杉中国|高瓴|顺为|真格|启明|IDG|经纬|源码|峰瑞|蓝驰|金沙江|中金|腾讯|字节|美团)[^，,]*?(?:资本|创投|基金|投资|战投|集团)?)",
        ]
        for pattern in investor_patterns:
            inv_match = re.search(pattern, desc_text)
            if inv_match:
                inv_text = inv_match.group(1)
                for inv in re.split(r"[、,，]", inv_text):
                    inv = inv.strip()
                    if inv and len(inv) > 2 and inv not in investors:
                        investors.append(inv)

        if not investors and ("红杉中国" in desc_text or "HongShan" in desc_text):
            investors.append("红杉中国")

        hongshan_role = ""
        if "领投" in desc_text and "红杉" in desc_text:
            if re.search(r"红杉[^，,]{0,10}领投|由[^，,]*红杉[^，,]*领投", desc_text):
                hongshan_role = "领投"
            else:
                hongshan_role = "参与"
        elif "跟投" in desc_text and "红杉" in desc_text:
            if re.search(r"红杉[^，,]{0,10}跟投", desc_text):
                hongshan_role = "跟投"
            else:
                hongshan_role = "参与"
        elif "红杉" in desc_text or "HongShan" in desc_text:
            hongshan_role = "参与"

        description = desc_text[:150] if desc_text else ""

        events.append({
            "company_name": company_name,
            "company_id": "",
            "company_url": news_url or "",
            "news_url": news_url,  # 具体新闻页URL，用于交叉验证
            "round_type": round_type,
            "amount": amount or "未披露",
            "event_date": event_date,
            "industry": industry,
            "investors": investors,
            "hongshan_role": hongshan_role,
            "description": description,
        })

    return events


def scrape_all(session):
    """从多个数据源抓取全部原始事件，并附加来源信息"""
    all_events = []

    # 数据源1: 机构页面（结构化，含公司ID）
    logger.info("抓取机构页面 vc.pedaily.cn")
    vc_html = fetch_page(session, HONGSHAN_VC_URL)
    if vc_html:
        vc_events = parse_vc_page(vc_html)
        for e in vc_events:
            # 机构页来源：链接到机构页本身（直接显示该轮次+红杉角色）
            # 公司详情页将在交叉验证中补充
            e["sources"] = [{"name": "投资界(机构页)", "url": HONGSHAN_VC_URL}]
        logger.info(f"机构页提取 {len(vc_events)} 条事件")
        all_events.extend(vc_events)

    # 数据源2: 移动端年度汇总（文本型，补充缺公司ID的事件）
    logger.info("抓取移动端年度汇总页")
    data_url = get_data_url()
    data_html = fetch_page(session, data_url)
    if data_html:
        data_events = parse_data_summary_page(data_html)
        for e in data_events:
            # 优先使用具体新闻页URL，其次汇总页
            src_url = e.get("news_url") or e.get("company_url") or data_url
            e["sources"] = [{"name": "投资界(新闻)", "url": src_url}]
        logger.info(f"年度汇总提取 {len(data_events)} 条事件")
        all_events.extend(data_events)

    return all_events


# ============================================================
# 交叉验证模块 - 抓取具体新闻页验证轮次，寻找多平台来源
# ============================================================

def search_pedaily_news(session, company_name, round_type=""):
    """
    在 pedaily.cn 新闻中搜索该公司的具体融资新闻。
    返回匹配该轮次的新闻URL列表。
    """
    query = f"{company_name} {round_type}"
    encoded = requests.utils.quote(query)
    search_url = f"https://m.pedaily.cn/search?keyword={encoded}"

    html = fetch_page(session, search_url, sleep_range=(1.0, 1.5), retry=2)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    articles = []

    # pedaily 搜索结果是 li 列表
    for li in soup.find_all("li"):
        link = li.find("a", href=True)
        if not link:
            continue
        href = link.get("href", "")
        title = link.get_text(strip=True)

        # 只找新闻页链接
        news_id = ""
        if "/news/" in href:
            news_match = re.search(r"/news/?(\d+)", href)
            if news_match:
                news_id = news_match.group(1)
        else:
            continue

        full_url = f"https://m.pedaily.cn/news/{news_id}" if news_id else ""
        if not full_url:
            continue

        # 检查标题或摘要中是否包含公司名和轮次
        li_text = li.get_text(strip=True)
        if company_name[:4] not in li_text:
            # 公司名不匹配，跳过
            continue

        articles.append({"name": "投资界(新闻)", "url": full_url, "text": li_text[:200]})

    logger.info(f"搜索 {company_name} ({round_type}): 找到 {len(articles)} 篇相关新闻")
    return articles[:3]


def fetch_news_detail(session, news_url):
    """
    抓取具体新闻页，验证文中是否提及该轮次和红杉。
    返回 dict: {verified_round, investors_mentioned, full_text_summary}
    """
    if not news_url:
        return None
    html = fetch_page(session, news_url, sleep_range=(0.3, 0.8))
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    # 提取文章正文
    article = soup.find("article") or soup.find("div", class_="article-content") or soup.find("div", class_="content")
    if article:
        full_text = article.get_text(separator="\n", strip=True)
    else:
        full_text = soup.get_text(separator="\n", strip=True)

    # 检测正文中提及的轮次
    rounds_found = re.findall(
        r"(种子轮|天使轮|天使\+轮|Pre-A轮|Pre-A\+轮|A轮|A\+轮|B轮|B\+轮|C轮|C\+轮|D轮|战略融资|出资设立轮)",
        full_text
    )

    # 检测是否提及红杉
    mentions_hongshan = "红杉" in full_text or "HongShan" in full_text

    return {
        "verified_rounds": list(set(rounds_found)),
        "mentions_hongshan": mentions_hongshan,
    }


def cross_validate_events(events, session):
    """
    对所有事件执行交叉验证，确保每个事件都指向精确的新闻页而非泛链接。

    对于每个事件：
    1. 如果已有具体新闻页URL（/news/xxx），抓取核验轮次
    2. 如果只有机构页/公司详情页的泛链接，搜索 pedaily.cn 找具体新闻
    3. 找到匹配轮次且含红杉的新闻页后，替换为主来源
    4. 实在找不到新闻页的，保留 VC 机构页作为来源（该页直接显示轮次+红杉角色）
    """
    fixed_count = 0
    for event in events:
        existing_sources = event.get("sources", [])
        existing_urls = {s.get("url") for s in existing_sources if s.get("url")}

        has_news_url = any("/news/" in s.get("url", "") for s in existing_sources)

        if not has_news_url:
            # 只有泛链接的事件（来自机构页），需要搜索具体新闻
            company = event.get("company_name", "")
            round_type = event.get("round_type", "")
            if not company:
                continue

            # 搜索 pedaily.cn 新闻
            news_articles = search_pedaily_news(session, company, round_type)

            # 核验每篇新闻，找匹配轮次+含红杉的
            best_source = None
            for article in news_articles:
                url = article["url"]
                detail = fetch_news_detail(session, url)
                if detail:
                    verified = detail.get("verified_rounds", [])
                    match = round_type and round_type in verified if verified else False
                    mentions_hs = detail.get("mentions_hongshan", False)

                    logger.info(
                        f"搜索核验 [{company}]: {url.split('/')[-1]} "
                        f"轮次={verified}, 含红杉={mentions_hs}, "
                        f"匹配={match}"
                    )

                    if match and mentions_hs:
                        best_source = article
                        break
                    elif match or mentions_hs:
                        if not best_source:
                            best_source = article

            if best_source:
                existing_sources.insert(0, best_source)
                existing_urls.add(best_source["url"])
                fixed_count += 1
                logger.info(f"✅ [{company}] 已匹配到新闻页: {best_source['url']}")
            else:
                # 找不到新闻页，保留 VC 机构页作为来源
                # 将来源名称改为"投资界(机构页)"以明确标注
                for src in existing_sources:
                    if "vc.pedaily.cn/vc/" in src.get("url", ""):
                        src["name"] = "投资界(机构页)"
                logger.info(f"⚠️ [{company}] 未找到精确新闻页，使用机构页作为来源")
        else:
            # 已有新闻URL的事件，核验轮次
            for src in existing_sources:
                url = src.get("url", "")
                if url and "/news/" in url:
                    detail = fetch_news_detail(session, url)
                    if detail:
                        verified = detail.get("verified_rounds", [])
                        event_round = event.get("round_type", "")
                        match = event_round in verified if verified else False
                        logger.info(
                            f"核验 [{event.get('company_name')}]: "
                            f"轮次={verified}, 含红杉={detail['mentions_hongshan']}, "
                            f"匹配={match}"
                        )
                        if not match and verified:
                            logger.warning(f"⚠️ 轮次不匹配! 事件={event_round}, 新闻页={verified}")
                    break

        # 补充公司详情页作为参考来源
        company_url = event.get("company_url", "")
        if company_url and company_url not in existing_urls:
            existing_sources.append({"name": "投资界(详情)", "url": company_url})

        event["sources"] = existing_sources

    if fixed_count:
        logger.info(f"交叉验证: 为 {fixed_count} 个事件补充了精确新闻页来源")

    return events
