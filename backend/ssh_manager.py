"""
SSH 会话管理器 - 核心引擎
支持多终端并发、会话持久化（tmux）、自动重连、终端内容回放
"""
import asyncio
import json
import logging
import os
import re
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Set

import asyncssh
from fastapi import WebSocket

from config import settings
from security import decrypt_secret

logger = logging.getLogger(__name__)

# 终端 buffer 持久化目录
BUFFER_DIR = Path(__file__).parent / "data" / "terminal_buffers"


class TerminalBuffer:
    """终端输出环形缓冲区（保存历史输出用于恢复），支持磁盘持久化"""

    def __init__(self, session_id: str, maxlen: int = settings.SESSION_BUFFER_SIZE):
        self.session_id = session_id
        self._maxlen = maxlen
        self._raw = []           # 原始字节序列（用于精确恢复）
        self._raw_max = 500000   # 最大保存字节数
        self._file_path = BUFFER_DIR / f"{session_id}.bin"
        self._file = None        # 持久化文件句柄

    def _ensure_dir(self):
        BUFFER_DIR.mkdir(parents=True, exist_ok=True)

    def open(self):
        """打开持久化文件，追加模式"""
        self._ensure_dir()
        try:
            self._file = open(self._file_path, "ab")
        except Exception as e:
            logger.error(f"打开 buffer 文件失败 {self._file_path}: {e}")
            self._file = None

    def load(self):
        """从磁盘加载历史数据（用于恢复会话）"""
        self._ensure_dir()
        if self._file_path.exists():
            try:
                data = self._file_path.read_bytes()
                if data:
                    # 按块分割加载（模拟之前的 write 行为）
                    chunk_size = 4096
                    for i in range(0, len(data), chunk_size):
                        self._raw.append(data[i:i + chunk_size])
                    # 如果文件过大，截断保留最近的 _raw_max 字节
                    total = sum(len(d) for d in self._raw)
                    while total > self._raw_max and self._raw:
                        removed = self._raw.pop(0)
                        total -= len(removed)
                    logger.info(f"从磁盘恢复终端 buffer: session={self.session_id}, {len(data)} 字节")
                    return True
            except Exception as e:
                logger.error(f"加载 buffer 文件失败 {self._file_path}: {e}")
        return False

    def write(self, data: bytes):
        self._raw.append(data)
        # 控制原始缓冲大小
        total = sum(len(d) for d in self._raw)
        while total > self._raw_max and self._raw:
            removed = self._raw.pop(0)
            total -= len(removed)
        # 同时写入磁盘
        if self._file:
            try:
                self._file.write(data)
                self._file.flush()
            except Exception as e:
                logger.debug(f"写入 buffer 文件失败: {e}")

    def get_replay(self) -> bytes:
        """获取用于重放的所有历史数据"""
        return b"".join(self._raw)

    def close(self):
        """关闭文件句柄"""
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None

    def destroy(self):
        """关闭并删除持久化文件"""
        self.close()
        try:
            if self._file_path.exists():
                self._file_path.unlink()
                logger.debug(f"已删除 buffer 文件: {self._file_path}")
        except Exception as e:
            logger.debug(f"删除 buffer 文件失败: {e}")

    def clear(self):
        self._raw.clear()


