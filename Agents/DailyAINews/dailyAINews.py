#!/usr/bin/env python3
"""
Daily AI News automation script.

What it does:
1) Pulls top 5 AI/software news items from NewsAPI.
2) Summarizes them with a GitHub-model API using your GitHub token (PAT).
3) Sends the summary via Gmail.

This script is designed for one-time execution. Use an external scheduler
(e.g., GitHub Actions cron) to run it daily.

Environment variables:
- NEWSAPI_KEY              (required)
- COPILOT_PAT              (required for AI summary)
- GITHUB_MODEL             (optional, default: gpt-4o-mini)
- GITHUB_MODELS_ENDPOINT   (optional, default: https://models.inference.ai.azure.com/chat/completions)
- GMAIL_APP_PASSWORD       (required for Gmail SMTP)
- EMAIL_FROM               (optional, default: atnew.ai@gmail.com)
- EMAIL_TO                 (optional, default: projjal007@gmail.com)
- SMTP_HOST                (optional, default: smtp.gmail.com)
- SMTP_PORT                (optional, default: 465)
"""

from __future__ import annotations

import json
import html
import os
import smtplib
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


NEWS_API_URL = "https://newsapi.org/v2/everything"
DEFAULT_QUERY = '"Artificial Intelligance" OR "Artificial Intelligence" OR "Software Technology"'
DEFAULT_SUBJECT = "Your Daily AI News - AtNews"
DEFAULT_FROM = "atnew.ai@gmail.com"
DEFAULT_TO = "projjal007@gmail.com,projwal20@gmail.com,kalyan.halder12@gmail.com"
DEFAULT_GITHUB_MODEL = "gpt-4o-mini"
DEFAULT_MODELS_ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"
BANNER_FILENAME = "AtNew_banner.jpeg"


@dataclass
class NewsItem:
    title: str
    source: str
    published_at: str
    url: str
    description: str


def get_ist_timezone() -> timezone:
    if ZoneInfo is not None:
        try:
            return ZoneInfo("Asia/Kolkata")
        except (KeyError, Exception):
            pass
    return timezone(timedelta(hours=5, minutes=30))


def fetch_top_news(newsapi_key: str, page_size: int = 5) -> List[NewsItem]:
    query_params = {
        "q": DEFAULT_QUERY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": str(page_size),
        "apiKey": newsapi_key,
    }
    url = NEWS_API_URL + "?" + urllib.parse.urlencode(query_params)

    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"News API HTTP error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"News API connection error: {exc}") from exc

    if payload.get("status") != "ok":
        raise RuntimeError(f"News API error: {payload}")

    articles = payload.get("articles", [])
    items: List[NewsItem] = []
    for article in articles[:page_size]:
        items.append(
            NewsItem(
                title=(article.get("title") or "Untitled").strip(),
                source=(article.get("source", {}) or {}).get("name", "Unknown Source"),
                published_at=(article.get("publishedAt") or "").strip(),
                url=(article.get("url") or "").strip(),
                description=(article.get("description") or "").strip(),
            )
        )

    return items


def build_summary_prompt(items: List[NewsItem]) -> str:
    lines = []
    for idx, item in enumerate(items, start=1):
        lines.append(
            f"{idx}. Title: {item.title}\n"
            f"   Source: {item.source}\n"
            f"   Published: {item.published_at}\n"
            f"   Description: {item.description}\n"
            f"   URL: {item.url}"
        )
    joined = "\n\n".join(lines)

    return (
        "Create a concise daily AI news digest from these articles. "
        "Return:\n"
        "1) A 2-3 sentence overall summary.\n"
        "2) 5 bullet points (one per article) with impact for software/AI professionals.\n"
        "3) A short 'Why it matters today' line.\n\n"
        f"Articles:\n{joined}"
    )


def summarize_with_github_models(items: List[NewsItem], pat: str) -> str:
    endpoint = os.getenv("GITHUB_MODELS_ENDPOINT", DEFAULT_MODELS_ENDPOINT)
    model = os.getenv("GITHUB_MODEL", DEFAULT_GITHUB_MODEL)

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are an expert tech news analyst. Keep summaries factual and concise.",
            },
            {
                "role": "user",
                "content": build_summary_prompt(items),
            },
        ],
        "temperature": 0.3,
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {pat}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"GitHub model HTTP error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub model connection error: {exc}") from exc

    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError(f"Unexpected model response: {result}")

    content = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError(f"Empty summary from model response: {result}")

    return content


