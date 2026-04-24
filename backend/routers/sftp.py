"""
API 路由 - SFTP 文件管理
"""
import os
import stat
import asyncio
import logging
from typing import Optional, List
from pathlib import Path

import asyncssh
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import aiofiles

from database import get_db
from models import Server, User
from security import decrypt_secret
from routers.auth import get_current_user
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sftp", tags=["SFTP文件管理"])

os.makedirs(settings.SFTP_UPLOAD_DIR, exist_ok=True)


async def _get_sftp_client(server: Server):
    """建立SFTP连接"""
    connect_kwargs = {
        "host": server.host,
        "port": server.port,
        "username": server.username,
        "known_hosts": None,
    }
    if server.auth_type == "password":
        connect_kwargs["password"] = decrypt_secret(server.encrypted_password)
    else:
        key_str = decrypt_secret(server.encrypted_private_key)
        passphrase = decrypt_secret(server.private_key_passphrase) or None
        if key_str:
            connect_kwargs["client_keys"] = [asyncssh.import_private_key(key_str, passphrase)]
    
    conn = await asyncssh.connect(**connect_kwargs)
    sftp = await conn.start_sftp_client()
    return conn, sftp


async def _get_server(server_id: int, user: User, db: AsyncSession) -> Server:
    result = await db.execute(
        select(Server).where(Server.id == server_id, Server.owner_id == user.id)
    )
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")
    return server


@router.get("/{server_id}/list")
async def list_directory(
    server_id: int,
    path: str = "/",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出目录内容"""
    server = await _get_server(server_id, current_user, db)
    conn, sftp = await _get_sftp_client(server)
    try:
        entries = await sftp.readdir(path)
        files = []
        for entry in entries:
            try:
                attrs = entry.attrs
                files.append({
                    "name": entry.filename,
                    "path": os.path.join(path, entry.filename).replace("\\", "/"),
                    "is_dir": stat.S_ISDIR(attrs.permissions) if attrs.permissions else False,
                    "size": attrs.size or 0,
                    "mtime": attrs.mtime or 0,
                    "permissions": oct(attrs.permissions)[-4:] if attrs.permissions else "----",
                    "uid": attrs.uid,
                    "gid": attrs.gid,
                })
            except Exception:
                continue
        # 排序：目录在前
        files.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return {"path": path, "files": files}
    finally:
        sftp.exit()
        conn.close()


@router.get("/{server_id}/download")
async def download_file(
    server_id: int,
    path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """下载文件"""
    server = await _get_server(server_id, current_user, db)
    conn, sftp = await _get_sftp_client(server)
    
    filename = os.path.basename(path)
    local_path = os.path.join(settings.SFTP_UPLOAD_DIR, f"{current_user.id}_{filename}")
    
    try:
        await sftp.get(path, local_path)
        sftp.exit()
        conn.close()
        
        async def file_generator():
            async with aiofiles.open(local_path, "rb") as f:
                while True:
                    chunk = await f.read(65536)
                    if not chunk:
                        break
                    yield chunk
            # 清理临时文件
            try:
                os.remove(local_path)
            except Exception:
                pass
        
        return StreamingResponse(
            file_generator(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        sftp.exit()
        conn.close()
        raise HTTPException(status_code=400, detail=f"下载失败: {e}")


@router.post("/{server_id}/upload")
async def upload_file(
    server_id: int,
    remote_path: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传文件"""
    # 检查文件大小
    content = await file.read()
    size_mb = len(content) / 1024 / 1024
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"文件超过最大限制 {settings.MAX_UPLOAD_SIZE_MB}MB")
    
    server = await _get_server(server_id, current_user, db)
    
    # 保存到临时目录
    local_path = os.path.join(settings.SFTP_UPLOAD_DIR, f"{current_user.id}_{file.filename}")
    async with aiofiles.open(local_path, "wb") as f:
        await f.write(content)
    
    conn, sftp = await _get_sftp_client(server)
    try:
        dest = os.path.join(remote_path, file.filename).replace("\\", "/")
        await sftp.put(local_path, dest)
        return {"message": "上传成功", "path": dest}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"上传失败: {e}")
    finally:
        sftp.exit()
        conn.close()
        try:
            os.remove(local_path)
        except Exception:
            pass


@router.delete("/{server_id}/delete")
async def delete_file(
    server_id: int,
    path: str,
    is_dir: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除文件或目录"""
    server = await _get_server(server_id, current_user, db)
    conn, sftp = await _get_sftp_client(server)
    try:
        if is_dir:
            await sftp.rmtree(path)
        else:
            await sftp.remove(path)
        return {"message": "删除成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"删除失败: {e}")
    finally:
        sftp.exit()
        conn.close()


@router.post("/{server_id}/mkdir")
async def create_directory(
    server_id: int,
    path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建目录"""
    server = await _get_server(server_id, current_user, db)
    conn, sftp = await _get_sftp_client(server)
    try:
        await sftp.mkdir(path)
        return {"message": "目录创建成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    finally:
        sftp.exit()
        conn.close()


@router.post("/{server_id}/rename")
async def rename_file(
    server_id: int,
    old_path: str,
    new_path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重命名文件或目录"""
    server = await _get_server(server_id, current_user, db)
    conn, sftp = await _get_sftp_client(server)
    try:
        await sftp.rename(old_path, new_path)
        return {"message": "重命名成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"重命名失败: {e}")
    finally:
        sftp.exit()
        conn.close()


@router.get("/{server_id}/read")
async def read_file(
    server_id: int,
    path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """读取文本文件内容（用于在线编辑）"""
    server = await _get_server(server_id, current_user, db)
    conn, sftp = await _get_sftp_client(server)
    try:
        async with sftp.open(path, "r") as f:
            content = await f.read()
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取失败: {e}")
    finally:
        sftp.exit()
        conn.close()


@router.post("/{server_id}/write")
async def write_file(
    server_id: int,
    path: str,
    content: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """写入文本文件内容（在线编辑保存）"""
    server = await _get_server(server_id, current_user, db)
    conn, sftp = await _get_sftp_client(server)
    try:
        async with sftp.open(path, "w") as f:
            await f.write(content)
        return {"message": "保存成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"保存失败: {e}")
    finally:
        sftp.exit()
        conn.close()
