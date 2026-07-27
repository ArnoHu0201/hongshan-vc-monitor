"""
红杉中国投资监控 - HTML 报告渲染模块（响应式设计）
支持移动端卡片化展示 + 桌面端表格展示，多来源链接支持
"""

import logging
from datetime import datetime

import pandas as pd

from config import TIME_WINDOW_DAYS, INCREMENT_BG_COLOR, INCREMENT_LABEL

logger = logging.getLogger(__name__)

# ============================================================
# 响应式 CSS（适配桌面 + 移动端邮件客户端）
# ============================================================
BASE_STYLE = f"""
/* ---------- 全局 ---------- */
body{{font-family:-apple-system,'Microsoft YaHei','PingFang SC','Helvetica Neue',Arial,sans-serif;margin:0;padding:0;background:#f5f6fa;font-size:14px;line-height:1.6;color:#333;}}
.container{{max-width:680px;margin:0 auto;padding:20px 16px;}}
h2{{color:#c0392b;font-size:20px;margin:0 0 4px 0;padding-bottom:8px;border-bottom:3px solid #c0392b;}}
.subtitle{{color:#888;font-size:13px;margin:4px 0 16px 0;}}
.summary-bar{{background:#fff;border-radius:8px;padding:12px 16px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.08);font-size:13px;color:#555;line-height:1.8;}}
.summary-bar b{{color:#c0392b;}}
.legend{{background:#fff;border-radius:8px;padding:8px 14px;margin-bottom:14px;font-size:12px;color:#888;border-left:4px solid #f1c40f;}}
.legend span{{display:inline-block;background:{INCREMENT_BG_COLOR};padding:1px 8px;border-radius:3px;font-weight:bold;font-size:13px;color:#856404;}}
.footer{{color:#bbb;font-size:11px;margin-top:24px;padding-top:12px;border-top:1px solid #eee;text-align:center;line-height:1.8;}}

/* ---------- 桌面表格 ---------- */
.desktop-table{{width:100%;border-collapse:collapse;font-size:12px;display:table;}}
.desktop-table th{{background:#c0392b;color:#fff;padding:8px 6px;text-align:center;font-weight:bold;font-size:11px;white-space:nowrap;}}
.desktop-table td{{padding:6px;border-bottom:1px solid #eee;vertical-align:top;}}
.desktop-table tr:nth-child(even){{background:#fafafa;}}
.desktop-table tr:hover{{background:#fef0f0;}}
.desktop-table .tr-new td{{background:{INCREMENT_BG_COLOR} !important;}}
.desktop-table .tr-new:hover td{{background:#ffe69c !important;}}
.source-links a{{color:#c0392b;text-decoration:none;margin-right:2px;white-space:nowrap;font-size:11px;}}
.source-links a:hover{{text-decoration:underline;}}
.new-badge{{background:#f1c40f;color:#856404;font-size:10px;padding:0 4px;border-radius:2px;font-weight:bold;margin-left:3px;}}
.new-badge-full{{display:inline-block;background:{INCREMENT_BG_COLOR};padding:1px 6px;border-radius:3px;font-weight:bold;font-size:11px;color:#856404;margin-bottom:2px;}}

/* ---------- 移动端卡片 ---------- */
.mobile-cards{{display:none;width:100%;}}
.event-card{{background:#fff;border-radius:8px;padding:12px 14px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,0.08);position:relative;}}
.event-card-new{{background:{INCREMENT_BG_COLOR};}}
.card-header{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;}}
.card-company{{font-size:15px;font-weight:bold;color:#333;}}
.card-round{{font-size:12px;color:#c0392b;background:#fef0f0;padding:1px 8px;border-radius:10px;white-space:nowrap;}}
.card-meta{{font-size:12px;color:#888;margin-bottom:4px;line-height:1.5;}}
.card-meta strong{{color:#555;}}
.card-tag{{display:inline-block;font-size:10px;color:#c0392b;background:#fef0f0;padding:0 6px;border-radius:3px;margin-right:4px;margin-top:2px;}}
.card-desc{{font-size:12px;color:#666;margin:6px 0;line-height:1.5;}}
.card-sources{{font-size:11px;color:#999;margin-top:6px;}}
.card-sources a{{color:#c0392b;text-decoration:none;}}
.card-investors{{font-size:12px;color:#555;margin:4px 0;line-height:1.4;}}
.no-event-box{{background:#fff;border-radius:8px;padding:24px;text-align:center;color:#999;font-size:14px;box-shadow:0 1px 3px rgba(0,0,0,0.08);}}
.no-event-box .icon{{font-size:36px;margin-bottom:8px;}}

/* ---------- 媒体查询 ---------- */
@media only screen and (max-width:600px){{
.container{{padding:12px 10px;}}
h2{{font-size:18px;}}
.desktop-table{{display:none !important;}}
.mobile-cards{{display:block !important;}}
}}
@media only screen and (min-width:601px){{
.desktop-table{{display:table;}}
.mobile-cards{{display:none;}}
}}
"""


