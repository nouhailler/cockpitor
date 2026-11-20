import asyncio

from fastapi import APIRouter, Query
from fastapi.responses import Response


def create_router(app):
    router = APIRouter()
    # Two reads at once, never an unbounded queue of worker threads.
    gate = asyncio.Semaphore(2)

    async def read(function, *args):
        from ..services import ServiceError

        if gate.locked():
            raise ServiceError("FILES_BUSY", "Lecture de fichiers occupée ; réessayez", 429)
        async with gate:
            # Await the worker even on cancellation: do not release its admission slot early.
            task = asyncio.create_task(asyncio.to_thread(function, *args))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise

    @router.get("/api/v1/files/options")
    def options():
        return app.state.files.options()

    @router.get("/api/v1/files")
    async def listing(
        root: str = Query(max_length=32),
        path: str = Query("", max_length=1024),
        q: str = Query("", max_length=100),
    ):
        return await read(app.state.files.listing, root, path, q)

    @router.get("/api/v1/files/preview")
    async def preview(root: str = Query(max_length=32), path: str = Query(max_length=1024)):
        return await read(app.state.files.read, root, path, True)

    @router.get("/api/v1/files/download")
    async def download(root: str = Query(max_length=32), path: str = Query(max_length=1024)):
        content = await read(app.state.files.read, root, path)
        return Response(
            content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": 'attachment; filename="cockpitor-file.bin"'},
        )

    return router
