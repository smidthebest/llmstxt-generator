import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import crawl, generate, pages, schedules, sites

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="llms.txt Generator", version="0.1.0")

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
