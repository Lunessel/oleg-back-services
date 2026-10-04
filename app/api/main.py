from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    settings.media_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="oleg-back-services")
    app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
