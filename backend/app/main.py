import logging

from fastapi import FastAPI, Request, Response
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


@app.middleware("http")
async def no_cache_api(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

app.include_router(sites.router)
app.include_router(crawl.router)
app.include_router(pages.router)
app.include_router(generate.router)
app.include_router(schedules.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
