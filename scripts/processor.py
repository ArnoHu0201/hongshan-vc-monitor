"""
红杉中国投资监控 - 数据处理模块
负责筛选、去重、增量检测
"""

import json
import logging
from datetime import datetime, timedelta

from config import TARGET_ROUNDS, TIME_WINDOW_DAYS, WEEKLY_INCREMENT_DAYS, SENT_RECORDS_FILE

logger = logging.getLogger(__name__)


def filter_events(events, target_rounds=None, time_window_days=None):
    """按轮次和时间窗口筛选事件"""
    if target_rounds is None:
        target_rounds = TARGET_ROUNDS
    if time_window_days is None:
        time_window_days = TIME_WINDOW_DAYS

    cutoff_date = (datetime.now() - timedelta(days=time_window_days)).date()

    filtered = []
    for event in events:
        # 轮次筛选
        if event["round_type"] not in target_rounds:
            continue

        # 时间筛选（只比较日期，不含时分秒）
        if event["event_date"]:
            try:
                event_date = datetime.strptime(event["event_date"], "%Y-%m-%d").date()
                if event_date < cutoff_date:
                    continue
            except ValueError:
                pass

        # 必须有公司名
        if not event["company_name"]:
            continue

        filtered.append(event)

    logger.info(f"筛选: {len(filtered)}/{len(events)} 条 (轮次={target_rounds}, 窗口={time_window_days}天)")
    return filtered


def deduplicate_events(events):
    """按公司名+轮次去重，优先保留有 company_id 的版本"""
    seen = {}
    for event in events:
        key = (event["company_name"], event["round_type"])
        if key not in seen:
            seen[key] = event
        else:
            if event.get("company_id") and not seen[key].get("company_id"):
                seen[key] = event
            # 合并 sources 字段（去重）
            old_sources = seen[key].get("sources", [])
            new_sources = event.get("sources", [])
            for s in new_sources:
                if s.get("url") and not any(os.get("url") == s.get("url") for os in old_sources):
                    old_sources.append(s)
            seen[key]["sources"] = old_sources
    return list(seen.values())


def event_key(event):
    """生成事件的唯一标识键"""
    return f"{event['company_name']}|{event['round_type']}|{event.get('event_date', '')}"


def load_sent_records():
    """加载已发送记录"""
    if SENT_RECORDS_FILE.exists():
        try:
            return json.loads(SENT_RECORDS_FILE.read_text(encoding="utf-8"))
        except:
            return []
    return []


def save_sent_records(events):
    """将事件追加到已发送记录"""
    records = load_sent_records()
    for event in events:
        key = event_key(event)
        if key not in records:
            records.append(key)
    SENT_RECORDS_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def get_new_events(events, sent_records):
    """筛选出不在已发送记录中的增量事件"""
    new = []
    for e in events:
        key = event_key(e)
        if key not in sent_records:
            new.append(e)
    return new


def mark_incremental(events, sent_records):
    """为每个事件标记是否为增量（is_new=True/False）"""
    marked = []
    for event in events:
        key = event_key(event)
        event["is_new"] = key not in sent_records
        marked.append(event)
    logger.info(f"增量标记: {sum(1 for e in marked if e['is_new'])}/{len(marked)} 条为新增")
    return marked


def get_recent_increment_keys(sent_records, days=WEEKLY_INCREMENT_DAYS):
    """获取过去 N 天内新增的记录键列表（用于周报增量标识）"""
    cutoff = (datetime.now() - timedelta(days=days)).date()
    # sent_records 只存了键字符串，不含时间信息
    # 增量标识依赖 is_new 标记，在 mark_incremental() 中处理
    # 这里返回全部 sent_records 作为"已发送"集合
    return set(sent_records)
