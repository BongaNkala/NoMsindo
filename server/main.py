from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from . import api, licensing, portal
from .config import Settings
from .models import Base

HERE = Path(__file__).parent


def create_app(data_dir=None, database_url=None) -> FastAPI:
    settings = Settings.load(data_dir, database_url)
    app = FastAPI(title="NoMsindo Admin", docs_url=None, redoc_url=None, openapi_url=None)
    engine = create_engine(settings.database_url,
                           connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {})
    Base.metadata.create_all(engine)
    app.state.settings = settings
    app.state.SessionLocal = sessionmaker(engine, expire_on_commit=False)
    app.state.private_key = licensing.load_or_create_private_key(settings.data_dir)

    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax",
                       https_only=settings.cookie_secure, max_age=8 * 3600)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; "
                                                   "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        return resp

    @app.exception_handler(portal.NeedLogin)
    async def need_login(request: Request, exc):
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "http_error", "message": str(exc.detail)}, status_code=exc.status_code)
        return portal.templates.TemplateResponse(request, "error.html", {
            "user": None, "status": exc.status_code, "message": exc.detail, "flash": None, "csrf": ""},
            status_code=exc.status_code)

    @app.get("/api/v1/public-key", response_class=PlainTextResponse)
    def public_key(request: Request):
        return licensing.public_pem(request.app.state.private_key).decode()

    @app.get("/healthz", response_class=PlainTextResponse)
    def healthz():
        return "ok"

    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    app.include_router(api.router)
    app.include_router(portal.router)
    return app


def app_factory() -> FastAPI:  # uvicorn --factory server.main:app_factory
    return create_app()
