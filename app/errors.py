from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError


class ServiceUnavailableError(RuntimeError):
    """Raised when storage is unavailable or cannot complete a request."""


def structured_error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


async def service_unavailable_handler(_: Request, exc: ServiceUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=structured_error("DATABASE_UNAVAILABLE", str(exc) or "Database unavailable"),
    )


async def sqlalchemy_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=structured_error("DATABASE_UNAVAILABLE", "Database unavailable"),
    )


async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content=structured_error("HTTP_ERROR", str(exc.detail)))


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=structured_error("INTERNAL_ERROR", "Unexpected server error"),
    )
