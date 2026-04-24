"""
API 路由 - 认证
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import time

from database import get_db
from models import User, AuditLog
from security import verify_password, create_access_token, decode_token, get_password_hash
from config import settings

router = APIRouter(prefix="/api/auth", tags=["认证"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    username: str
    is_admin: bool


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    if not payload:
        raise credentials_exception
    username = payload.get("sub")
    if not username:
        raise credentials_exception
    
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise credentials_exception
    return user


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        # 记录失败日志
        log = AuditLog(
            action="login_failed",
            detail=f"用户名: {form_data.username}",
            ip_address=request.client.host if request.client else None,
            user_id=user.id if user else 1,
        )
        db.add(log)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    
    # 更新最后登录时间
    await db.execute(update(User).where(User.id == user.id).values(last_login=time.time()))
    
    # 记录登录日志
    log = AuditLog(
        action="login",
        detail="登录成功",
        ip_address=request.client.host if request.client else None,
        user_id=user.id,
    )
    db.add(log)
    
    token = create_access_token({"sub": user.username})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        username=user.username,
        is_admin=user.is_admin,
    )


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "created_at": current_user.created_at,
        "last_login": current_user.last_login,
    }


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(req.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="旧密码错误")
    
    await db.execute(
        update(User)
        .where(User.id == current_user.id)
        .values(hashed_password=get_password_hash(req.new_password))
    )
    return {"message": "密码修改成功"}


@router.get("/users", dependencies=[Depends(get_admin_user)])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "is_admin": u.is_admin,
            "is_active": u.is_active,
            "created_at": u.created_at,
            "last_login": u.last_login,
        }
        for u in users
    ]


@router.post("/users", dependencies=[Depends(get_admin_user)])
async def create_user(
    username: str,
    password: str,
    is_admin: bool = False,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    user = User(
        username=username,
        hashed_password=get_password_hash(password),
        is_admin=is_admin,
    )
    db.add(user)
    await db.flush()
    return {"id": user.id, "username": user.username}
