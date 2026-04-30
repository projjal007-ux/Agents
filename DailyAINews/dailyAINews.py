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
- GITHUB_COPILOT_PAT       (required for AI summary)
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
import os
import smtplib
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import List

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


NEWS_API_URL = "https://newsapi.org/v2/everything"
DEFAULT_QUERY = '"Artificial Intelligance" OR "Artificial Intelligence" OR "Software Technology"'
DEFAULT_SUBJECT = "Your Daily AI News - AtNews"
DEFAULT_FROM = "atnew.ai@gmail.com"
DEFAULT_TO = "projjal007@gmail.com"
DEFAULT_GITHUB_MODEL = "gpt-4o-mini"
DEFAULT_MODELS_ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"


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

    lines.append(f"Generated at: {datetime.now(get_ist_timezone()).isoformat()}")
    return "\n".join(lines)


def send_email(
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    app_password: str,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 465,
) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
        server.login(sender, app_password)
        server.sendmail(sender, [recipient], msg.as_string())


def run_job() -> None:
    newsapi_key = os.getenv("NEWSAPI_KEY", "").strip()
    github_pat = os.getenv("GITHUB_COPILOT_PAT", "").strip()
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

    if not newsapi_key:
        raise RuntimeError("Missing NEWSAPI_KEY environment variable.")
    if not github_pat:
        raise RuntimeError("Missing GITHUB_COPILOT_PAT environment variable.")
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

    email_body = compose_email_body(items, summary_text)

    print(f"[INFO] Sending email to {recipient}...")
    send_email(
        sender=sender,
        recipient=recipient,
        subject=DEFAULT_SUBJECT,
        body=email_body,
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
