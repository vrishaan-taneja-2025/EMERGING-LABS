
from fastapi import Depends, HTTPException,Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from app.core.security import SECRET_KEY

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def require_roles(*roles):
    def checker(request: Request):
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401)

        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload["role"] not in roles:
            raise HTTPException(status_code=403)

        return payload
    return checker