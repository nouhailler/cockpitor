import secrets

from fastapi.responses import JSONResponse

from .i18n import translate


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": translate(message),
                "correlation_id": secrets.token_hex(8),
            }
        },
        status_code=status,
    )