def _format_amount(amount):
    """金额格式化"""
    if not amount or amount == "未披露":
        return '<span style="color:#bbb;">未披露</span>'
    return amount


def _format_date(date_str):
    """日期格式化"""
    if not date_str:
        return "-"
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%m/%d")
    except:
        return date_str


def _render_sources(event):
    """将多条来源渲染为 HTML 链接"""
    sources = event.get("sources", [])
    if not sources:
        return ""

    links = []
    for src in sources[:4]:  # 最多显示4条
        name = src.get("name", "来源")
        url = src.get("url", "")
        if url:
            links.append(f'<a href="{url}" target="_blank">{name}</a>')
    return " · ".join(links) if links else ""


def _render_sources_table(event):
    """表格内来源列渲染（短标签）"""
    sources = event.get("sources", [])
    if not sources:
        return ""

    links = []
    for src in sources[:3]:
        name = src.get("name", "来源")
        short_name = name
        # 名称缩写
        for abbr in ["投资界", "36氪", "新浪", "腾讯", "搜狐", "网易", "百度", "官网"]:
            if abbr in name:
                short_name = abbr
                break
        url = src.get("url", "")
        if url:
            links.append(f'<a href="{url}" target="_blank" style="color:#c0392b;text-decoration:none;margin-right:2px;white-space:nowrap;font-size:11px;">{short_name}</a>')
    return " ".join(links) if links else ""


def build_dataframe(events):
    """从事件列表构建 DataFrame"""
    df = pd.DataFrame(events)
    if len(df) > 0:
        df = df.sort_values("event_date", ascending=False).reset_index(drop=True)
        df.insert(0, "序号", range(1, len(df) + 1))
    return df


# ============================================================
# 桌面端表格渲染
# ============================================================
# 桌面端只展示核心列
DESKTOP_COLS = [
    "company_name", "industry", "round_type", "amount", "investors",
    "hongshan_role", "event_date", "sources"
]
DESKTOP_LABELS = {
    "company_name": "公司", "industry": "行业", "round_type": "轮次", "amount": "金额",
    "investors": "投资方", "hongshan_role": "角色",
    "event_date": "日期", "sources": "来源"
}


def _render_desktop_table(events, highlight_new=True):
    """渲染桌面端表格 HTML"""
    rows_html = ""
    for event in events:
        is_new = event.get("is_new", False)
        row_class = 'tr-new' if (highlight_new and is_new) else ''
        new_badge = f'<span class="new-badge">{INCREMENT_LABEL}</span>' if (highlight_new and is_new) else ''

        cells = ""
        for col in DESKTOP_COLS:
            val = ""
            if col == "company_name":
                val = f'{event.get("company_name", "")}'
            elif col == "sources":
                val = _render_sources_table(event)
            elif col == "event_date":
                val = _format_date(event.get(col, ""))
            elif col == "amount":
                val = _format_amount(event.get(col, ""))
            elif col == "investors":
                # 截断投资方
                inv = event.get("investors", "")
                if len(inv) > 30:
                    val = inv[:28] + "…"
                else:
                    val = inv
            elif col == "hongshan_role":
                role = event.get(col, "")
                if role == "领投":
                    val = '<span style="color:#e74c3c;font-weight:bold;">领投</span>'
                elif role == "跟投":
                    val = '<span style="color:#e67e22;">跟投</span>'
                else:
                    val = '<span style="color:#999;">参与</span>'
            else:
                val = event.get(col, "")
            cells += f"<td>{new_badge}{val}</td>"

        rows_html += f'<tr class="{row_class}">{cells}</tr>\n'

    headers = "".join(f"<th>{DESKTOP_LABELS.get(c, c)}</th>" for c in DESKTOP_COLS)
    header_html = f"<tr>{headers}</tr>"

    return f'<table class="desktop-table"><thead>{header_html}</thead><tbody>{rows_html}</tbody></table>'