def fallback_summary(items: List[NewsItem]) -> str:
    lines = ["AI News Summary (fallback mode):"]
    for i, item in enumerate(items, start=1):
        lines.append(f"- {i}. {item.title} ({item.source})")
    lines.append("Why it matters today: AI and software news is moving fast; keep tracking signals daily.")
    return "\n".join(lines)


def compose_email_body(items: List[NewsItem], summary_text: str) -> str:
    lines = [
        "Your Daily AI News Digest",
        "",
        summary_text,
        "",
        "Source Articles:",
    ]

    for i, item in enumerate(items, start=1):
        lines.extend(
            [
                f"{i}) {item.title}",
                f"   Source: {item.source}",
                f"   Published: {item.published_at}",
                f"   Link: {item.url}",
                "",
            ]
        )

    lines.extend(
        [
            f"Generated at: {datetime.now(get_ist_timezone()).isoformat()}",
            "",
            "Best Regards,",
            "AtNews Agent",
        ]
    )
    return "\n".join(lines)


def _summary_to_html(summary_text: str) -> str:
    section_titles = [
        "Overall Summary",
        "Impact for Software/AI Professionals",
        "Why it matters today",
    ]

    html_parts = []
    list_items = []

    def flush_list() -> None:
        if list_items:
            html_parts.append(
                "<ul style=\"margin:8px 0 0 18px;padding:0;color:#22303d;line-height:1.5;\">"
                + "".join(list_items)
                + "</ul>"
            )
            list_items.clear()

    for raw_line in summary_text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_list()
            continue

        cleaned = line.replace("**", "").lstrip("#").strip()

        matched_heading = None
        remainder = ""
        for title in section_titles:
            if cleaned.lower().startswith(title.lower()):
                matched_heading = title
                remainder = cleaned[len(title):].lstrip(": -")
                break

        if matched_heading:
            flush_list()
            html_parts.append(
                f"<p style=\"margin:12px 0 6px 0;color:#1f7a8c;\"><strong>{html.escape(matched_heading)}</strong></p>"
            )
            if remainder:
                html_parts.append(
                    f"<p style=\"margin:6px 0;color:#22303d;line-height:1.5;\">{html.escape(remainder)}</p>"
                )
            continue

        if line.startswith(("- ", "* ")):
            list_items.append(f"<li>{html.escape(line[2:].strip())}</li>")
            continue

        if line[0].isdigit() and (")" in line[:4] or "." in line[:4]):
            list_items.append(f"<li>{html.escape(line)}</li>")
            continue

        flush_list()
        html_parts.append(
            f"<p style=\"margin:8px 0;color:#22303d;line-height:1.5;\">{html.escape(cleaned)}</p>"
        )

    flush_list()
    return "".join(html_parts)