class SSHConnection:
    """单个 SSH 连接实例"""
    
    # tmux session 名前缀
    TMUX_PREFIX = "webssh_"

    def __init__(self, session_id: str, server_info: dict):
        self.session_id = session_id
        self.server_info = server_info
        self.conn: Optional[asyncssh.SSHClientConnection] = None
        self.process: Optional[asyncssh.SSHClientProcess] = None
        self.channel = None
        self.buffer = TerminalBuffer(session_id)
        self.websockets: Set[WebSocket] = set()
        self.cols = 80
        self.rows = 24
        self.status = "connecting"  # connecting/active/disconnected/closed
        self.created_at = time.time()
        self.last_activity = time.time()
        self._read_task: Optional[asyncio.Task] = None
        self._keepalive_task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0
        self._max_reconnect = 10
        self._lock = asyncio.Lock()
        self.uses_tmux = False  # 是否使用 tmux
        self.tmux_session_name = f"{self.TMUX_PREFIX}{session_id}"
        self.on_status_change = None  # 状态变更回调（由 WebSocket 路由设置）

    @property
    def tmux_cmd(self):
        """tmux attach-or-new 命令"""
        # -u: 强制 UTF-8
        # -A: 如果 session 已存在则 attach，不存在则创建
        # 注意：不使用 -f /dev/null，因为 tmux_init_cmd 已经设置了全局选项
        # PTY 大小由 SSH channel 的 term_size 控制，tmux 会自动适配
        return (
            f'tmux -u new-session -A -s {self.tmux_session_name}'
        )

    @property
    def tmux_init_cmd(self):
        """设置 tmux 全局选项的命令（在 new-session 之前执行一次）"""
        return (
            'tmux set-option -g escape-time 0 \\; '
            'set-option -g default-terminal xterm-256color \\; '
            'set-option -ga terminal-overrides ",xterm-256color:Tc" \\; '
            'set-option -g mouse on \\; '
            'set-option -g status off'
        )

    async def _check_tmux_available(self) -> bool:
        """检查远端是否有 tmux"""
        try:
            result = await self.conn.run("which tmux 2>/dev/null", check=True)
            return result.stdout.strip().endswith("tmux")
        except Exception:
            return False

    async def connect(self, is_reconnect: bool = False) -> bool:
        """建立 SSH 连接"""
        info = self.server_info
        try:
            connect_kwargs = {
                "host": info["host"],
                "port": info.get("port", 22),
                "username": info["username"],
                "connect_timeout": settings.SSH_CONNECT_TIMEOUT,
                "server_host_key_algs": ["ssh-rsa", "ecdsa-sha2-nistp256", 
                                          "ssh-ed25519", "rsa-sha2-256", "rsa-sha2-512"],
                "known_hosts": None,  # 不验证主机密钥（内网环境）
            }

            auth_type = info.get("auth_type", "password")
            if auth_type == "password":
                connect_kwargs["password"] = decrypt_secret(info.get("encrypted_password", ""))
            elif auth_type == "key":
                private_key_str = decrypt_secret(info.get("encrypted_private_key", ""))
                passphrase = decrypt_secret(info.get("private_key_passphrase", "")) or None
                if private_key_str:
                    key = asyncssh.import_private_key(private_key_str, passphrase)
                    connect_kwargs["client_keys"] = [key]
                    connect_kwargs["passphrase"] = None

            # 跳板机支持
            if info.get("proxy_enabled") and info.get("proxy_host"):
                proxy_conn = await asyncssh.connect(
                    host=info["proxy_host"],
                    port=info.get("proxy_port", 22),
                    username=info["proxy_username"],
                    password=decrypt_secret(info.get("proxy_encrypted_password", "")),
                    known_hosts=None,
                    connect_timeout=settings.SSH_CONNECT_TIMEOUT,
                )
                connect_kwargs["tunnel"] = proxy_conn

            self.conn = await asyncssh.connect(**connect_kwargs)
            
            # 从磁盘恢复历史 buffer（用于页面刷新后重放）
            # tmux 模式下需要记录增量数据，因为 tmux attach 只重绘当前屏幕
            self.buffer.load()
            # 打开 buffer 持久化写入
            self.buffer.open()
            
            # 判断是否使用 tmux
            if not is_reconnect:
                self.uses_tmux = await self._check_tmux_available()
                if self.uses_tmux:
                    logger.info(f"远端支持 tmux，使用 tmux 托管终端: {info['host']} [session={self.session_id}]")
                    # 预先设置 tmux 全局选项
                    try:
                        await self.conn.run(self.tmux_init_cmd, check=False)
                    except Exception as e:
                        logger.warning(f"设置 tmux 选项失败（不影响功能）: {e}")
                else:
                    logger.info(f"远端无 tmux，使用普通 shell: {info['host']} [session={self.session_id}]")
            
            # 打开交互式 Shell（优先用 tmux）
            if self.uses_tmux:
                cmd = self.tmux_cmd
            else:
                cmd = None  # 默认 shell

            self.process = await self.conn.create_process(
                term_type="xterm-256color",
                term_size=(self.cols, self.rows),
                encoding=None,
                command=cmd,
            )
            
            self.status = "active"
            self._reconnect_attempts = 0
            logger.info(f"SSH连接成功: {info['host']} [session={self.session_id}, tmux={self.uses_tmux}]")
            
            # 通知所有已连接的 WebSocket 状态已变更
            await self._broadcast_status()
            
            # 启动读取任务
            self._read_task = asyncio.create_task(self._read_loop())
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            
            return True

        except Exception as e:
            self.status = "disconnected"
            logger.error(f"SSH连接失败 {info['host']}: {e}")
            # 通知所有已连接的 WebSocket 连接失败
            await self._broadcast_status()
            await self._broadcast(
                f"\r\n\033[31m[连接失败] {e}\033[0m\r\n".encode()
            )
            return False

    async def _read_loop(self):
        """持续读取 SSH 输出并广播到所有 WebSocket"""
        total_bytes = 0
        logger.info(f"_read_loop 启动: session={self.session_id}, websockets={len(self.websockets)}")
        try:
            while self.process and not self.process.stdout.at_eof():
                try:
                    data = await asyncio.wait_for(
                        self.process.stdout.read(4096), timeout=0.1
                    )
                    if data:
                        total_bytes += len(data)
                        self.buffer.write(data)
                        self.last_activity = time.time()
                        await self._broadcast(data)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.debug(f"读取SSH数据异常: {e}")
                    break
            logger.info(f"SSH读取循环结束: session={self.session_id}, 共读取 {total_bytes} 字节")
        except Exception as e:
            logger.error(f"SSH读取循环异常: {e}")
        finally:
            if self.status == "active":
                self.status = "disconnected"
                await self._broadcast_status()
                await self._broadcast(
                    "\r\n\033[33m[SSH连接已断开，正在尝试重连...]\033[0m\r\n".encode()
                )
                asyncio.create_task(self._auto_reconnect())
            elif self.status == "disconnected":
                # 已经是断开状态，也通知一下
                await self._broadcast_status()

    async def _keepalive_loop(self):
        """SSH keepalive，通过发送 keep-alive 请求而非执行命令，避免干扰 TUI"""
        while self.status == "active":
            await asyncio.sleep(settings.SSH_KEEPALIVE_INTERVAL)
            if self.conn and self.status == "active":
                try:
                    # 用 send_keepalive 代替 run("true")，不创建新 channel，不干扰主 PTY
                    self.conn.send_keepalive()
                except Exception:
                    pass

    async def _auto_reconnect(self):
        """自动重连逻辑（tmux 模式下 attach 回原会话）"""
        for attempt in range(1, self._max_reconnect + 1):
            if self.status == "closed":
                return
            delay = min(2 ** attempt, 60)  # 指数退避，最长60秒
            await self._broadcast(
                f"\r\n\033[33m[第{attempt}次重连，等待{delay}秒...]\033[0m\r\n".encode()
            )
            await asyncio.sleep(delay)
            
            if self.status == "closed":
                return
            
            logger.info(f"尝试重连 session={self.session_id}, 第{attempt}次")
            # tmux 模式下 is_reconnect=True，会 attach 回已有的 tmux session
            success = await self.connect(is_reconnect=True)
            if success:
                if self.uses_tmux:
                    await self._broadcast(
                        "\r\n\033[32m[重连成功！（已恢复 tmux 会话）]\033[0m\r\n".encode()
                    )
                else:
                    await self._broadcast(
                        "\r\n\033[32m[重连成功！]\033[0m\r\n".encode()
                    )
                return
        
        await self._broadcast(
            "\r\n\033[31m[重连失败，已达最大重试次数。请手动重新连接。]\033[0m\r\n".encode()
        )

    async def _broadcast(self, data: bytes):
        """广播数据到所有连接的 WebSocket"""
        dead = set()
        for ws in self.websockets.copy():
            try:
                await ws.send_bytes(data)
            except Exception:
                dead.add(ws)
        if dead:
            logger.debug(f"_broadcast: session={self.session_id}, 发送到 {len(self.websockets)} 个 ws, {len(dead)} 个失败")
        self.websockets -= dead

    async def _broadcast_status(self):
        """向所有 WebSocket 广播当前连接状态"""
        dead = set()
        msg = json.dumps({"type": "status", "status": self.status, "session_id": self.session_id})
        for ws in self.websockets.copy():
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        self.websockets -= dead
        # 同时调用状态变更回调
        if self.on_status_change:
            try:
                self.on_status_change(self.status)
            except Exception:
                self.on_status_change = None

    async def write(self, data: bytes):
        """向 SSH 发送输入"""
        if self.process and self.status == "active":
            try:
                self.process.stdin.write(data)
                await self.process.stdin.drain()  # 确保数据立即发送
                self.last_activity = time.time()
            except Exception as e:
                logger.error(f"SSH写入失败: {e}")

    async def resize(self, cols: int, rows: int):
        """调整终端大小"""
        old_cols, old_rows = self.cols, self.rows
        self.cols = cols
        self.rows = rows
        if self.process and self.status == "active":
            try:
                self.process.change_terminal_size(cols, rows)
            except Exception:
                pass

    async def force_redraw(self):
        """强制 tmux 重绘屏幕（用于刷新页面后恢复显示）"""
        if not (self.process and self.status == "active" and self.uses_tmux):
            return
        try:
            # 先缩小再恢复，强制 tmux 感知尺寸变化并重绘
            self.process.change_terminal_size(self.cols - 1, self.rows - 1)
            await asyncio.sleep(0.05)
            self.process.change_terminal_size(self.cols, self.rows)
            logger.info(f"强制 tmux 重绘完成: session={self.session_id}")
        except Exception as e:
            logger.warning(f"强制 tmux 重绘失败: {e}")

    def attach_websocket(self, ws: WebSocket):
        self.websockets.add(ws)

    def detach_websocket(self, ws: WebSocket):
        self.websockets.discard(ws)

    async def get_replay_data(self) -> bytes:
        """获取历史数据用于恢复终端显示"""
        return self.buffer.get_replay()

    async def close(self):
        """关闭 SSH 连接"""
        self.status = "closed"
        if self._read_task:
            self._read_task.cancel()
        if self._keepalive_task:
            self._keepalive_task.cancel()
        if self.process:
            try:
                self.process.close()
            except Exception:
                pass
        # 关闭 buffer 持久化文件
        self.buffer.close()
        # tmux 模式下清理远端 tmux session
        if self.uses_tmux and self.conn:
            try:
                await self.conn.run(
                    f"tmux kill-session -t {self.tmux_session_name} 2>/dev/null",
                    check=False,
                )
            except Exception:
                pass
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
        self.websockets.clear()
        logger.info(f"SSH连接关闭: session={self.session_id}")