# ============================================================
# 移动端卡片渲染
# ============================================================
def _render_mobile_cards(events, highlight_new=True):
    """渲染移动端卡片式列表 HTML"""
    cards_html = ""
    for event in events:
        is_new = event.get("is_new", False)
        card_class = "event-card event-card-new" if (highlight_new and is_new) else "event-card"
        new_tag = f'<span class="new-badge-full">{INCREMENT_LABEL} 新增</span><br>' if (highlight_new and is_new) else ""

        company = event.get("company_name", "")
        round_type = event.get("round_type", "")
        amount = _format_amount(event.get("amount", ""))
        event_date = _format_date(event.get("event_date", ""))
        industry = event.get("industry", "")
        location = event.get("location", "")
        founded = event.get("founded_date", "")
        investors = event.get("investors", "")
        hongshan_role = event.get("hongshan_role", "")
        intro = event.get("intro", "") or event.get("description", "")
        if len(intro) > 120:
            intro = intro[:117] + "…"

        sources_html = _render_sources(event)

        # 行业标签
        tag_html = ""
        if industry:
            tag_html += f'<span class="card-tag">{industry}</span>'
        if location:
            tag_html += f'<span class="card-tag">{location}</span>'
        if founded:
            tag_html += f'<span class="card-tag">成立{founded}</span>'

        role_text = hongshan_role if hongshan_role else "参与"

        cards_html += f"""
<div class="{card_class}">
  {new_tag}
  <div class="card-header">
    <span class="card-company">{company}</span>
    <span class="card-round">{round_type}</span>
  </div>
  <div class="card-meta"><strong>金额</strong>：{amount} &nbsp;|&nbsp; <strong>日期</strong>：{event_date}</div>
  <div class="card-meta"><strong>红杉</strong>：{role_text} &nbsp;|&nbsp; <strong>投资方</strong>：{investors[:80] if len(investors) > 80 else investors}</div>
  {tag_html}
  {f'<div class="card-desc">{intro}</div>' if intro else ''}
  {f'<div class="card-sources">📎 {sources_html}</div>' if sources_html else ''}
</div>"""

    return f'<div class="mobile-cards">{cards_html}</div>' if cards_html else ""


# ============================================================
# 报告生成函数
# ============================================================
def _build_header(title, summary_lines, events, show_legend=True, highlight_new=True):
    """构建 HTML 头部 + 摘要 + 图例 + 表格 + 卡片"""
    now_str = datetime.now().strftime("%Y年%m月%d日")
    summary = "".join(f"<p style='margin:2px 0;'>{line}</p>" for line in summary_lines)

    legend_html = ""
    if show_legend and highlight_new:
        new_count = sum(1 for e in events if e.get("is_new", False))
        if new_count > 0:
            legend_html = f'<div class="legend"><span>{INCREMENT_LABEL} 新增事件</span> 标记为增量数据</div>'

    desktop_html = _render_desktop_table(events, highlight_new=highlight_new) if events else ""
    mobile_html = _render_mobile_cards(events, highlight_new=highlight_new) if events else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>{BASE_STYLE}</style>
</head>
<body>
<div class="container">
<h2>🔴 {title}</h2>
<p class="subtitle">{now_str}</p>
<div class="summary-bar">{summary}</div>
{legend_html}
{desktop_html}
{mobile_html}
{f'<div class="no-event-box"><div class="icon">📭</div><p>{datetime.now().strftime("%Y年%m月%d日")} 红杉中国无新增天使/A轮投资事件披露。</p></div>' if not events else ''}
<p class="footer">数据来源：投资界(pedaily.cn)、36氪、新浪财经等多渠道交叉验证<br>由 HongShan VC Monitor 自动生成</p>
</div>
</body>
</html>"""


def generate_daily_html(events, has_new=True):
    """
    日报模式：增量推送
    """
    title = "红杉中国 HongShan 天使/A轮投资 · 日报"
    if not has_new or not events:
        return _build_header(
            title,
            [f"📭 今日红杉中国无新增天使/A轮投资事件披露。"],
            [], show_legend=False
        )

    new_count = sum(1 for e in events if e.get("is_new", False))
    return _build_header(
        title,
        [f"📊 本次新增 <b>{new_count}</b> 条天使/A轮投资事件",
         f"🕐 覆盖过去 24 小时增量数据"],
        events, show_legend=True, highlight_new=True
    )


def generate_weekly_html(events):
    """
    周报模式：全量 + 增量标识
    """
    title = "红杉中国 HongShan 天使/A轮投资 · 周报"
    total = len(events)
    new_count = sum(1 for e in events if e.get("is_new", False))

    return _build_header(
        title,
        [f"📊 近{TIME_WINDOW_DAYS}天共 <b>{total}</b> 条投资事件",
         f"🆕 过去 7 日新增 <b>{new_count}</b> 条"],
        events, show_legend=True, highlight_new=True
    )


def generate_full_html(events):
    """
    全量模式：不含增量标识
    """
    title = "红杉中国 HongShan 天使/A轮投资监控"
    if not events:
        return _build_header(
            title,
            [f"📭 近{TIME_WINDOW_DAYS}天无符合条件的投资事件"],
            [], show_legend=False, highlight_new=False
        )

    return _build_header(
        title,
        [f"📊 近{TIME_WINDOW_DAYS}天共 <b>{len(events)}</b> 条投资事件",
         f"🕐 数据截至 {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
        events, show_legend=False, highlight_new=False
    )
