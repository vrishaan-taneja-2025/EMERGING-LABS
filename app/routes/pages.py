from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from app.core.auth_guard import login_required, require_user
from app.core.security import create_token, hash_password
from jose import jwt
from app.core.security import SECRET_KEY
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.equipment import Equipment
from app.models.user import User
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@router.get("/login")
def login_page(request: Request, error: str | None = None):
    token = request.cookies.get("access_token")
    if token:
        try:
            jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            return RedirectResponse("/dashboard")
        except:
            pass

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": error}
    )



@router.get("/register")
def register_page(request: Request):
    
    return templates.TemplateResponse(
        "register_public.html",
        {"request": request}
    )


@router.get("/dashboard")
def dashboard(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    
    current_user = getattr(request.state, "user", None)
    if not current_user:
        return RedirectResponse("/login?error=login_required", status_code=302)

    flash_message = request.cookies.get("flash_success")
    equipments = db.query(Equipment).all()
    response = templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "equipments": equipments,
            "flash_success": flash_message
        }
    )

    # ❗ Clear flash after reading
    if flash_message:
        response.delete_cookie("flash_success")

    return response

@router.get("/logout")
def logout():
    response = RedirectResponse(
        url="/login",
        status_code=302
    )

    # ❌ Remove JWT
    response.delete_cookie("access_token")

    # 🔔 Flash message (optional)
    response.set_cookie(
        key="flash_error",
        value="Logged out successfully",
        max_age=5
    )

    return response


# @router.get("/equipments")
# def equipments(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
#     equipments = db.query(Equipment).all()
#     return templates.TemplateResponse("equipments.html", {
#         "request": request,
#         "user": user,
#         "equipments": equipments
#     })