def compose_email_html(items: List[NewsItem], summary_text: str, include_banner: bool) -> str:
    summary_html = _summary_to_html(summary_text)
    article_rows = []
    for i, item in enumerate(items, start=1):
        article_rows.append(
            "<div style=\"margin-bottom:14px;padding:12px;border:1px solid #d9e1ea;"
            "border-radius:10px;background:#f8fbff;\">"
            f"<p style=\"margin:0 0 6px 0;font-weight:700;color:#102a43;\">{i}) {html.escape(item.title)}</p>"
            f"<p style=\"margin:0;color:#334e68;\"><strong>Source:</strong> {html.escape(item.source)}</p>"
            f"<p style=\"margin:0;color:#334e68;\"><strong>Published:</strong> {html.escape(item.published_at)}</p>"
            f"<p style=\"margin:4px 0 0 0;\"><a href=\"{html.escape(item.url)}\" style=\"color:#0b63ce;\">Read article</a></p>"
            "</div>"
        )

    banner_html = ""
    if include_banner:
        banner_html = (
            "<div style=\"margin-bottom:14px;\">"
            "<img src=\"cid:atnews_banner\" alt=\"AtNews Banner\" "
            "style=\"width:100%;max-width:640px;border-radius:10px;display:block;\"/>"
            "</div>"
        )

    generated_at = html.escape(datetime.now(get_ist_timezone()).isoformat())
    return (
        "<html><body style=\"margin:0;padding:0;background:#f4f7fb;font-family:Segoe UI,Arial,sans-serif;\">"
        "<div style=\"max-width:680px;margin:20px auto;background:#ffffff;border:1px solid #e5e9f0;"
        "border-radius:12px;padding:20px;\">"
        f"{banner_html}"
        "<h2 style=\"margin:0 0 10px 0;color:#0b63ce;\"><strong>Your Daily AI News Digest</strong></h2>"
        "<h3 style=\"margin:14px 0 8px 0;color:#1f7a8c;\"><strong>Summary</strong></h3>"
        f"{summary_html}"
        "<h3 style=\"margin:18px 0 10px 0;color:#1f7a8c;\"><strong>Source Articles</strong></h3>"
        f"{''.join(article_rows)}"
        f"<p style=\"margin:14px 0 0 0;color:#627d98;font-size:13px;\"><strong>Generated at:</strong> {generated_at}</p>"
        "<p style=\"margin:18px 0 0 0;color:#334e68;\">Best Regards,<br/><strong>AtNews Agent</strong></p>"
        "</div></body></html>"
    )


def send_email(
    sender: str,
    recipient: str,
    subject: str,
    body_text: str,
    body_html: str,
    app_password: str,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 465,
) -> None:
    recipient_list = [email.strip() for email in recipient.split(",") if email.strip()]
    if not recipient_list:
        raise RuntimeError("No valid recipient email addresses found in EMAIL_TO.")

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipient_list)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body_text, "plain", "utf-8"))
    alt.attach(MIMEText(body_html, "html", "utf-8"))
    msg.attach(alt)

    banner_path = Path(__file__).resolve().parent / BANNER_FILENAME
    if banner_path.exists():
        with banner_path.open("rb") as banner_file:
            banner = MIMEImage(banner_file.read())
        banner.add_header("Content-ID", "<atnews_banner>")
        banner.add_header("Content-Disposition", "inline", filename=BANNER_FILENAME)
        msg.attach(banner)

    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
        server.login(sender, app_password)
        server.sendmail(sender, recipient_list, msg.as_string())


def run_job() -> None:
    newsapi_key = os.getenv("NEWSAPI_KEY", "").strip()
    github_pat = os.getenv("COPILOT_PAT", "").strip() or os.getenv("GITHUB_COPILOT_PAT", "").strip()
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

    if not newsapi_key:
        raise RuntimeError("Missing NEWSAPI_KEY environment variable.")
    if not github_pat:
        raise RuntimeError("Missing COPILOT_PAT environment variable.")
    if not gmail_app_password:
        raise RuntimeError("Missing GMAIL_APP_PASSWORD environment variable.")

    sender = os.getenv("EMAIL_FROM", DEFAULT_FROM).strip()
    recipient = os.getenv("EMAIL_TO", DEFAULT_TO).strip()
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "465").strip())

    print("[INFO] Fetching top 5 AI/software news...")
    items = fetch_top_news(newsapi_key, page_size=5)

    if not items:
        raise RuntimeError("No news articles returned from NewsAPI.")

    print("[INFO] Generating summary using GitHub model...")
    try:
        summary_text = summarize_with_github_models(items, github_pat)
    except Exception as exc:
        print(f"[WARN] AI summary failed ({exc}). Using fallback summary.")
        summary_text = fallback_summary(items)

    email_body_text = compose_email_body(items, summary_text)
    email_body_html = compose_email_html(items, summary_text, include_banner=True)

    print(f"[INFO] Sending email to {recipient}...")
    send_email(
        sender=sender,
        recipient=recipient,
        subject=DEFAULT_SUBJECT,
        body_text=email_body_text,
        body_html=email_body_html,
        app_password=gmail_app_password,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
    )
    print("[INFO] Email sent successfully.")


def main() -> int:
    try:
        run_job()
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
