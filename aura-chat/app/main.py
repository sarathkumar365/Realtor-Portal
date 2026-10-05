"""ASGI entrypoint. `uvicorn app.main:app`."""

import logging
import sys
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import container as container_mod
from app.api import router
from app.chat import router as chat_router
from app.config import Settings, load
from app.conversations import router as conversations_router
from app.feedback import router as feedback_router
from app.limits import Limits


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the container on startup -- unless one was injected.

    Tests set app.state.container before the app starts; building over it here
    would silently replace their fakes with real adapters reading the real
    environment, which is a confusing way to discover you have no .env file.
    Whoever supplied the container owns closing it.
    """
    owned = getattr(app.state, "container", None) is None
    if owned:
        app.state.container = container_mod.build()
    try:
        yield
    finally:
        if owned:
            await app.state.container.aclose()


def configure_logging() -> None:
    """Make this service's own log lines actually appear.

    uvicorn configures the `uvicorn*` loggers and nothing else, so `aura.*`
    propagated to a handler-less root and logging.lastResort dropped it -- that
    handler only emits WARNING and above.
    """
    log = logging.getLogger("aura")
    if log.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
        )
    )
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI app.

    Settings arrive here as well as in the container because CORS is middleware:
    it has to be registered while the app is being constructed, and the container
    is not built until startup. Passing them in also lets a test pin an origin
    list instead of inheriting whatever .env happens to say.
    """
    cfg = settings or load()
    configure_logging()
    app = FastAPI(title="Aura Chat", version="0.1.0", lifespan=lifespan)
    # allow_credentials stays False: the token travels in the Authorization
    # header, never a cookie, so credentialed CORS buys nothing -- and with it
    # off, a mistake in the list cannot hand a third-party page a live session.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.origins,
        allow_origin_regex=cfg.allowed_origin_regex or None,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-Id", "Retry-After"],
    )
    app.state.limits = Limits(
        chat=cfg.chat_per_hour, login=cfg.login_per_hour, doctor=cfg.doctor_per_hour
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        """One short id per request, on state and on the way out."""
        rid = uuid.uuid4().hex[:12]
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    app.include_router(router)
    app.include_router(chat_router)
    app.include_router(feedback_router)
    app.include_router(conversations_router)
    return app


app = create_app()