class SessionManager:
    """全局会话管理器（单例）"""
    
    def __init__(self):
        self._sessions: Dict[str, SSHConnection] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    def start(self):
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def create_session(
        self, session_id: str, server_info: dict, cols: int = 80, rows: int = 24
    ) -> SSHConnection:
        """创建新 SSH 会话"""
        conn = SSHConnection(session_id, server_info)
        conn.cols = cols
        conn.rows = rows
        self._sessions[session_id] = conn
        # 异步连接，不阻塞
        asyncio.create_task(conn.connect())
        return conn

    def get_session(self, session_id: str) -> Optional[SSHConnection]:
        return self._sessions.get(session_id)

    async def close_session(self, session_id: str):
        conn = self._sessions.pop(session_id, None)
        if conn:
            await conn.close()
            conn.buffer.destroy()  # 删除持久化文件

    def list_sessions(self) -> List[dict]:
        result = []
        for sid, conn in self._sessions.items():
            result.append({
                "session_id": sid,
                "status": conn.status,
                "host": conn.server_info.get("host", ""),
                "ws_count": len(conn.websockets),
                "last_activity": conn.last_activity,
                "created_at": conn.created_at,
            })
        return result

    async def _cleanup_loop(self):
        """定期清理过期会话"""
        while True:
            await asyncio.sleep(300)  # 每5分钟检查
            now = time.time()
            to_close = []
            for sid, conn in self._sessions.items():
                # 超过保活时长且无活跃WebSocket的会话
                keepalive_secs = conn.server_info.get("keepalive_hours", 24) * 3600
                if (conn.status == "closed" or 
                    (len(conn.websockets) == 0 and 
                     now - conn.last_activity > keepalive_secs)):
                    to_close.append(sid)
            for sid in to_close:
                logger.info(f"清理过期会话: {sid}")
                await self.close_session(sid)


# 全局单例
session_manager = SessionManager()
