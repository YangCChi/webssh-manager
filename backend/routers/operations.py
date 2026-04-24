"""
API 路由 - 运维工具（快捷命令、批量命令、操作日志）
"""
import asyncio
import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, desc

from config import settings
from database import get_db
from models import CommandSnippet, AuditLog, User, TerminalSession
from routers.auth import get_current_user
from ssh_manager import session_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["运维工具"])


# ===== 常用命令 =====

class SnippetCreate(BaseModel):
    name: str
    command: str
    description: str = ""
    category: str = "通用"


@router.get("/snippets")
async def list_snippets(
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(CommandSnippet).where(CommandSnippet.user_id == current_user.id)
    if category:
        query = query.where(CommandSnippet.category == category)
    query = query.order_by(CommandSnippet.use_count.desc(), CommandSnippet.sort_order)
    result = await db.execute(query)
    snippets = result.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "command": s.command,
            "description": s.description,
            "category": s.category,
            "use_count": s.use_count,
        }
        for s in snippets
    ]


@router.post("/snippets")
async def create_snippet(
    req: SnippetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    snippet = CommandSnippet(
        name=req.name,
        command=req.command,
        description=req.description,
        category=req.category,
        user_id=current_user.id,
    )
    db.add(snippet)
    await db.flush()
    return {"id": snippet.id, "name": snippet.name}


@router.delete("/snippets/{snippet_id}")
async def delete_snippet(
    snippet_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(CommandSnippet).where(
            CommandSnippet.id == snippet_id,
            CommandSnippet.user_id == current_user.id,
        )
    )
    return {"message": "删除成功"}


@router.post("/snippets/{snippet_id}/use")
async def use_snippet(
    snippet_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """标记命令被使用（统计使用次数）"""
    await db.execute(
        update(CommandSnippet)
        .where(CommandSnippet.id == snippet_id, CommandSnippet.user_id == current_user.id)
        .values(use_count=CommandSnippet.use_count + 1)
    )
    return {"message": "ok"}


# ===== 批量命令 =====

class BatchCommandRequest(BaseModel):
    session_ids: List[str]  # 目标会话ID列表
    command: str             # 要发送的命令
    interval_ms: int = 100   # 发送间隔（毫秒）


@router.post("/batch-command")
async def send_batch_command(
    req: BatchCommandRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    向多个终端同时发送命令
    """
    # 验证会话归属
    result = await db.execute(
        select(TerminalSession).where(
            TerminalSession.id.in_(req.session_ids),
            TerminalSession.user_id == current_user.id,
        )
    )
    valid_sessions = {s.id for s in result.scalars().all()}
    
    sent = []
    failed = []
    
    for sid in req.session_ids:
        if sid not in valid_sessions:
            failed.append({"session_id": sid, "reason": "无权访问"})
            continue
        
        conn = session_manager.get_session(sid)
        if not conn or conn.status != "active":
            failed.append({"session_id": sid, "reason": "会话未连接"})
            continue
        
        try:
            cmd = req.command
            if not cmd.endswith("\n"):
                cmd += "\n"
            await conn.write(cmd.encode())
            sent.append(sid)
        except Exception as e:
            failed.append({"session_id": sid, "reason": str(e)})
        
        if req.interval_ms > 0:
            await asyncio.sleep(req.interval_ms / 1000)
    
    # 记录审计日志
    log = AuditLog(
        action="batch_command",
        detail=f"命令: {req.command[:100]}, 目标: {len(req.session_ids)}个会话",
        user_id=current_user.id,
    )
    db.add(log)
    
    return {"sent": sent, "failed": failed, "total": len(req.session_ids)}


# ===== 审计日志 =====

@router.get("/audit-logs")
async def list_audit_logs(
    page: int = 1,
    page_size: int = 50,
    action: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(AuditLog).where(AuditLog.user_id == current_user.id)
    if action:
        query = query.where(AuditLog.action == action)
    query = query.order_by(desc(AuditLog.created_at))
    
    # 总数
    from sqlalchemy import func, select as sel
    count_result = await db.execute(
        sel(func.count()).select_from(AuditLog).where(AuditLog.user_id == current_user.id)
    )
    total = count_result.scalar()
    
    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "logs": [
            {
                "id": l.id,
                "action": l.action,
                "detail": l.detail,
                "server_host": l.server_host,
                "server_name": l.server_name,
                "ip_address": l.ip_address,
                "created_at": l.created_at,
                "session_id": l.session_id,
            }
            for l in logs
        ],
    }


# ===== 会话管理 =====

@router.get("/sessions")
async def list_my_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户的所有活跃终端会话（自动清理幽灵会话）"""
    result = await db.execute(
        select(TerminalSession).where(
            TerminalSession.user_id == current_user.id,
            TerminalSession.status != "closed",
        )
    )
    db_sessions = result.scalars().all()
    
    sessions_out = []
    for s in db_sessions:
        live_conn = session_manager.get_session(s.id)
        if live_conn and live_conn.status != "closed":
            # 有活跃 SSH 连接，正常返回
            sessions_out.append({
                "id": s.id,
                "tab_id": s.tab_id,
                "tab_name": s.tab_name,
                "tab_color": s.tab_color,
                "server_id": s.server_id,
                "status": live_conn.status,
                "terminal_cols": s.terminal_cols,
                "terminal_rows": s.terminal_rows,
                "created_at": s.created_at,
                "last_activity": s.last_activity,
                "keepalive_hours": s.keepalive_hours,
            })
        else:
            # 幽灵会话：数据库有记录但无实际连接，删除
            await db.delete(s)
    
    if sessions_out != db_sessions:
        await db.commit()
    
    return sessions_out


@router.post("/sessions/connect")
async def create_session_and_connect(
    server_id: int,
    tab_name: str = "",
    tab_color: str = "#409EFF",
    keepalive_hours: int = 24,
    cols: int = 80,
    rows: int = 24,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建终端会话并启动SSH连接"""
    import uuid as _uuid
    
    # 获取服务器连接信息
    from models import Server
    result = await db.execute(
        select(Server).where(Server.id == server_id, Server.owner_id == current_user.id)
    )
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")
    
    # 检查会话数量限制
    count_result = await db.execute(
        select(TerminalSession).where(
            TerminalSession.user_id == current_user.id,
            TerminalSession.status == "active",
        )
    )
    active_count = len(count_result.scalars().all())
    if active_count >= settings.MAX_SESSIONS_PER_USER:
        raise HTTPException(status_code=400, detail=f"已达最大会话数限制 ({settings.MAX_SESSIONS_PER_USER})")
    
    session_id = str(_uuid.uuid4())
    tab_id = str(_uuid.uuid4())
    
    # 保存会话到数据库
    db_session = TerminalSession(
        id=session_id,
        tab_id=tab_id,
        tab_name=tab_name or server.name,
        tab_color=tab_color,
        user_id=current_user.id,
        server_id=server_id,
        terminal_cols=cols,
        terminal_rows=rows,
        keepalive_hours=keepalive_hours,
        status="active",
    )
    db.add(db_session)
    
    # 更新服务器连接统计
    server.last_connected = time.time()
    server.connect_count = (server.connect_count or 0) + 1
    
    # 记录审计日志
    log = AuditLog(
        action="connect",
        detail=f"连接到 {server.host}",
        server_host=server.host,
        server_name=server.name,
        user_id=current_user.id,
        session_id=session_id,
    )
    db.add(log)
    await db.flush()
    
    # 启动 SSH 连接
    server_info = {
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
        "keepalive_hours": keepalive_hours,
    }
    await session_manager.create_session(session_id, server_info, cols, rows)
    
    return {
        "session_id": session_id,
        "tab_id": tab_id,
        "tab_name": db_session.tab_name,
        "tab_color": tab_color,
        "server_id": server_id,
        "server_name": server.name,
        "server_host": server.host,
    }


@router.delete("/sessions/{session_id}")
async def close_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """关闭终端会话并从数据库删除"""
    from models import Server

    result = await db.execute(
        select(TerminalSession).where(
            TerminalSession.id == session_id,
            TerminalSession.user_id == current_user.id,
        )
    )
    db_session = result.scalar_one_or_none()
    if db_session:
        # 查关联的服务器信息
        srv_result = await db.execute(select(Server).where(Server.id == db_session.server_id))
        server = srv_result.scalar_one_or_none()
        host = server.host if server else "unknown"

        # 记录日志
        log = AuditLog(
            action="disconnect",
            detail=f"关闭会话 {db_session.tab_name}",
            server_host=host,
            server_name=db_session.tab_name,
            user_id=current_user.id,
            session_id=session_id,
        )
        db.add(log)
        # 直接删除记录，避免幽灵会话
        await db.delete(db_session)
        await db.commit()

    await session_manager.close_session(session_id)
    return {"message": "会话已关闭"}
