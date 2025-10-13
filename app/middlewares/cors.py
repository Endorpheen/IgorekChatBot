from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.settings import Settings


def setup_cors(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_origin_regex=settings.allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
