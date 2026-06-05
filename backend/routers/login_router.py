# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models import User

login_router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    email: str
    password: str

@login_router.post("/login")
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(User).where(User.email == payload.email)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    if user.password != payload.password:
        raise HTTPException(status_code=401, detail="Wrong password")

    return {
        "id":       user.id,
        "name":     user.name,
        "email":    user.email,
        "username": user.username,
        "role":     user.role,
    }