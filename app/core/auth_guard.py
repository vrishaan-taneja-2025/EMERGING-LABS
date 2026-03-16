from fastapi import HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from jose import jwt
from app.core.security import ALGORITHM, SECRET_KEY
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User


def login_required(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse("/login?error=login_required", status_code=302)
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            return RedirectResponse("/login?error=login_required", status_code=302)

        # Fetch the actual user object from DB
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return RedirectResponse("/login?error=login_required", status_code=302)

        request.state.user = user  # ✅ set the actual User ORM object

    except Exception:
        return RedirectResponse("/login?error=login_required", status_code=302)

    return None  # means login is valid

def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse("/login?error=login_required", status_code=302)

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
    except Exception:
        return RedirectResponse("/login?error=login_required", status_code=302)

    user = db.query(User).filter(User.username == username).first()
    if not user:
        return RedirectResponse("/login?error=login_required", status_code=302)

    return user

def require_user(user=Depends(get_current_user)):
    if isinstance(user, RedirectResponse):
        return user
    return user


def admin_required(request: Request, user: User = Depends(get_current_user)):
    if not user.role or user.role.name.lower() != "admin":
        response = RedirectResponse("/dashboard", status_code=302)
        response.set_cookie(
            key="flash_error",
            value="Unauthorized access",
            max_age=5
        )
        return response
    return None

def manager_required(request: Request, user: User = Depends(get_current_user)):
    if not user.role or user.role.name.lower() != "manager":
        response = RedirectResponse("/dashboard", status_code=302)
        response.set_cookie(
            key="flash_error",
            value="Unauthorized access",
            max_age=5
        )
        return response
    return None