"""
WebSSH Manager - 主应用入口
"""
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import settings
from database import init_db
from ssh_manager import session_manager
from routers import auth, servers, terminal, sftp, operations

# 日志配置
os.makedirs(settings.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"{settings.LOG_DIR}/webssh.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭生命周期"""
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    
    # 初始化数据库
    await init_db()
    
    # 启动会话管理器（清理任务）
    session_manager.start()
    
    logger.info(f"✅ 服务已启动，监听 {settings.HOST}:{settings.PORT}")
    
    yield
    
    logger.info("🛑 服务正在关闭...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# IP 白名单中间件
@app.middleware("http")
async def ip_whitelist_middleware(request: Request, call_next):
    if settings.ALLOWED_IPS:
        allowed = [ip.strip() for ip in settings.ALLOWED_IPS.split(",") if ip.strip()]
        client_ip = request.client.host if request.client else ""
        if client_ip not in allowed:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": "IP不在白名单中"})
    return await call_next(request)


# 注册路由
app.include_router(auth.router)
app.include_router(servers.router)
app.include_router(terminal.router)
app.include_router(sftp.router)
app.include_router(operations.router)


# 健康检查
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "time": time.time(),
        "active_sessions": len(session_manager._sessions),
    }


# 前端静态文件（生产环境）
static_dir = "/app/frontend/dist"
if os.path.exists(static_dir):
    app.mount("/assets", StaticFiles(directory=f"{static_dir}/assets"), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """所有非API路由都返回前端入口页面（SPA路由支持）"""
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            from fastapi import HTTPException as HE
            raise HE(status_code=404)
        return FileResponse(f"{static_dir}/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
