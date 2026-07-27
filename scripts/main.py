"""
红杉中国投资监控 - 主入口
支持三种运行模式：daily(日报增量)、weekly(周报全量+增量标识)、full(首次全量)
"""

import sys
import json
import logging
from datetime import datetime

from config import OUTPUT_DIR, TIME_WINDOW_DAYS
from scraper import get_session, scrape_all, cross_validate_events
from processor import filter_events, deduplicate_events, load_sent_records, save_sent_records, get_new_events, mark_incremental
from enricher import enrich_events
from renderer import generate_daily_html, generate_weekly_html, generate_full_html
from email_sender import send_email_smtp, get_html_body_for_mcp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def run_daily():
    """
    日报模式：只发送上次日报后的增量事件。
    无增量时发送"无新增事件"通知。
    """
    logger.info("===== 开始日报模式（增量推送） =====")

    # 防重复发送：检查今天是否已有发送记录
    from config import OUTPUT_DIR
    last_run_file = OUTPUT_DIR / "last_daily_run.json"
    today_str = datetime.now().strftime("%Y-%m-%d")
    if last_run_file.exists():
        try:
            last_run_data = json.loads(last_run_file.read_text(encoding="utf-8"))
            if last_run_data.get("date") == today_str and last_run_data.get("sent"):
                logger.info(f"今天 ({today_str}) 已发送过日报，跳过发送。如需重发请删除 {last_run_file}")
                return None
        except Exception:
            pass

    session = get_session()
    all_events = scrape_all(session)

    # 筛选 + 去重
    filtered = filter_events(all_events)
    filtered = deduplicate_events(filtered)

    if not filtered:
        logger.info("无符合条件的投资事件")
        html = generate_daily_html([], has_new=False)
        file_name = f"hongshan_daily_no_new_{datetime.now().strftime('%Y%m%d')}.html"
        html_file = OUTPUT_DIR / file_name
        html_file.write_text(html, encoding="utf-8")
        logger.info(f"日报(无新增): {html_file}")
        return html_file

    # 补充详情
    enriched = enrich_events(filtered, session)

    # 交叉验证：抓取新闻页验证轮次，搜索多平台来源
    enriched = cross_validate_events(enriched, session)

    # 增量检测
    sent_records = load_sent_records()
    new_events = get_new_events(enriched, sent_records)

    if new_events:
        # 标记增量
        marked = mark_incremental(new_events, sent_records)
        html = generate_daily_html(marked, has_new=True)
        file_name = f"hongshan_daily_{datetime.now().strftime('%Y%m%d')}.html"
        # 保存增量记录
        save_sent_records(new_events)
        logger.info(f"日报(有增量): {len(new_events)} 条新事件")
    else:
        html = generate_daily_html([], has_new=False)
        file_name = f"hongshan_daily_no_new_{datetime.now().strftime('%Y%m%d')}.html"
        logger.info("日报(无增量): 无新增事件")

    html_file = OUTPUT_DIR / file_name
    html_file.write_text(html, encoding="utf-8")

    # 尝试 SMTP 发送
    subject = f"红杉中国(HongShan) 天使轮/A轮投资监控 - 日报 ({datetime.now().strftime('%Y年%m月%d日')})"
    send_result = send_email_smtp(subject, html)
    if not send_result:
        logger.warning("SMTP 发送失败（可能授权码未设置），邮件已保存为本地文件")
    else:
        # 标记今天已发送
        last_run_file = OUTPUT_DIR / "last_daily_run.json"
        last_run_file.write_text(
            json.dumps({"date": today_str, "sent": True, "time": datetime.now().isoformat()}, ensure_ascii=False),
            encoding="utf-8"
        )
        logger.info(f"已标记今天 ({today_str}) 日报已发送")

    logger.info(f"日报完成: {html_file}")
    logger.info("===== 日报模式结束 =====")
    return html_file


def run_weekly():
    """
    周报模式：发送全量数据，增量事件带黄色标识。
    同时更新 sent_records。
    """
    logger.info("===== 开始周报模式（全量+增量标识） =====")

    session = get_session()
    all_events = scrape_all(session)

    # 筛选 + 去重
    filtered = filter_events(all_events)
    filtered = deduplicate_events(filtered)

    if not filtered:
        logger.info("近30天无符合条件的投资事件")
        html = generate_weekly_html([])
        html_file = OUTPUT_DIR / f"hongshan_weekly_{datetime.now().strftime('%Y%m%d')}.html"
        html_file.write_text(html, encoding="utf-8")
        return html_file

    # 补充详情
    enriched = enrich_events(filtered, session)

    # 交叉验证
    enriched = cross_validate_events(enriched, session)

    # 增量标识
    sent_records = load_sent_records()
    marked = mark_incremental(enriched, sent_records)

    html = generate_weekly_html(marked)
    html_file = OUTPUT_DIR / f"hongshan_weekly_{datetime.now().strftime('%Y%m%d')}.html"
    html_file.write_text(html, encoding="utf-8")

    # 更新 sent_records（周报将全量事件标记为已发送）
    save_sent_records(enriched)

    # 尝试 SMTP 发送
    subject = f"红杉中国(HongShan) 天使轮/A轮投资监控 - 周报 ({datetime.now().strftime('%Y年%m月%d日')})"
    send_result = send_email_smtp(subject, html)
    if not send_result:
        logger.warning("SMTP 发送失败（可能授权码未设置），邮件已保存为本地文件")

    logger.info(f"周报完成: {html_file}")
    logger.info("===== 周报模式结束 =====")
    return html_file


def run_full():
    """
    全量模式：不区分增量，发送近30天全量数据。
    用于首次运行或手动测试。
    """
    logger.info("===== 开始全量模式 =====")

    session = get_session()
    all_events = scrape_all(session)

    # 筛选 + 去重
    filtered = filter_events(all_events)
    filtered = deduplicate_events(filtered)

    # 补充详情
    enriched = enrich_events(filtered, session) if filtered else []

    # 交叉验证
    if enriched:
        enriched = cross_validate_events(enriched, session)

    html = generate_full_html(enriched)
    html_file = OUTPUT_DIR / f"hongshan_report_{datetime.now().strftime('%Y%m%d')}.html"
    html_file.write_text(html, encoding="utf-8")

    # 保存 JSON 数据
    import pandas as pd
    from renderer import build_dataframe
    df = build_dataframe(enriched)
    if len(df) > 0:
        json_file = OUTPUT_DIR / f"hongshan_data_{datetime.now().strftime('%Y%m%d')}.json"
        df.to_json(json_file, orient="records", force_ascii=False, indent=2)

    logger.info(f"全量报告: {html_file}")
    logger.info("===== 全量模式结束 =====")
    return html_file


def run_test():
    """测试模式：只抓取并打印解析结果，不生成报告"""
    logger.info("===== 测试模式 =====")
    session = get_session()
    all_events = scrape_all(session)
    filtered = filter_events(all_events)
    filtered = deduplicate_events(filtered)

    import json
    print(f"原始事件: {len(all_events)} 条 → 筛选去重后: {len(filtered)} 条")
    for e in filtered:
        print(json.dumps(e, ensure_ascii=False))
    logger.info("===== 测试结束 =====")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"

    if mode == "daily":
        run_daily()
    elif mode == "weekly":
        run_weekly()
    elif mode == "full":
        run_full()
    elif mode == "test":
        run_test()
    else:
        logger.error(f"未知模式: {mode}")
        print("用法: python main.py [daily|weekly|full|test]")
