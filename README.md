# llms.txt Generator

Automated [llms.txt](https://llmstxt.org/) generator for any website. Crawls a site, extracts metadata, categorizes pages, and assembles the result into the llms.txt Markdown format. Supports monitoring for changes and automatic regeneration.

## Stack

- **Backend API**: FastAPI (Python) + SQLAlchemy + PostgreSQL
- **Worker**: Dedicated async worker process for durable crawl task execution
- **Frontend**: React + Vite + TypeScript + Tailwind CSS
- **Infrastructure**: Docker Compose

## Queue/Worker Architecture (Feature A)

- API requests create `crawl_jobs` and enqueue durable `crawl_tasks` in Postgres.
- Worker claims tasks with `FOR UPDATE SKIP LOCKED`.
- Worker uses leased execution with heartbeat renewal.
- Failures retry with exponential backoff; terminal failures move to `dead_letter`.
- Scheduler runs in worker only and enqueues tasks (no in-process API crawling).

## Local Quick Start (Feature A ports)

Use the dedicated env file and compose project name to avoid conflicts with other local agents.

```bash
cp .env.featurea.example .env.featurea
docker compose --env-file .env.featurea -p featurea_spike up --build
```

- Frontend: http://localhost:3011
- Backend API: http://localhost:8011
- API docs: http://localhost:8011/docs
- Postgres host port: `5434`

Stop stack:

```bash
docker compose --env-file .env.featurea -p featurea_spike down
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/sites` | Submit URL, create site + enqueue crawl |
| GET | `/api/sites` | List all sites |
| GET | `/api/sites/{id}` | Get site details |
| DELETE | `/api/sites/{id}` | Delete site (cascade) |
| POST | `/api/sites/{id}/crawl` | Enqueue re-crawl |
| GET | `/api/sites/{id}/crawl/{job_id}` | Poll crawl progress |
| GET | `/api/sites/{id}/pages` | List discovered pages |
| GET | `/api/sites/{id}/llms-txt` | Get latest llms.txt |
| PUT | `/api/sites/{id}/llms-txt` | Save user edits |
| GET | `/api/sites/{id}/llms-txt/download` | Download as file |
| GET | `/api/sites/{id}/llms-txt/history` | Version history |
| PUT | `/api/sites/{id}/schedule` | Create/update schedule |
| GET | `/api/sites/{id}/schedule` | Get schedule |
| DELETE | `/api/sites/{id}/schedule` | Remove schedule |

## Reliability behaviors added

- **Durability**: tasks persist in Postgres; API restarts do not drop work.
- **Crash recovery**: expired leases are recycled and retried.
- **Retry control**: exponential backoff + max attempts.
- **Dead-letter state**: exhausted tasks are visible and auditable.

## Railway deployment shape

- Service A: API (`uvicorn app.main:app`)
- Service B: Worker (`python -m app.worker`)
- Service C: Managed Postgres

Same repo, separate start commands, no external broker required.
