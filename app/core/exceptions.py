from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class BadRequestException(AppException):
    def __init__(self, message: str = "Bad request.", details: Any | None = None) -> None:
        super().__init__(400, "BAD_REQUEST", message, details)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Unauthorized.", details: Any | None = None) -> None:
        super().__init__(401, "UNAUTHORIZED", message, details)


class ForbiddenException(AppException):
    def __init__(self, message: str = "Forbidden.", details: Any | None = None) -> None:
        super().__init__(403, "FORBIDDEN", message, details)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found.", details: Any | None = None) -> None:
        super().__init__(404, "NOT_FOUND", message, details)


class ConflictException(AppException):
    def __init__(self, message: str = "Resource conflict.", details: Any | None = None) -> None:
        super().__init__(409, "CONFLICT", message, details)


def _error_response(status_code: int, code: str, message: str, details: Any | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({"code": code, "message": message, "details": details}),
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            422,
            "VALIDATION_ERROR",
            "Request validation failed.",
            exc.errors(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        code = "HTTP_ERROR"
        if exc.status_code == 401:
            code = "UNAUTHORIZED"
        elif exc.status_code == 403:
            code = "FORBIDDEN"
        elif exc.status_code == 404:
            code = "NOT_FOUND"
        return _error_response(exc.status_code, code, str(exc.detail), None)
