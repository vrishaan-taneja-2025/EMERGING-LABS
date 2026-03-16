from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext

from app.db.session import get_db
from app.models.user import User
from app.models.role import Role
from app.core.auth_guard import require_user,admin_required
from app.core.security import hash_password

router = APIRouter(prefix="/users", tags=["Users"])
templates = Jinja2Templates(directory="app/templates")



# -------------------------
# LIST USERS
# -------------------------
@router.get("/")
def list_users(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    
    guard = admin_required(request, user)
    if guard:
        return guard
    

    users = db.query(User).all()
    roles = db.query(Role).all()

    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "users": users,
            "roles": roles,
            "user": user,
        }
    )

# -------------------------
# CREATE USER
# -------------------------
@router.post("/create")
def create_user(
    username: str = Form(...),
    password: str = Form(...),
    role_id: int = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(400, "Username already exists")

    new_user = User(
        username=username,
        password_hash=hash_password(password),
        role_id=role_id
    )
    db.add(new_user)
    db.commit()

    return RedirectResponse("/users", status_code=302)

# -------------------------
# UPDATE USER
# -------------------------
@router.post("/edit/{user_id}")
def edit_user(
    user_id: int,
    role_id: int = Form(...),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")

    u.role_id = role_id
    u.is_active = is_active
    db.commit()

    return RedirectResponse("/users", status_code=302)

# -------------------------
# DELETE USER
# -------------------------
@router.get("/delete/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")

    db.delete(u)
    db.commit()

    return RedirectResponse("/users", status_code=302)