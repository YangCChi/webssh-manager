"""
API 路由 - 服务器管理
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
import time

from database import get_db
from models import Server, ServerGroup
from security import encrypt_secret, decrypt_secret
from routers.auth import get_current_user
from models import User

router = APIRouter(prefix="/api/servers", tags=["服务器管理"])


class ServerCreate(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str
    auth_type: str = "password"
    password: Optional[str] = None
    private_key: Optional[str] = None
    private_key_passphrase: Optional[str] = None
    proxy_enabled: bool = False
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None
    group_id: Optional[int] = None
    tags: str = ""
    notes: str = ""


class ServerUpdate(ServerCreate):
    pass


class GroupCreate(BaseModel):
    name: str
    color: str = "#409EFF"


def server_to_dict(s: Server, include_credentials: bool = False) -> dict:
    d = {
        "id": s.id,
        "name": s.name,
        "host": s.host,
        "port": s.port,
        "username": s.username,
        "auth_type": s.auth_type,
        "proxy_enabled": s.proxy_enabled,
        "proxy_host": s.proxy_host,
        "proxy_port": s.proxy_port,
        "proxy_username": s.proxy_username,
        "group_id": s.group_id,
        "tags": s.tags,
        "notes": s.notes,
        "is_favorite": s.is_favorite,
        "last_connected": s.last_connected,
        "connect_count": s.connect_count,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }
    return d


@router.get("/groups")
async def list_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ServerGroup).where(ServerGroup.user_id == current_user.id)
    )
    groups = result.scalars().all()
    return [{"id": g.id, "name": g.name, "color": g.color, "sort_order": g.sort_order} for g in groups]


@router.post("/groups")
async def create_group(
    req: GroupCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = ServerGroup(name=req.name, color=req.color, user_id=current_user.id)
    db.add(group)
    await db.flush()
    return {"id": group.id, "name": group.name, "color": group.color}


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(ServerGroup).where(
            ServerGroup.id == group_id, ServerGroup.user_id == current_user.id
        )
    )
    return {"message": "分组已删除"}


@router.get("")
async def list_servers(
    group_id: Optional[int] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Server).where(Server.owner_id == current_user.id)
    if group_id is not None:
        query = query.where(Server.group_id == group_id)
    if search:
        from sqlalchemy import or_
        query = query.where(
            or_(
                Server.name.contains(search),
                Server.host.contains(search),
                Server.tags.contains(search),
            )
        )
    query = query.order_by(Server.is_favorite.desc(), Server.sort_order, Server.name)
    result = await db.execute(query)
    servers = result.scalars().all()
    return [server_to_dict(s) for s in servers]


@router.post("")
async def create_server(
    req: ServerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    server = Server(
        name=req.name,
        host=req.host,
        port=req.port,
        username=req.username,
        auth_type=req.auth_type,
        encrypted_password=encrypt_secret(req.password or ""),
        encrypted_private_key=encrypt_secret(req.private_key or ""),
        private_key_passphrase=encrypt_secret(req.private_key_passphrase or ""),
        proxy_enabled=req.proxy_enabled,
        proxy_host=req.proxy_host,
        proxy_port=req.proxy_port,
        proxy_username=req.proxy_username,
        proxy_encrypted_password=encrypt_secret(req.proxy_password or ""),
        group_id=req.group_id,
        tags=req.tags,
        notes=req.notes,
        owner_id=current_user.id,
    )
    db.add(server)
    await db.flush()
    return server_to_dict(server)


@router.put("/{server_id}")
async def update_server(
    server_id: int,
    req: ServerUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Server).where(Server.id == server_id, Server.owner_id == current_user.id)
    )
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")
    
    server.name = req.name
    server.host = req.host
    server.port = req.port
    server.username = req.username
    server.auth_type = req.auth_type
    if req.password is not None:
        server.encrypted_password = encrypt_secret(req.password)
    if req.private_key is not None:
        server.encrypted_private_key = encrypt_secret(req.private_key)
    if req.private_key_passphrase is not None:
        server.private_key_passphrase = encrypt_secret(req.private_key_passphrase)
    server.proxy_enabled = req.proxy_enabled
    server.proxy_host = req.proxy_host
    server.proxy_port = req.proxy_port
    server.proxy_username = req.proxy_username
    if req.proxy_password is not None:
        server.proxy_encrypted_password = encrypt_secret(req.proxy_password)
    server.group_id = req.group_id
    server.tags = req.tags
    server.notes = req.notes
    server.updated_at = time.time()
    
    return server_to_dict(server)


@router.delete("/{server_id}")
async def delete_server(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(Server).where(Server.id == server_id, Server.owner_id == current_user.id)
    )
    return {"message": "服务器已删除"}


@router.post("/{server_id}/favorite")
async def toggle_favorite(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Server).where(Server.id == server_id, Server.owner_id == current_user.id)
    )
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")
    server.is_favorite = not server.is_favorite
    return {"is_favorite": server.is_favorite}


@router.get("/{server_id}/connection-info")
async def get_connection_info(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """获取服务器连接信息（含解密后的凭据，仅内部使用）"""
    result = await db.execute(
        select(Server).where(Server.id == server_id, Server.owner_id == current_user.id)
    )
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")
    
    return {
        "host": server.host,
        "port": server.port,
        "username": server.username,
        "auth_type": server.auth_type,
        "encrypted_password": server.encrypted_password,
        "encrypted_private_key": server.encrypted_private_key,
        "private_key_passphrase": server.private_key_passphrase,
        "proxy_enabled": server.proxy_enabled,
        "proxy_host": server.proxy_host,
        "proxy_port": server.proxy_port,
        "proxy_username": server.proxy_username,
        "proxy_encrypted_password": server.proxy_encrypted_password,
        "keepalive_hours": 24,
    }
