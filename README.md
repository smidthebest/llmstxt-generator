# llms.txt Generator

A full-stack application that automatically generates [llms.txt](https://llmstxt.org/) files for any website. It crawls a given URL, categorizes discovered pages, computes relevance scores, and produces a structured llms.txt file that helps LLMs understand your site.

## Features

- **Automated crawling** — BFS crawler with configurable depth (1-5) and page limit (50-500). Respects robots.txt, parses sitemaps, skips binary files, and rate-limits requests.
- **Live crawl visualization** — Real-time SSE (Server-Sent Events) feed showing each URL as it's crawled, with title, description, category badge, depth indicator, and relevance score.
- **Page categorization** — URL-pattern-based classification into categories like Documentation, API Reference, Guides, Getting Started, Examples, FAQ, Blog, etc.
- **Relevance scoring** — Heuristic scoring based on page category, crawl depth, URL path length, and sitemap presence.
- **LLM-powered generation** — Uses OpenAI (configurable model) to generate structured llms.txt with intelligent section grouping and descriptions. Falls back to a deterministic template generator when no API key is configured.
- **Version history** — Every generated llms.txt is versioned. View and diff previous generations.
- **Inline editing** — Edit the generated llms.txt directly in the browser with a Markdown editor.
- **Scheduled re-crawls** — Cron-based scheduling (via APScheduler) to automatically re-crawl sites on a recurring basis.
- **Change detection** — Content-hash-based change tracking across crawl runs. The "Changed" counter shows how many pages have new or modified content since the last crawl.
- **Advanced crawl configuration** — Configure max depth and max pages before each crawl via a collapsible settings panel.

## Tech Stack

### Backend
- **FastAPI** — Async Python web framework
- **SQLAlchemy 2.0** — Async ORM with asyncpg driver
- **PostgreSQL 16** — Primary datastore
- **Alembic** — Database migrations
- **httpx** — Async HTTP client for crawling
- **BeautifulSoup + lxml** — HTML parsing and metadata extraction
- **APScheduler** — Cron-based scheduled re-crawls
- **OpenAI SDK** — LLM-powered llms.txt generation

### Frontend
- **React 19** + **TypeScript**
- **Vite** — Build tooling
- **TanStack Query** — Server state management with automatic polling
- **Tailwind CSS** — Utility-first styling
- **CodeMirror** — Markdown editor for llms.txt editing
- **Nginx** — Static file serving + reverse proxy to backend

## Quick Start

### Prerequisites

- Docker and Docker Compose

### Running

```bash
# (Optional) Set OpenAI API key for LLM-powered generation
export LLMSTXT_OPENAI_KEY=sk-...

# Start all services
docker compose up -d --build

# Open in browser
open http://localhost:3000
```

The app will be available at `http://localhost:3000`. API docs at `http://localhost:8000/docs`.

### Local Development

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start PostgreSQL (via Docker)
docker compose up db -d

# Run migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --reload

# Start worker (separate terminal)
RUN_SCHEDULER=true python -m app.worker
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server proxies `/api` requests to `http://localhost:8000`.

### Resetting the Database

```bash
docker compose down -v   # -v removes the pgdata volume
docker compose up -d --build
```

### Configuration

Environment variables (set in `docker-compose.yml` or via `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLMSTXT_OPENAI_KEY` | _(empty)_ | OpenAI API key. If not set, falls back to template-based generation. |
| `LLM_MODEL` | `gpt-5.2` | OpenAI model to use for llms.txt generation. |
| `WORKER_ID` | `worker-1` | Unique identifier for the worker process. |
| `RUN_SCHEDULER` | `false` (API) / `true` (worker) | Whether to run the APScheduler cron loop. |
| `TASK_LEASE_SECONDS` | `60` | How long a worker lease lasts before expiry. |
| `TASK_MAX_ATTEMPTS` | `5` | Maximum retry attempts before dead-lettering a task. |

## How It Works

1. **Submit a URL** — The site is registered and a crawl task is enqueued
2. **Crawl** — The worker claims the task and performs a BFS traversal, respecting robots.txt and fetching sitemap.xml
3. **Extract** — Each page is parsed for title, description, headings, and OG tags
4. **Categorize** — URL-pattern heuristics assign categories (Documentation, API Reference, Guides, etc.) and compute relevance scores
5. **Generate** — llms.txt is assembled following the spec, with sections ordered by relevance
6. **Monitor** — Optional cron-based re-crawling detects content changes via SHA-256 hashes and regenerates

## Architecture

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Frontend │────▶│  Nginx   │────▶│ FastAPI  │     │ Worker   │
│  React   │     │  Proxy   │     │  (API)   │     │ Process  │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                                       │                 │
                                       │    ┌────────────┘
                                       ▼    ▼
                                  ┌──────────────┐
                                  │  PostgreSQL  │
                                  │   (pgdata)   │
                                  └──────────────┘
```

### Services

| Service | Role |
|---------|------|
| **frontend** | React SPA served via Nginx. Proxies `/api/` to the backend. |
| **backend** | FastAPI application. REST API, SSE streams, database management. Does not run crawl tasks directly. |
| **worker** | Separate Python process. Polls the task queue, executes crawl jobs, generates llms.txt, runs the APScheduler for cron re-crawls. |
| **db** | PostgreSQL 16. Stores sites, pages, crawl jobs, generated files, schedules, and the task queue. |

### Request Flow

1. User submits a URL via the frontend
2. Backend creates a `Site` and `CrawlJob` record, then enqueues a `CrawlTask` into the DB-backed task queue
3. Worker claims the task using `SELECT ... FOR UPDATE SKIP LOCKED`, sets a lease, and begins crawling
4. As each page is crawled, the worker inserts it into the `pages` table and updates the `crawl_jobs` row with progress counters
5. Frontend connects to the SSE endpoint (`GET /api/sites/{id}/crawl/{jobId}/stream`), which polls the DB every 1s for new pages and progress updates
6. When the crawl completes, the worker generates llms.txt (via LLM or template) and marks the job as completed
7. The SSE stream sends a terminal `completed` event and closes

### Why a Separate Worker Process?

The original architecture ran crawl jobs as `asyncio.create_task()` on the uvicorn event loop. This was simple but had real limitations:

| Concern | Old (in-process) | New (worker) |
|---------|-------------------|--------------|
| **Crash recovery** | Lost — if uvicorn restarted, in-flight crawls vanished | Automatic — lease expires, task is recovered and retried |
| **Retry logic** | None — a transient network error was a permanent failure | Exponential backoff, up to 5 retries with jitter |
| **Resource isolation** | Crawl tasks competed with API request handling on the same event loop | Worker runs in a separate process/container |
| **Horizontal scaling** | Single process only | Multiple workers with `FOR UPDATE SKIP LOCKED` claim semantics |
| **Observability** | No audit trail | Full task history: attempts, errors, lease owners, timestamps |
| **Restart tolerance** | `docker compose restart backend` killed active crawls | Worker keeps going independently |

### Why DB Polling for SSE Instead of Redis/In-Memory Pub/Sub?

The SSE endpoint polls the database every 1 second for new pages and progress updates. This replaces the original in-memory pub/sub (asyncio.Queue fanout). The trade-offs:

| | In-Memory Pub/Sub | DB Polling |
|---|---|---|
| Latency | ~instant | ~1s |
| Works across processes | No (API + worker must share memory) | Yes |
| Survives API restart | No | Yes (pages already persisted) |
| Replay completed crawls | Requires separate logic | Free — pages are already in the DB |
| Extra infrastructure | None (but tightly couples API and worker) | None |

DB polling was chosen because: (1) it works naturally with the separate worker process, (2) completed crawls can be replayed for free by querying stored pages, (3) the 1s latency is imperceptible when pages arrive every ~200ms+ anyway, and (4) it avoids adding Redis as another infrastructure dependency.

### Task Queue Design

The `crawl_tasks` table implements a durable task queue with the following guarantees:

- **Atomic claim** — `SELECT ... FOR UPDATE SKIP LOCKED` ensures exactly-once delivery even with multiple workers polling concurrently.
- **Lease-based ownership** — Each claimed task has a `leased_until` timestamp. The worker renews the lease every 10s via a heartbeat loop running as an `asyncio.Task`.
- **Automatic recovery** — The worker loop checks for expired leases on every poll cycle and moves stale tasks back to `failed` status for retry.
- **Idempotency** — Scheduled crawls use an idempotency key (`cron-{site_id}-{date}`) to prevent duplicate task creation when the scheduler fires.
- **Retry with backoff** — Failed tasks are retried with jittered exponential backoff: `15s * 2^(attempt-1) * (1 + random(0, 0.2))`.
- **Dead letter** — Tasks exceeding `max_attempts` (default 5) are moved to `dead_letter` status rather than retrying forever.
- **Row-level locking** — All task state transitions (claim, heartbeat, complete, fail, recover) use `FOR UPDATE SKIP LOCKED` to prevent race conditions between the worker and the recovery loop.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/sites` | Create a new site and start initial crawl |
| `GET` | `/api/sites` | List all sites |
| `GET` | `/api/sites/{id}` | Get site details |
| `DELETE` | `/api/sites/{id}` | Delete a site and all associated data |
| `POST` | `/api/sites/{id}/crawl` | Start a new crawl (accepts `max_depth`, `max_pages`) |
| `GET` | `/api/sites/{id}/crawl` | List crawl jobs for a site |
| `GET` | `/api/sites/{id}/crawl/{jobId}` | Get crawl job status |
| `GET` | `/api/sites/{id}/crawl/{jobId}/stream` | SSE stream of live crawl events |
| `GET` | `/api/sites/{id}/pages` | List crawled pages |
| `GET` | `/api/sites/{id}/llms-txt` | Get latest generated llms.txt |
| `PUT` | `/api/sites/{id}/llms-txt` | Update llms.txt content (manual edit) |
| `GET` | `/api/sites/{id}/llms-txt/history` | List all generated llms.txt versions |
| `PUT` | `/api/sites/{id}/schedule` | Create or update a crawl schedule |
| `GET` | `/api/sites/{id}/schedule` | Get current schedule |
| `DELETE` | `/api/sites/{id}/schedule` | Delete a schedule |

## Project Structure

```
profound_takehome/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, router registration
│   │   ├── config.py            # Pydantic settings (env vars)
│   │   ├── database.py          # Async SQLAlchemy engine + session factory
│   │   ├── worker.py            # Worker process entry point
│   │   ├── models/              # SQLAlchemy ORM models
│   │   │   ├── site.py
│   │   │   ├── page.py
│   │   │   ├── crawl_job.py
│   │   │   ├── crawl_task.py    # Task queue model
│   │   │   ├── generated_file.py
│   │   │   └── schedule.py
│   │   ├── routers/             # FastAPI route handlers
│   │   │   ├── sites.py
│   │   │   ├── crawl.py         # Crawl management + SSE stream
│   │   │   ├── pages.py
│   │   │   ├── llms_txt.py
│   │   │   └── schedules.py
│   │   ├── services/
│   │   │   ├── crawler.py       # BFS web crawler (httpx + asyncio)
│   │   │   ├── extractor.py     # HTML metadata extraction
│   │   │   ├── categorizer.py   # URL-based page categorization + relevance
│   │   │   ├── generator.py     # Template-based llms.txt generation
│   │   │   ├── llm_generator.py # LLM-powered llms.txt generation
│   │   │   ├── task_queue.py    # DB-backed task queue operations
│   │   │   └── scheduler.py     # APScheduler integration
│   │   ├── tasks/
│   │   │   └── crawl_task.py    # Crawl job execution pipeline
│   │   └── schemas/             # Pydantic request/response schemas
│   ├── alembic/                 # Database migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/client.ts        # Typed API client (axios)
│   │   ├── hooks/
│   │   │   └── useCrawlStream.ts# SSE EventSource React hook
│   │   ├── components/
│   │   │   ├── UrlInput.tsx
│   │   │   ├── CrawlVisualization.tsx  # Live crawl feed
│   │   │   ├── CrawlConfigPanel.tsx    # Advanced crawl settings
│   │   │   ├── LlmsTxtViewer.tsx
│   │   │   └── SchedulePanel.tsx
│   │   └── pages/
│   │       ├── HomePage.tsx
│   │       └── SitePage.tsx
│   ├── nginx.conf
│   ├── package.json
│   └── Dockerfile
└── docker-compose.yml
```
