from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates

from app.db.session import get_db
from app.models.role import Role
from app.core.auth_guard import require_user

router = APIRouter(prefix="/roles", tags=["Roles"])
templates = Jinja2Templates(directory="app/templates")


# -------------------------
# List Roles
# -------------------------
@router.get("/")
def list_roles(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    search = request.query_params.get("search", "")
    page = int(request.query_params.get("page", 1))
    per_page = 10

    query = db.query(Role)
    if search:
        query = query.filter(Role.name.ilike(f"%{search}%"))

    total = query.count()
    roles = query.offset((page - 1) * per_page).limit(per_page).all()

    return templates.TemplateResponse(
        "roles.html",
        {
            "request": request,
            "user": user,
            "roles": roles,
            "page": page,
            "per_page": per_page,
            "total": total,
            "search": search,
        },
    )


# -------------------------
# Create Role
# -------------------------
@router.post("/create")
def create_role(
    name: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    if db.query(Role).filter(Role.name == name).first():
        raise HTTPException(status_code=400, detail="Role already exists")

    role = Role(name=name)
    db.add(role)
    db.commit()

    return RedirectResponse("/roles", status_code=302)


# -------------------------
# Edit Role
# -------------------------
@router.post("/edit/{role_id}")
def edit_role(
    role_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    role.name = name
    db.commit()

    return RedirectResponse("/roles", status_code=302)


# -------------------------
# Delete Role
# -------------------------
@router.get("/delete/{role_id}")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.users:
        raise HTTPException(
            status_code=400,
            detail="Role is assigned to users and cannot be deleted",
        )

    db.delete(role)
    db.commit()

    return RedirectResponse("/roles", status_code=302)
