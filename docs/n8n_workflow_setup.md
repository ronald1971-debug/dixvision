# I-37 — n8n Workflow Setup for web_autolearn Pipeline

**ADAPTED FROM:** https://github.com/n8n-io/n8n  
**License:** Sustainable Use License (FLAG: review before production)  
**Classification:** PATTERN_ONLY (REST client integration)

## Overview

n8n serves as a visual workflow orchestrator for the `sensory/web_autolearn/`
pipeline. Operators configure crawl sources, filters, and schedules via the
n8n GUI without writing code.

## Architecture

```
┌─────────────────────┐        ┌──────────────────────┐
│  n8n Workflow GUI    │        │  DIX sensory layer   │
│                     │        │                      │
│  [Crawl Sources]    │──REST──│  n8n_pipeline.py     │
│  [Filters]          │        │  ↓                   │
│  [Schedules]        │        │  crawler.py          │
│  [Webhook Output]───│──POST──│  ↓                   │
│                     │        │  pending_buffer.py   │
└─────────────────────┘        └──────────────────────┘
```

## Setup

### 1. Install n8n

```bash
# Docker (recommended)
docker run -d --name n8n -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n

# Or via npm
npm install -g n8n
n8n start
```

### 2. Configure API Key

1. Open n8n GUI at `http://localhost:5678`
2. Go to Settings → API → Create API Key
3. Store key in DIX credentials system

### 3. Create Crawl Workflow

Example workflow for news crawling:
1. **Schedule Trigger** → every 15 minutes
2. **HTTP Request** → fetch RSS feeds (configurable URLs)
3. **Function** → extract article URLs
4. **HTTP Request** → fetch each article
5. **Webhook** → POST to DIX at `/api/sensory/webhook`

### 4. Configure DIX Integration

```python
from sensory.web_autolearn.n8n_pipeline import N8nPipelineClient

client = N8nPipelineClient(
    base_url="http://localhost:5678",
    api_key="your-n8n-api-key",
    in_memory=False,
)

# List available workflows
workflows = client.list_workflows()

# Trigger a specific crawl workflow
result = client.trigger_workflow(
    workflow_id="crawl-news-sources",
    input_data={"sources": ["reuters", "bloomberg"]},
)
```

## Workflow Templates

### News Crawler
- Trigger: Schedule (every 15 min)
- Sources: RSS feeds from `seeds.yaml`
- Output: Webhook to DIX with extracted articles

### Social Sentiment
- Trigger: Schedule (every 5 min)
- Sources: Twitter/X API, Reddit API
- Output: Webhook with sentiment scores

### SEC Filings
- Trigger: Schedule (every hour)
- Sources: SEC EDGAR RSS
- Output: Webhook with filing metadata

## Security

- n8n API key stored in DIX credentials (never in code)
- Webhook endpoint requires authentication token
- n8n runs on internal network only (not exposed to internet)
