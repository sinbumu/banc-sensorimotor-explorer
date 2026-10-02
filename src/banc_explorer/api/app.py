"""FastAPI adapter; one local graph worker, no hosted service or accounts."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from banc_explorer.api.service import BusyError, ExplorerService, Kind, PathRequest
from banc_explorer.config import Settings


def create_app(settings: Settings, output: Path, *, offline=False, service=None) -> FastAPI:
    service = service or ExplorerService(settings, output, offline=offline)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            service.start()
            yield
        finally:
            service.close()

    app = FastAPI(title="BANC local explorer", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.service = service
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.middleware("http")
    async def local_request(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
            return JSONResponse(
                {"detail": "Cross-origin requests are not supported."}, status_code=403
            )
        if request.method == "POST":
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "Expected application/json."}, status_code=415)
            length = request.headers.get("content-length", "")
            if not length.isdecimal():
                return JSONResponse(
                    {"detail": "A Content-Length header is required."}, status_code=411
                )
            if int(length) > 4096:
                return JSONResponse({"detail": "Request body exceeds 4 KiB."}, status_code=413)
            if len(await request.body()) > 4096:
                return JSONResponse({"detail": "Request body exceeds 4 KiB."}, status_code=413)
        return await call_next(request)

    @app.get("/health")
    def health():
        return service.health()

    @app.get("/metadata/facets")
    def facets():
        return service.facets()

    @app.get("/neurons/search")
    def search(
        kind: Kind,
        q: Annotated[str, Query(max_length=120)] = "",
        body_part: Annotated[str | None, Query(max_length=120)] = None,
        proofread_only: bool = True,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        return service.search(kind, q.strip(), body_part, proofread_only, limit, offset)

    @app.post("/paths", status_code=202)
    def paths(body: PathRequest):
        try:
            return service.submit(body)
        except BusyError as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/paths/{job_id}")
    def path_status(job_id: str):
        try:
            return service.get_job(job_id)
        except KeyError:
            raise HTTPException(
                404, "Unknown job. Server job history is limited to the last 32 jobs."
            ) from None

    return app
