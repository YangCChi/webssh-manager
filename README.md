# WebSSH Manager

> 商用级 WebSSH 管理平台 —— 多终端 · 会话持久化 · SFTP · 一键部署

## ✨ 核心功能

| 功能 | 说明 |
|------|------|
| **多终端** | 同时连接 ≥3 台服务器，独立标签，互不干扰 |
| **会话持久化** | 关闭网页 SSH 不断，重新打开自动恢复所有终端 |
| **自动重连** | 网络闪断指数退避重连，最多重试 10 次 |
| **服务器管理** | 别名/分组/标签/收藏，支持跳板机 |
| **认证方式** | 密码 + SSH 私钥（RSA/Ed25519），加密存储 |
| **SFTP 文件管理** | 上传/下载/编辑/删除/重命名/创建目录 |
| **批量命令** | 一键向多个终端同时发送命令 |
| **常用命令** | 收藏常用命令，一键发送 |
| **操作审计** | 完整操作日志，可筛选导出 |
| **终端美化** | xterm.js · 256色 · 4套主题 · 自定义字号 · 全屏 |
| **安全** | JWT 认证 · 密码加密存储 · IP 白名单 · HTTPS |

## 🚀 快速部署

**全程只需要 2 条命令，不需要手动编辑任何文件。**

```bash
# 1. 克隆项目
git clone https://github.com/YangCChi/webssh-manager.git
cd webssh-manager

# 2. 一键部署（会自动安装 Docker、生成密钥、构建启动）
sudo bash deploy.sh
```

脚本会提示你输入：
- 管理员用户名（默认 `admin`，回车跳过）
- 管理员密码（必须设置）
- 访问端口（默认 `8080`，回车跳过）

部署完成后，浏览器打开 `http://你的服务器IP:8080` 即可使用。

> 密钥（SECRET_KEY / ENCRYPTION_KEY）由脚本自动生成，无需手动配置。

### 方式二：Docker Compose 手动部署

如果不想用一键脚本，也可以手动部署：

```bash
git clone https://github.com/YangCChi/webssh-manager.git
cd webssh-manager

# 1. 生成随机密钥并创建配置（自动完成，不需要 vim）
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -hex 32)
cat > .env << EOF
SECRET_KEY=$SECRET_KEY
ENCRYPTION_KEY=$ENCRYPTION_KEY
ADMIN_USERNAME=admin
ADMIN_PASSWORD=你的密码
PORT=8080
EOF

# 2. 启动
docker compose up -d
```

### 方式三：启用 HTTPS + Nginx

```bash
# 将 SSL 证书放入 docker/certs/
mkdir -p docker/certs
cp 你的证书.pem docker/certs/cert.pem
cp 你的私钥.pem docker/certs/key.pem

# 启动（含 Nginx）
docker compose --profile with-nginx up -d
```

### 方式四：本地开发

```bash
# 后端
cd backend
pip install -r requirements.txt
python main.py

# 前端（另开终端）
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

## ⚙️ 环境变量

创建 `.env` 文件：

```env
SECRET_KEY=your-random-secret-key-here        # JWT 签名密钥
ENCRYPTION_KEY=your-encryption-key-here       # SSH密码加密密钥
ADMIN_USERNAME=admin                           # 管理员用户名
ADMIN_PASSWORD=YourStrongPassword123          # 管理员密码
PORT=8080                                      # 访问端口
SESSION_KEEPALIVE_HOURS=24                     # 会话保活时长
ALLOWED_IPS=                                   # IP白名单（逗号分隔，留空不限制）
LOG_LEVEL=INFO
```

> ⚠️ **生产环境务必修改 SECRET_KEY 和 ENCRYPTION_KEY！**

## 📂 项目结构

```
webssh-manager/
├── backend/
│   ├── main.py           # FastAPI 主入口
│   ├── config.py         # 全局配置
│   ├── models.py         # 数据库模型
│   ├── database.py       # 数据库连接
│   ├── security.py       # JWT + 加密工具
│   ├── ssh_manager.py    # SSH 会话管理器（核心）
│   └── routers/
│       ├── auth.py       # 认证路由
│       ├── servers.py    # 服务器管理路由
│       ├── terminal.py   # WebSocket 终端路由
│       ├── sftp.py       # SFTP 文件管理路由
│       └── operations.py # 运维工具路由
├── frontend/
│   └── src/
│       ├── views/        # 页面组件
│       ├── components/   # 通用组件
│       ├── stores/       # Pinia 状态管理
│       └── utils/        # 工具函数
├── docker/
│   └── nginx.conf        # Nginx 配置（HTTPS）
├── Dockerfile
├── docker-compose.yml
└── deploy.sh             # 一键部署脚本
```

## 🔒 安全说明

- SSH 密码和私钥使用 **Fernet 对称加密**存储在数据库，密钥由 `ENCRYPTION_KEY` 衍生
- 平台登录使用 **bcrypt** 哈希存储密码
- API 使用 **JWT Bearer Token** 认证，默认 7 天有效期
- WebSocket 终端连接需通过认证后才能建立
- 建议生产环境配置 HTTPS + Nginx

## 🛠️ 管理命令

```bash
# 查看运行状态
docker compose ps

# 查看实时日志
docker compose logs -f webssh

# 停止服务
docker compose down

# 更新升级
git pull && docker compose build && docker compose up -d

# 备份数据
docker cp webssh-manager:/app/data ./backup-$(date +%Y%m%d)
```

## 技术栈

- **后端**: Python 3.11 · FastAPI · asyncssh · SQLAlchemy · aiosqlite
- **前端**: Vue 3 · xterm.js · Element Plus · Pinia · Vite
- **部署**: Docker · Docker Compose · Nginx
