"""
数据库连接 & 初始化
"""
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

from config import settings
from models import Base, User
from security import get_password_hash

logger = logging.getLogger(__name__)

# 确保数据目录存在
os.makedirs("data", exist_ok=True)
os.makedirs(settings.LOG_DIR, exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库，创建表，插入默认管理员"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 检查是否已有管理员账号
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.is_admin == True))
        admin = result.scalar_one_or_none()
        
        if not admin:
            # 创建默认管理员，密码从环境变量读取，默认 admin123
            default_password = os.getenv("ADMIN_PASSWORD", "admin123")
            admin_user = User(
                username=os.getenv("ADMIN_USERNAME", "admin"),
                hashed_password=get_password_hash(default_password),
                is_admin=True,
                is_active=True,
            )
            session.add(admin_user)
            await session.commit()
            logger.info(f"✅ 创建默认管理员账号: admin / {default_password}")
        else:
            logger.info(f"✅ 已存在管理员账号: {admin.username}")
