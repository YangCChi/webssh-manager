"""
数据库模型定义
"""
import time
from sqlalchemy import Column, Integer, String, Boolean, Float, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """平台用户（登录账号）"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(200), nullable=False)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(Float, default=time.time)
    last_login = Column(Float, nullable=True)

    servers = relationship("Server", back_populates="owner", cascade="all, delete-orphan")
    sessions = relationship("TerminalSession", back_populates="user", cascade="all, delete-orphan")
    snippets = relationship("CommandSnippet", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")


class ServerGroup(Base):
    """服务器分组"""
    __tablename__ = "server_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    color = Column(String(20), default="#409EFF")  # 分组颜色标识
    sort_order = Column(Integer, default=0)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    servers = relationship("Server", back_populates="group")


class Server(Base):
    """SSH 服务器信息"""
    __tablename__ = "servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)             # 别名
    host = Column(String(255), nullable=False)              # IP 或域名
    port = Column(Integer, default=22)
    username = Column(String(100), nullable=False)
    auth_type = Column(String(20), default="password")      # password / key
    encrypted_password = Column(Text, nullable=True)        # 加密存储的密码
    encrypted_private_key = Column(Text, nullable=True)     # 加密存储的私钥
    private_key_passphrase = Column(Text, nullable=True)    # 私钥密码（加密）

    # 跳板机配置
    proxy_enabled = Column(Boolean, default=False)
    proxy_host = Column(String(255), nullable=True)
    proxy_port = Column(Integer, nullable=True)
    proxy_username = Column(String(100), nullable=True)
    proxy_encrypted_password = Column(Text, nullable=True)

    # 元数据
    tags = Column(String(500), default="")                  # 逗号分隔标签
    notes = Column(Text, default="")
    sort_order = Column(Integer, default=0)
    is_favorite = Column(Boolean, default=False)
    last_connected = Column(Float, nullable=True)
    connect_count = Column(Integer, default=0)

    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)

    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("server_groups.id"), nullable=True)

    owner = relationship("User", back_populates="servers")
    group = relationship("ServerGroup", back_populates="servers")
    sessions = relationship("TerminalSession", back_populates="server")


class TerminalSession(Base):
    """终端会话持久化记录"""
    __tablename__ = "terminal_sessions"

    id = Column(String(64), primary_key=True)              # UUID
    tab_id = Column(String(64), nullable=False, index=True) # 前端标签ID
    tab_name = Column(String(100), default="")
    tab_color = Column(String(20), default="#409EFF")

    # 关联
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False)

    # tmux/screen 后台会话标识
    tmux_session = Column(String(100), nullable=True)       # tmux session name
    pid = Column(Integer, nullable=True)                    # SSH 进程 PID

    # 状态
    status = Column(String(20), default="active")           # active/disconnected/closed
    terminal_cols = Column(Integer, default=220)
    terminal_rows = Column(Integer, default=50)

    # 时间
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)
    last_activity = Column(Float, default=time.time)
    keepalive_hours = Column(Integer, default=24)           # 保活时长

    user = relationship("User", back_populates="sessions")
    server = relationship("Server", back_populates="sessions")


class CommandSnippet(Base):
    """常用命令收藏"""
    __tablename__ = "command_snippets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    command = Column(Text, nullable=False)
    description = Column(String(500), default="")
    category = Column(String(50), default="通用")
    sort_order = Column(Integer, default=0)
    use_count = Column(Integer, default=0)
    created_at = Column(Float, default=time.time)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="snippets")


class AuditLog(Base):
    """操作审计日志"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(50), nullable=False)             # connect/disconnect/command/sftp_upload等
    detail = Column(Text, default="")
    server_host = Column(String(255), nullable=True)
    server_name = Column(String(100), nullable=True)
    ip_address = Column(String(45), nullable=True)          # 客户端IP
    created_at = Column(Float, default=time.time)
    session_id = Column(String(64), nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="audit_logs")
