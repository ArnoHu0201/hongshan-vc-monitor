"""
红杉中国投资监控 - 邮件发送模块
支持 SMTP 发送（云端/自动化场景）和本地 QQ邮箱 MCP 辅助
"""

import smtplib
import re
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from config import SMTP_SERVER, SMTP_PORT, SMTP_SENDER, SMTP_PASSWORD, EMAIL_TO, EMAIL_CC, OUTPUT_DIR

logger = logging.getLogger(__name__)


def send_email_smtp(subject, html_body, to_list=None, cc_list=None, sender=None, password=None):
    """
    通过 SMTP 发送 HTML 邮件。
    适用于 GitHub Actions / 云端自动化场景。

    参数:
    subject: 邮件主题
    html_body: HTML 邮件正文内容
    to_list: 收件人列表（默认使用 config.EMAIL_TO）
    cc_list: 抄送列表
    sender: 发件邮箱（默认使用 config.SMTP_SENDER）
    password: SMTP 授权码（默认使用 config.SMTP_PASSWORD）
    """
    to_list = to_list or EMAIL_TO
    cc_list = cc_list or EMAIL_CC
    sender = sender or SMTP_SENDER
    password = password or SMTP_PASSWORD

    if not password:
        logger.error("SMTP 授权码未设置，无法发送邮件！请在 config.py 或环境变量 SMTP_PASSWORD 中设置。")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    html_part = MIMEText(html_body, "html", "utf-8")
    msg.attach(html_part)

    try:
        if SMTP_PORT == 465:
            # SSL 直连
            server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30)
        else:
            # TLS
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30)
            server.starttls()

        server.login(sender, password)
        all_recipients = to_list + (cc_list or [])
        server.sendmail(sender, all_recipients, msg.as_string())
        server.quit()
        logger.info(f"邮件发送成功: {subject} → {all_recipients}")
        return True
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False


def send_email_smtp_from_file(html_file, subject=None):
    """从 HTML 文件发送邮件"""
    html_file = Path(html_file)
    if not html_file.exists():
        logger.error(f"HTML 文件不存在: {html_file}")
        return False

    html_body = html_file.read_text(encoding="utf-8")
    if not subject:
        subject = f"红杉中国(HongShan) 天使轮/A轮投资监控 - {html_file.stem}"

    return send_email_smtp(subject, html_body)


def get_html_body_for_mcp(html_file):
    """
    为 QQ邮箱 MCP 准备邮件正文内容。
    WorkBuddy 的 QQ邮箱 MCP (mcp__qq-mail__SendMessage) 需要纯 HTML 字符串，
    不含 <html>/<head>/<body> 外层标签（MCP 会自行包装）。

    参数:
    html_file: 生成的 HTML 报告文件路径

    返回:
    dict: { "subject": ..., "body": ..., "body_format": "HTML", "to": [...] }
    """
    html_file = Path(html_file)
    if not html_file.exists():
        logger.error(f"HTML 文件不存在: {html_file}")
        return None

    full_html = html_file.read_text(encoding="utf-8")

    # 提取 <body> 内的内容
    body_match = re.search(r"<body[^>]*>(.*?)</body>", full_html, re.DOTALL)
    if body_match:
        body_content = body_match.group(1)
    else:
        body_content = full_html

    # 提取 <style> 内容
    style_match = re.search(r"<style[^>]*>(.*?)</style>", full_html, re.DOTALL)
    style_content = style_match.group(1) if style_match else ""

    # 组合: style + body
    combined = f"<style>{style_content}</style>\n{body_content}" if style_content else body_content

    # 生成主题
    date_str = html_file.stem.split("_")[-1]
    if "weekly" in html_file.stem:
        subject = f"红杉中国(HongShan) 天使轮/A轮投资监控 - 周报 ({date_str})"
    elif "daily" in html_file.stem:
        subject = f"红杉中国(HongShan) 天使轮/A轮投资监控 - 日报 ({date_str})"
    elif "no_new" in html_file.stem:
        subject = f"红杉中国(HongShan) 投资监控 - 日报: 无新增 ({date_str})"
    else:
        subject = f"红杉中国(HongShan) 天使轮/A轮投资监控 ({date_str})"

    return {
        "subject": subject,
        "body": combined,
        "body_format": "HTML",
        "to": EMAIL_TO,
    }
