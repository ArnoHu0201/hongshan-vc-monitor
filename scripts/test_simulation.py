"""
模拟测试脚本 v2：模拟2026年3-5月，测试日报/周报机制
修正：无新增事件的工作日也发送"无新增"通知邮件
"""

import sys
import os
import logging
from datetime import datetime, timedelta

# 环境变量
os.environ['SMTP_SENDER'] = 'system@cardatatool.com'
os.environ['SMTP_PASSWORD'] = 'S66JZxrz59aQcxXM'
os.environ['EMAIL_TO'] = 'tshu@che300.com'

sys.path.insert(0, '.')
from config import TARGET_ROUNDS
from processor import mark_incremental
from renderer import generate_daily_html, generate_weekly_html
from email_sender import send_email_smtp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ============================================================
# 3-5月准确事件数据（经新闻页核验）
# ============================================================
EVENTS_3_5 = [
    # 3月
    {
        "company_name": "CODE27",
        "round_type": "天使轮",
        "event_date": "2026-03-18",
        "news_url": "https://m.pedaily.cn/news/561813",
        "desc": "CODE27完成超千万美元天使轮融资，红杉中国参与",
    },
    {
        "company_name": "汇天",
        "round_type": "A轮",
        "event_date": "2026-03-13",
        "news_url": "https://m.pedaily.cn/news/561685",
        "desc": "低空经济企业汇天完成2亿美元A轮融资，红杉中国参与",
    },
    # 4月 - 无符合条件的天使/A轮事件（A+轮不在目标范围）
    # 5月
    {
        "company_name": "LiberAI",
        "round_type": "天使轮",
        "event_date": "2026-05-15",
        "news_url": "https://m.pedaily.cn/news/563925",
        "desc": "LiberAI完成数亿元天使轮融资，红杉中国参与",
    },
]

# 6月数据（已核验）
EVENTS_6 = [
    {
        "company_name": "栗上LISSOME",
        "round_type": "A轮",
        "event_date": "2026-06-22",
        "news_url": "https://m.pedaily.cn/news/565409",
        "desc": "栗上LISSOME完成A轮融资，红杉中国参与",
    },
    {
        "company_name": "无界动力",
        "round_type": "天使轮",
        "event_date": "2026-06-26",
        "news_url": "https://m.pedaily.cn/news/565576",
        "desc": "无界动力完成超2亿美元天使轮融资，红杉中国参与",
    },
]

def build_event(raw):
    """构建标准事件 dict"""
    return {
        "company_name": raw["company_name"],
        "company_id": "",
        "company_url": raw["news_url"],
        "round_type": raw["round_type"],
        "amount": "未披露",
        "event_date": raw["event_date"],
        "industry": "",
        "investors": ["红杉中国"],
        "hongshan_role": "参与",
        "description": raw["desc"],
        "sources": [{"name": "投资界(新闻)", "url": raw["news_url"]}],
    }


def simulate_daily_report(date_str, new_events, sent_records):
    """模拟日报 - 无论有无新增都发邮件"""
    logger.info(f"=== 模拟日报: {date_str} ===")
    
    if not new_events:
        html = generate_daily_html([], has_new=False)
        subject = f"红杉中国(HongShan) 天使/A轮投资监控 - 日报 ({date_str})"
        logger.info(f"  无新增事件，发送'无新增'通知")
    else:
        marked = mark_incremental(new_events, sent_records)
        html = generate_daily_html(marked, has_new=True)
        subject = f"红杉中国(HongShan) 天使/A轮投资监控 - 日报 ({date_str})"
        # 更新 sent_records
        for e in new_events:
            key = f"{e['company_name']}|{e['round_type']}|{e['event_date']}"
            if key not in sent_records:
                sent_records.append(key)
        logger.info(f"  新增 {len(new_events)} 条事件")
    
    result = send_email_smtp(subject, html)
    logger.info(f"  日报邮件发送: {result}")
    return sent_records


def simulate_weekly_report(date_str, events_up_to_date, sent_records):
    """模拟周报"""
    logger.info(f"=== 模拟周报: {date_str} ===")
    
    if not events_up_to_date:
        html = generate_weekly_html([])
    else:
        marked = mark_incremental(events_up_to_date, sent_records)
        html = generate_weekly_html(marked)
    
    subject = f"红杉中国(HongShan) 天使/A轮投资监控 - 周报 ({date_str})"
    result = send_email_smtp(subject, html)
    logger.info(f"  周报邮件发送: {result} (全量{len(events_up_to_date)}条)")
    return sent_records


def run_simulation():
    """模拟3-5月 + 6月"""
    sent_records = []
    
    # 合并所有事件
    all_events = [build_event(e) for e in EVENTS_3_5 + EVENTS_6]
    all_events.sort(key=lambda x: x['event_date'])
    
    logger.info(f"总事件数: {len(all_events)}")
    for e in all_events:
        print(f"  {e['event_date']} | {e['company_name']} | {e['round_type']}")
    
    print("\n" + "="*60)
    print("模拟 2026年3月1日 ~ 6月30日 日报/周报")
    print("="*60)
    
    # 周报日期：每周一
    mondays = []
    d = datetime(2026, 3, 1)
    while d <= datetime(2026, 6, 30):
        if d.weekday() == 0:  # 周一
            mondays.append(d)
        d += timedelta(days=1)
    
    dailies_sent = 0
    weeklies_sent = 0
    
    current_date = datetime(2026, 3, 1)
    end_date = datetime(2026, 6, 30)
    
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        is_weekday = current_date.weekday() < 5  # 周一到周五
        
        # 日报：每个工作日都发（无论有无新增）
        if is_weekday:
            todays_events = [e for e in all_events if e['event_date'] == date_str]
            sent_records = simulate_daily_report(date_str, todays_events, sent_records)
            dailies_sent += 1
        
        # 周报：每周一
        if current_date in mondays:
            events_sofar = [e for e in all_events if e['event_date'] <= date_str]
            sent_records = simulate_weekly_report(date_str, events_sofar, sent_records)
            weeklies_sent += 1
        
        current_date += timedelta(days=1)
    
    print("\n" + "="*60)
    print(f"模拟完成!")
    print(f"  日报: {dailies_sent} 封 (每个工作日)")
    print(f"  周报: {weeklies_sent} 封 (每周一)")
    print(f"  sent_records: {len(sent_records)} 条")
    print("="*60)


if __name__ == "__main__":
    run_simulation()
