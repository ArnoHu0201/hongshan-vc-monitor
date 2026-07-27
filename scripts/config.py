"""
红杉中国投资监控 - 配置文件
支持从环境变量和 .env 文件读取敏感信息，适配 GitHub Actions 云端运行
"""

import os
from pathlib import Path

# ============================================================
# 自动加载 .env 文件（本地运行方便，不影响 GitHub Actions）
# ============================================================
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    with open(_env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key and not os.environ.get(key):  # 环境变量优先
                    os.environ[key] = value

# ============================================================
# 数据源配置
# ============================================================
HONGSHAN_VC_URL = "https://vc.pedaily.cn/vc/106728.html"
HONGSHAN_VC_ID = "106728"
COMPANY_DETAIL_BASE = "https://vc.pedaily.cn/company/"

# 目标轮次（含子变体）
TARGET_ROUNDS = ["天使轮", "天使+轮", "Pre-A轮", "A轮", "A+轮"]

# 时间窗口
TIME_WINDOW_DAYS = 30  # 全量数据时间窗口
WEEKLY_INCREMENT_DAYS = 7  # 周报增量标识时间窗口

# ============================================================
# 文件路径
# ============================================================
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

SENT_RECORDS_FILE = OUTPUT_DIR / "sent_records.json"
COMPANY_CACHE_FILE = OUTPUT_DIR / "company_detail_cache.json"

# ============================================================
# 邮件配置 (SMTP - 用于云端/自动化)
# ============================================================
SMTP_SERVER = "smtp.exmail.qq.com"
SMTP_PORT = 465  # SSL
SMTP_SENDER = os.environ.get("SMTP_SENDER", "system@cardatatool.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")  # 从环境变量读取授权码
EMAIL_TO = os.environ.get("EMAIL_TO", "rzwei@che300.com").split(",")  # 支持多收件人(逗号分隔)
EMAIL_CC = os.environ.get("EMAIL_CC", "").split(",") if os.environ.get("EMAIL_CC") else []

# ============================================================
# HTTP 请求配置
# ============================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://vc.pedaily.cn/",
}

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
]

# ============================================================
# 增量标识样式
# ============================================================
INCREMENT_BG_COLOR = "#fff3cd"  # 黄色背景色
INCREMENT_LABEL = "🆕"  # 增量标记符号
