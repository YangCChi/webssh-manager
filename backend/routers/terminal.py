"""
WebSocket 终端路由 - SSH 会话的核心通信层
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from database import get_db, AsyncSessionLocal
from models import Server, TerminalSession, AuditLog, User
from ssh_manager import session_manager
from security import decode_token
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["终端WebSocket"])


async def _get_user_from_token(token: str, db: AsyncSession) -> Optional[User]:
    payload = decode_token(token)
    if not payload:
        return None
    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


@router.websocket("/ws/terminal/{session_id}")
async def terminal_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket 终端连接
    
    协议：
    - 客户端发送 JSON: {"type": "auth", "token": "..."}  -> 认证
    - 客户端发送 JSON: {"type": "resize", "cols": N, "rows": N}  -> 调整大小
    - 客户端发送 JSON: {"type": "input", "data": "..."}  -> 键盘输入（base64）
    - 客户端发送 JSON: {"type": "ping"}  -> 心跳
    - 服务端发送 bytes: SSH输出数据
    - 服务端发送 JSON: {"type": "status", "status": "..."}  -> 状态通知
    """
    await websocket.accept()
    
    conn = None
    user = None
    
    try:
        # 第一步：等待认证消息
        auth_data = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        auth_msg = json.loads(auth_data)
        
        if auth_msg.get("type") != "auth":
            await websocket.send_json({"type": "error", "message": "请先发送认证信息"})
            await websocket.close()
            return
        
        token = auth_msg.get("token", "")
        
        async with AsyncSessionLocal() as db:
            user = await _get_user_from_token(token, db)
            if not user:
                await websocket.send_json({"type": "error", "message": "认证失败"})
                await websocket.close()
                return

        # 第二步：查找或创建会话
        conn = session_manager.get_session(session_id)
        
        if conn is None:
            # 从数据库恢复会话信息
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(TerminalSession).where(
                        TerminalSession.id == session_id,
                        TerminalSession.user_id == user.id,
                    )
                )
                db_session = result.scalar_one_or_none()
                
                if db_session:
                    # 恢复已有会话
                    srv_result = await db.execute(
                        select(Server).where(Server.id == db_session.server_id)
                    )
                    server = srv_result.scalar_one_or_none()
                    if server:
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
                            "keepalive_hours": db_session.keepalive_hours,
                        }
                        conn = await session_manager.create_session(
                            session_id, server_info,
                            db_session.terminal_cols, db_session.terminal_rows
                        )

        if conn is None:
            await websocket.send_json({"type": "error", "message": "会话不存在"})
            await websocket.close()
            return

        # 附加 WebSocket
        conn.attach_websocket(websocket)
        logger.info(f"WS attached: session={session_id}, status={conn.status}, websockets={len(conn.websockets)}")
        
        # 发送历史缓冲区数据（恢复终端显示）
        # 无论 tmux 还是非 tmux 模式都回放 buffer：
        # - 非 tmux：buffer 是唯一的恢复来源
        # - tmux：buffer 先回放旧数据，随后 tmux attach 的完整重绘会覆盖屏幕内容
        replay = await conn.get_replay_data()
        if replay:
            logger.info(f"回放 buffer: session={session_id}, {len(replay)} 字节")
            await websocket.send_bytes(replay)
        else:
            logger.info(f"无 buffer 回放: session={session_id}")
        
        # 等待 SSH 连接完成（而不是固定 sleep）
        # 这样可以确保 tmux attach 的重绘数据已经开始发送
        if conn.status == "connecting":
            logger.info(f"等待 SSH 连接: session={session_id}")
            for _ in range(60):  # 最多等 6 秒（60 * 100ms）
                if conn.status != "connecting":
                    break
                await asyncio.sleep(0.1)
        
        logger.info(f"SSH 连接状态: session={session_id}, status={conn.status}, websockets={len(conn.websockets)}, uses_tmux={getattr(conn, 'uses_tmux', False)}")
        
        await websocket.send_json({
            "type": "status",
            "status": conn.status,
            "session_id": session_id,
        })

        # 主消息循环
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=60)
                
                if message.get("type") == "websocket.disconnect":
                    break
                
                if "text" in message:
                    msg = json.loads(message["text"])
                    msg_type = msg.get("type", "")
                    
                    if msg_type == "input":
                        import base64
                        data = base64.b64decode(msg.get("data", ""))
                        await conn.write(data)
                    
                    elif msg_type == "resize":
                        cols = int(msg.get("cols", 80))
                        rows = int(msg.get("rows", 24))
                        await conn.resize(cols, rows)
                        # 更新数据库
                        async with AsyncSessionLocal() as db:
                            await db.execute(
                                update(TerminalSession)
                                .where(TerminalSession.id == session_id)
                                .values(terminal_cols=cols, terminal_rows=rows, updated_at=time.time())
                            )
                            await db.commit()
                    
                    elif msg_type == "ping":
                        await websocket.send_json({"type": "pong"})
                
                elif "bytes" in message:
                    # 直接发送字节输入
                    await conn.write(message["bytes"])
                    
            except asyncio.TimeoutError:
                # 超时发送心跳
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket消息处理错误: {e}")
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket连接错误: {e}")
    finally:
        if conn:
            conn.detach_websocket(websocket)
        # 更新最后活动时间
        if session_id:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(TerminalSession)
                    .where(TerminalSession.id == session_id)
                    .values(last_activity=time.time(), updated_at=time.time())
                )
                await db.commit()
        logger.info(f"WebSocket断开: session={session_id}")



