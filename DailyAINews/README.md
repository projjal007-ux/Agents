# DailyAINews

Automated daily AI news digest:

1. Fetches top 5 AI/software news articles from NewsAPI.
2. Summarizes the articles using a GitHub model endpoint and your PAT.
3. Sends the summary by email.
4. Runs daily at 7:00 AM IST via GitHub Actions cron.

## Files

- `dailyAINews.py` - one-run Python job (no internal scheduler loop)
- `.github/workflows/daily-ai-news.yml` - cron scheduler and job runner

## Required GitHub Secrets

Set these secrets in repo settings:

1. `NEWSAPI_KEY`
2. `GITHUB_COPILOT_PAT`
3. `GMAIL_APP_PASSWORD`

Path:

- GitHub -> Settings -> Secrets and variables -> Actions -> New repository secret

## Email Defaults

- From: `atnew.ai@gmail.com`
- To: `projjal007@gmail.com`
- Subject: `Your Daily AI News - AtNews`

You can override sender/recipient using environment variables (`EMAIL_FROM`, `EMAIL_TO`).

## Schedule

Cron in workflow:

- `30 1 * * *` (UTC)
- Equivalent to `07:00` IST daily

## Manual Run

You can run the workflow manually:

1. Open Actions tab
2. Select `Daily AI News`
3. Click `Run workflow`

## Local Test (Optional)

```bash
export NEWSAPI_KEY="..."
export GITHUB_COPILOT_PAT="..."
export GMAIL_APP_PASSWORD="..."
python dailyAINews.py
```

PowerShell:

```powershell
$env:NEWSAPI_KEY = "..."
$env:GITHUB_COPILOT_PAT = "..."
$env:GMAIL_APP_PASSWORD = "..."
python .\dailyAINews.py
```

## Notes

- The query includes both `Artificial Intelligance` and `Artificial Intelligence`.
- If model summarization fails, the script sends a fallback summary.
