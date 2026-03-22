from app.core.security import create_token, verify_password, hash_password
from fastapi.responses import RedirectResponse
from fastapi import APIRouter, Depends, Form, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.role import Role
from app.models.user import User


router = APIRouter(prefix="/auth")

@router.post("/login")
def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()

    if (
        not user
        or not user.is_active
        or not user.role
        or not verify_password(password, user.password_hash)
    ):
        response = RedirectResponse(
            url="/login?error=invalid_credentials",
            status_code=status.HTTP_302_FOUND
        )
        response.set_cookie(
            key="flash_error",
            value="Invalid username or password",
            max_age=5
        )
        return response
    # ✅ Create JWT
    token = create_token({
        "sub": user.username,
        "role": user.role.name
    })

    # ✅ Redirect to dashboard
    response = RedirectResponse(
        url="/dashboard",
        status_code=status.HTTP_302_FOUND
    )

    # JWT cookie
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax"
    )

    # 🔔 Flash success message
    response.set_cookie(
        key="flash_success",
        value="Login successful",
        max_age=5  
        # seconds
    )

    return response




@router.post("/register")
def register_user(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    
    
    # 1️⃣ Check if user already exists
    existing_user = (
        db.query(User)
        .filter(User.username == username)
        .first()
    )

    if existing_user:
        response = RedirectResponse(
            url="/register",
            status_code=status.HTTP_302_FOUND
        )
        response.set_cookie(
            key="flash_error",
            value="Username already exists",
            max_age=5
        )
        return response

    # 2️⃣ Hash password
    hashed_password = hash_password(password) 
    role_user = (
        db.query(Role)
        .filter(func.lower(Role.name) == "user")
        .first()
    )
    if not role_user:
        response = RedirectResponse(
            url="/register",
            status_code=status.HTTP_302_FOUND
        )
        response.set_cookie(
            key="flash_error",
            value="Default user role is not configured",
            max_age=5
        )
        return response
    # 3️⃣ Create user (default role = user)
    user = User(
        username=username,
        password_hash=hashed_password,
        role_id=role_user.id,
        is_active=True
    )

    # 4️⃣ Save to DB
    db.add(user)
    db.commit()
    db.refresh(user)

    # 5️⃣ CREATE JWT (AUTO LOGIN)
    token = create_token({
        "sub": user.username,
        "role": user.role.name
    })

    # 6️⃣ Redirect to dashboard with JWT cookie
    response = RedirectResponse(
        url="/dashboard",
        status_code=status.HTTP_302_FOUND
    )
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax"
    )

    return response
