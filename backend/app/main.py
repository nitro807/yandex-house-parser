from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import ParseRequest, ParseResult
from .parser import ParserError, YandexHouseParser


parser = YandexHouseParser()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await parser.stop()


app = FastAPI(title="Организации в доме", version="0.1.0", lifespan=lifespan)
origins = [value.strip() for value in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if value.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/parse", response_model=ParseResult)
async def parse_house(request: ParseRequest) -> ParseResult:
    try:
        return await parser.parse(str(request.url))
    except ParserError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Не удалось обработать ссылку Яндекс Карт") from exc
