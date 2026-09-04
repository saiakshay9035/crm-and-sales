# Autonomous AI Lead Generation & Outreach Agent
### Integrated with `trycompai/crm` (Comp AI Agentic CRM)

This agent is built for placing Indian tech talent & end-to-end project management with Western/Dubai startups.

## Architecture

1. **Lead Scraping**: Finds founders/CTOs at startups in US, UAE, EU, and Australia using ScrapeGraphAI/Playwright.
2. **AI Personalization**: Uses **Ollama** (100% local & free) or Groq/Gemini to write tailored pitches highlighting senior developer placement + full product & project management delivery at 60% lower cost.
3. **Agentic CRM Integration (`trycompai/crm`)**: Automatically creates company records, contact records, research notes, and interaction history in your Comp AI CRM.
4. **Outreach Engine**: Handles automated email dispatch via SMTP or Composio with built-in dry-run safety modes.

## Quick Start Guide

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Agent (Test / Dry-Run Mode)
```bash
python main.py
```

### 3. Connect to `trycompai/crm`
If you are self-hosting `trycompai/crm` via Docker or Bun:
* Set `CRM_API_URL` and `CRM_API_KEY` in `config.py` or `.env`.

### 4. Enable Real Email Dispatch
Edit `main.py` and set `dry_run=False`, then update your SMTP / Workspace credentials in `config.py`.
