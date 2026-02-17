# llms.txt Generator

Automated [llms.txt](https://llmstxt.org/) generator for any website. Crawls a site, extracts metadata, categorizes pages, and assembles the result into the llms.txt Markdown format. Supports monitoring for changes and automatic regeneration.

## Stack

- **Backend**: FastAPI (Python) + SQLAlchemy + PostgreSQL
- **Frontend**: React + Vite + TypeScript + Tailwind CSS
- **Infrastructure**: Docker Compose

## Quick Start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

## Local Development

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start PostgreSQL (via Docker or locally)
docker compose up db -d

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server proxies `/api` requests to `http://localhost:8000`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/sites` | Submit URL, create site + start crawl |
| GET | `/api/sites` | List all sites |
| GET | `/api/sites/{id}` | Get site details |
| DELETE | `/api/sites/{id}` | Delete site (cascade) |
| POST | `/api/sites/{id}/crawl` | Trigger re-crawl |
| GET | `/api/sites/{id}/crawl/{job_id}` | Poll crawl progress |
| GET | `/api/sites/{id}/pages` | List discovered pages |
| GET | `/api/sites/{id}/llms-txt` | Get latest llms.txt |
| PUT | `/api/sites/{id}/llms-txt` | Save user edits |
| GET | `/api/sites/{id}/llms-txt/download` | Download as file |
| GET | `/api/sites/{id}/llms-txt/history` | Version history |
| PUT | `/api/sites/{id}/schedule` | Create/update schedule |
| GET | `/api/sites/{id}/schedule` | Get schedule |
| DELETE | `/api/sites/{id}/schedule` | Remove schedule |

## How It Works

1. **Submit a URL** - The site is registered and a crawl begins automatically
2. **Crawl** - BFS traversal (max depth 3, max 200 pages), respects robots.txt, fetches sitemap.xml
3. **Extract** - Parses HTML for title, description, headings, and OG tags
4. **Categorize** - URL-pattern heuristics assign categories (Documentation, API Reference, Guides, etc.) and relevance scores
5. **Generate** - Assembles llms.txt following the spec with ordered sections
6. **Monitor** - Optional cron-based re-crawling detects changes via content hashes and regenerates

## Architecture

```
Frontend (React) → Nginx → Backend (FastAPI) → PostgreSQL
                              ↓
                         Crawler (httpx async)
                         Extractor (BeautifulSoup)
                         Categorizer (URL heuristics)
                         Generator (Markdown assembly)
                         Scheduler (APScheduler)
```
