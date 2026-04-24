"""
WebSSH Manager - 全局配置
"""
import os
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings


def _ensure_key_file() -> str:
    """确保 ENCRYPTION_KEY 持久化，重启后不会变"""
    key_file = Path(__file__).parent / "data" / ".encryption_key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_hex(32)
    key_file.write_text(key)
    return key


class Settings(BaseSettings):
    # 应用基础配置
    APP_NAME: str = "WebSSH Manager"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # 安全配置
    SECRET_KEY: str = os.getenv("SECRET_KEY", secrets.token_hex(32))
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7天

    # 数据库
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/webssh.db"

    # 加密密钥（持久化到文件，避免每次重启生成新 key 导致已加密的密码失效）
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", _ensure_key_file())

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 会话配置
    SESSION_KEEPALIVE_HOURS: int = 24      # 默认会话保活时长（小时）
    MAX_SESSIONS_PER_USER: int = 20        # 每用户最大会话数
    SESSION_BUFFER_SIZE: int = 10000       # 每终端保存的最大历史行数

    # SSH 配置
    SSH_CONNECT_TIMEOUT: int = 15
    SSH_KEEPALIVE_INTERVAL: int = 30

    # SFTP 配置
    SFTP_UPLOAD_DIR: str = "/tmp/webssh_uploads"
    MAX_UPLOAD_SIZE_MB: int = 100

    # 日志
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs"

    # IP 白名单（逗号分隔，空=不限制）
    ALLOWED_IPS: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
