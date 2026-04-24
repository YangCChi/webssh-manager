# ==================== 构建阶段：前端 ====================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install --registry=https://registry.npmmirror.com

COPY frontend/ .
RUN npm run build

# ==================== 构建阶段：后端依赖 ====================
FROM python:3.11-slim AS backend-builder

WORKDIR /app
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    fastapi==0.111.0 \
    uvicorn[standard]==0.30.1 \
    websockets==12.0 \
    asyncssh==2.14.2 \
    python-jose[cryptography]==3.3.0 \
    argon2-cffi==23.1.0 \
    sqlalchemy==2.0.30 \
    aiosqlite==0.20.0 \
    python-multipart==0.0.9 \
    cryptography==42.0.8 \
    paramiko==3.4.0 \
    aiofiles==23.2.1 \
    python-dotenv==1.0.1 \
    pydantic==2.7.1 \
    pydantic-settings==2.3.3 \
    httpx==0.27.0 \
    greenlet==3.0.3

# ==================== 运行阶段 ====================
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制 Python 包
COPY --from=backend-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# 复制后端代码
COPY backend/ ./

# 复制前端构建产物
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# 创建必要目录
RUN mkdir -p /app/data /app/logs /tmp/webssh_uploads

# 非 root 用户运行
RUN useradd -m -u 1000 webssh && chown -R webssh:webssh /app /tmp/webssh_uploads
USER webssh

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
