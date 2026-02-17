import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import crawl, generate, pages, schedules, sites
from app.services.scheduler import load_schedules_from_db, scheduler

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    await load_schedules_from_db()
    yield
    scheduler.shutdown()


app = FastAPI(title="llms.txt Generator", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sites.router)
app.include_router(crawl.router)
app.include_router(pages.router)
app.include_router(generate.router)
app.include_router(schedules.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
