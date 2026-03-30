from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import jwt
from app.core.auth_guard import require_user
from app.core.security import SECRET_KEY

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {"request": request})


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
        request,
        "login.html",
        {"request": request, "error": error}
    )



@router.get("/register")
def register_page(request: Request):
    
    return templates.TemplateResponse(
        request,
        "register_public.html",
        {"request": request}
    )


@router.get("/tableau-dashboard")
def tableau_dashboard(request: Request, user=Depends(require_user)):
    return templates.TemplateResponse(
        request,
        "tableau_dashboard.html",
        {
            "request": request,
            "user": user,
            "tableau_api_base": "/api/tableau",
        },
    )

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
