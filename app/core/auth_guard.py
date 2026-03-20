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


def get_user_role_name(user: User | None) -> str:
    if isinstance(user, RedirectResponse):
        return ""
    if not user or not hasattr(user, "role") or not user.role or not user.role.name:
        return ""
    return user.role.name.strip().lower()


def ensure_user_has_role(user: User, *allowed_roles: str):
    if isinstance(user, RedirectResponse):
        raise HTTPException(401, "Login required")
    role_name = get_user_role_name(user)
    normalized_roles = {role.strip().lower() for role in allowed_roles}
    if role_name not in normalized_roles:
        allowed_text = ", ".join(sorted(normalized_roles))
        raise HTTPException(403, f"Only {allowed_text} can perform this action")


def admin_required(request: Request, user: User = Depends(get_current_user)):
    if get_user_role_name(user) != "admin":
        response = RedirectResponse("/dashboard", status_code=302)
        response.set_cookie(
            key="flash_error",
            value="Unauthorized access",
            max_age=5
        )
        return response
    return None

def manager_required(request: Request, user: User = Depends(get_current_user)):
    if get_user_role_name(user) != "manager":
        response = RedirectResponse("/dashboard", status_code=302)
        response.set_cookie(
            key="flash_error",
            value="Unauthorized access",
            max_age=5
        )
        return response
    return None
