# llms.txt Generator

Automatically generates [llms.txt](https://llmstxt.org/) files for any website. Paste a URL, watch it crawl in real-time, and get an AI-organized llms.txt that helps LLMs understand your site.

**Live demo:** [https://amusing-reprieve-production-ac49.up.railway.app](https://amusing-reprieve-production-ac49.up.railway.app)

<img width="1624" height="994" alt="Screenshot 2026-02-19 at 4 27 07 PM" src="https://github.com/user-attachments/assets/a6e0d04d-a08a-4e43-a666-83dbda4bcb3f" />


## How It Works

1. **Submit a URL** — site is registered and a crawl task is enqueued
2. **Crawl** — worker performs BFS traversal, respecting robots.txt and parsing sitemaps. JS-heavy SPAs are auto-detected and rendered with headless Chromium
3. **Extract & Categorize** — each page is parsed for title, description, and headings, then classified by URL pattern (Docs, API, Guides, Blog, etc.)
4. **Generate** — pages are sent to an LLM (GPT) which selects the most important pages and organizes them into a structured llms.txt
5. **Monitor** — optional cron scheduling re-crawls sites and regenerates llms.txt only when meaningful changes are detected

<img width="1624" height="994" alt="Screenshot 2026-02-19 at 4 27 45 PM" src="https://github.com/user-attachments/assets/d89b11f5-2a60-40fd-be63-417f653c0dbd" />

<img width="1624" height="994" alt="Screenshot 2026-02-19 at 4 28 11 PM" src="https://github.com/user-attachments/assets/b763fae3-5b57-4d7c-a14e-f8abf4eef28e" />

## Architecture

```
                    ┌──────────────┐
                    │   Frontend   │
                    │  React + TS  │
                    │   (Nginx)    │
                    └──────┬───────┘
                           │ HTTP
                           ▼
                    ┌──────────────┐
                    │   Backend    │
                    │   FastAPI    │
                    │  (REST+SSE)  │
                    └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │  PostgreSQL  │
                    │  (DB Queue)  │
                    └──────┬───────┘
                           │ poll + claim
                    ┌──────┴───────┐
                    │    Worker    │
                    │  Crawler +   │
                    │  LLM Gen +   │
                    │  Scheduler   │
                    └──────────────┘
```

**Frontend** — React SPA. Calls backend API directly. Live crawl feed via SSE.

**Backend** — FastAPI. REST API, SSE streams, DB management. Does not crawl — just enqueues tasks.

**Worker** — Polls a Postgres-backed task queue (`SELECT ... FOR UPDATE SKIP LOCKED`). Runs crawls, generates llms.txt via LLM, handles cron scheduling. Horizontally scalable — multiple replicas claim tasks independently with no duplicate work.

**PostgreSQL** — Stores sites, pages, crawl jobs, generated files, schedules, and the durable task queue.

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | React 18, TypeScript, Vite, TanStack Query, Tailwind CSS, CodeMirror |
| **Backend** | FastAPI, SQLAlchemy 2.0 (async), Alembic, httpx (HTTP/2), Playwright |
| **Database** | PostgreSQL 16 |
| **LLM** | OpenAI SDK with structured outputs (JSON schema) |
| **Infra** | Docker Compose, Nginx, Railway |

## Features

- **2-tier crawling** — httpx for static sites, Playwright (headless Chromium) auto-fallback for SPAs
- **Smart SPA detection** — output-quality probe: if static fetch yields few links, Playwright renders the page and promotes the domain to JS mode
- **Live visualization** — real-time SSE feed showing each page as it's discovered
- **LLM-powered organization** — GPT selects and groups the most important pages into clean sections
- **Inline editing** — edit the generated llms.txt directly in the browser
- **Scheduled re-crawls** — cron-based monitoring with incremental change detection
- **Version history** — every generation is versioned with diff tracking
- **Durable task queue** — Postgres-backed with lease ownership, retry with backoff, and crash recovery

## Quick Start

```bash
# Clone
git clone https://github.com/smidthebest/llmstxt-generator.git
cd llmstxt-generator

# Set OpenAI key for LLM-powered generation (optional — falls back to template)
export LLMSTXT_OPENAI_KEY=sk-...

# Start everything
docker compose up -d --build

# Open browser
open http://localhost:3000
```

API docs available at `http://localhost:8000/docs`.

## Configuration

Key environment variables (set in `docker-compose.yml` or `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLMSTXT_OPENAI_KEY` | _(empty)_ | OpenAI API key. Falls back to template generation if unset. |
| `LLM_MODEL` | `gpt-5.2` | OpenAI model for llms.txt generation |
| `MAX_CRAWL_PAGES` | `200` | Default max pages per crawl |
| `MAX_CRAWL_DEPTH` | `3` | Default BFS depth (1-5) |
| `CRAWL_CONCURRENCY` | `20` | Concurrent fetch workers per crawl |

See `backend/app/config.py` for the full list of configuration options.

## Deployment (Railway)

The app runs on [Railway](https://railway.com) as four services from one repo.

### Setup

1. Create a Railway project with a **PostgreSQL** database

2. Add three services from the GitHub repo:

   | Service | Root Directory | Start Command |
   |---------|---------------|---------------|
   | **backend** | `backend` | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
   | **worker** | `backend` | `until alembic upgrade head; do sleep 2; done && python -m app.worker` |
   | **frontend** | `frontend` | _(Dockerfile handles it)_ |

3. Set environment variables:

   **Backend + Worker** (shared):
   - `DATABASE_URL` → `${{Postgres.DATABASE_URL}}`
   - `LLMSTXT_OPENAI_KEY` → your key
   - `LLM_MODEL` → `gpt-4.1`

   **Backend only**: `CORS_ORIGINS` → `["https://your-frontend.up.railway.app"]`, `RUN_SCHEDULER` → `false`

   **Worker only**: `RUN_SCHEDULER` → `true`

   **Frontend only**: `VITE_API_URL` → `https://your-backend.up.railway.app/api` _(build-time variable — redeploy after changing)_

4. Generate public domains for backend and frontend in Railway networking settings

5. Set watch paths to prevent cross-service rebuilds: `backend/**` for backend/worker, `frontend/**` for frontend

### Scaling

Both the API and worker services scale horizontally by increasing replicas in Railway. Workers use `FOR UPDATE SKIP LOCKED` for atomic task claiming — no duplicate work, no configuration needed.

[Screenshot: Schedule configuration — cron expression input with next run preview]

[Screenshot: Version history — list of previous generations with timestamps]

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/sites` | Create site + start initial crawl |
| `GET` | `/api/sites` | List all sites |
| `DELETE` | `/api/sites/{id}` | Delete site and all data |
| `POST` | `/api/sites/{id}/crawl` | Start a new crawl |
| `GET` | `/api/sites/{id}/crawl/{jobId}/stream` | SSE live crawl feed |
| `GET` | `/api/sites/{id}/llms-txt` | Get latest llms.txt |
| `PUT` | `/api/sites/{id}/llms-txt` | Save manual edits |
| `GET` | `/api/sites/{id}/llms-txt/history` | Version history |
| `PUT` | `/api/sites/{id}/schedule` | Set crawl schedule |

Full interactive docs at `/docs` (Swagger UI).
