from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.exceptions import HTTPException

def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in (401, 403):
        response = RedirectResponse("/dashboard", status_code=302)
        response.set_cookie(
            "flash_error",
            "Unauthorized access.",
            max_age=5
        )
        return response
    raise exc