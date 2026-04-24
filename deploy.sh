#!/bin/bash
# WebSSH Manager - 一键部署脚本（直接部署，无需 Docker）
set -e

INSTALL_DIR="/opt/webssh-manager"
SERVICE_NAME="webssh-manager"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[✓] $1${NC}"; }
warn() { echo -e "${YELLOW}[!] $1${NC}"; }
err() { echo -e "${RED}[✗] $1${NC}"; exit 1; }
info() { echo -e "${BLUE}[i] $1${NC}"; }

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     WebSSH Manager 一键部署脚本       ║"
echo "║     （直接部署模式 · 无需 Docker）     ║"
echo "╚══════════════════════════════════════╝"
echo ""

# 检查 root
[[ $EUID -eq 0 ]] || err "请以 root 用户运行此脚本"

# 停掉可能正在运行的旧服务
systemctl stop "$SERVICE_NAME" 2>/dev/null || true

# 读取配置
read -p "请输入管理员用户名 [默认: admin]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}

read -s -p "请输入管理员密码: " ADMIN_PWD
echo ""
[[ -z "$ADMIN_PWD" ]] && err "管理员密码不能为空，请重新运行"

read -p "请输入访问端口 [默认: 8080]: " APP_PORT
APP_PORT=${APP_PORT:-8080}

# 生成密钥
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -hex 32)

# 检测系统类型并安装依赖
info "安装系统依赖..."
if command -v apt-get &>/dev/null; then
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv python3-full nodejs npm libssl-dev 2>/dev/null
    log "apt 依赖安装完成"
elif command -v yum &>/dev/null || command -v dnf &>/dev/null; then
    yum install -y python3 python3-pip nodejs npm openssl-devel 2>/dev/null || \
    dnf install -y python3 python3-pip nodejs npm openssl-devel 2>/dev/null
    log "yum/dnf 依赖安装完成"
else
    err "不支持的系统，请手动安装 python3、pip、nodejs、npm"
fi

# 确保 node 和 npm 可用
if ! command -v node &>/dev/null; then
    warn "node 未找到，尝试通过 npm 安装..."
    curl -fsSL https://rpm.nodesource.com/setup_20.x | bash - 2>/dev/null || \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - 2>/dev/null || true
fi
log "Node $(node -v 2>/dev/null || echo '未知'), npm $(npm -v 2>/dev/null || echo '未知')"

# 复制项目文件
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR/." "$INSTALL_DIR/"
cd "$INSTALL_DIR"

# 生成 .env 文件
cat > "$INSTALL_DIR/.env" << EOF
# WebSSH Manager 配置文件
# 生成于 $(date)

SECRET_KEY=$SECRET_KEY
ENCRYPTION_KEY=$ENCRYPTION_KEY
ADMIN_USERNAME=$ADMIN_USER
ADMIN_PASSWORD=$ADMIN_PWD
PORT=$APP_PORT
EOF
chmod 600 "$INSTALL_DIR/.env"
log "配置文件已生成"

# 安装后端 Python 依赖（使用 venv 避免 PEP 668 限制）
info "安装 Python 依赖..."
cd "$INSTALL_DIR/backend"
python3 -m venv "$INSTALL_DIR/backend/venv"
source "$INSTALL_DIR/backend/venv/bin/activate"
pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || \
pip install -r requirements.txt -q
deactivate
log "Python 依赖安装完成（venv）"

# 构建前端
info "构建前端..."
cd "$INSTALL_DIR/frontend"
npm install --registry=https://registry.npmmirror.com --silent 2>/dev/null
npm run build --silent 2>/dev/null
log "前端构建完成"

# 创建 systemd 服务
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << SVC
[Unit]
Description=WebSSH Manager
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR/backend
ExecStart=$INSTALL_DIR/backend/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port $APP_PORT --workers 1
Environment=SECRET_KEY=$SECRET_KEY
Environment=ENCRYPTION_KEY=$ENCRYPTION_KEY
Environment=ADMIN_USERNAME=$ADMIN_USER
Environment=ADMIN_PASSWORD=$ADMIN_PWD
Environment=PORT=$APP_PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SVC

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"
log "服务已启动"

# 等待启动
info "等待服务启动..."
for i in $(seq 1 15); do
    if curl -sf "http://localhost:$APP_PORT/api/health" &>/dev/null; then
        log "服务启动成功！"
        break
    fi
    sleep 1
    echo -n "."
done
echo ""

# 防火墙
if command -v ufw &>/dev/null; then
    ufw allow "$APP_PORT/tcp" &>/dev/null || true
elif command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port="$APP_PORT/tcp" &>/dev/null || true
    firewall-cmd --reload &>/dev/null || true
fi

# 获取公网 IP
PUBLIC_IP=$(curl -sf https://api.ipify.org 2>/dev/null || curl -sf https://ifconfig.me 2>/dev/null || echo "你的服务器IP")

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║              🎉 部署成功！                        ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║  访问地址: http://$PUBLIC_IP:$APP_PORT"
echo "║  用户名:   $ADMIN_USER"
echo "║  密码:     已设置（不显示）"
echo "║"
echo "║  管理命令:"
echo "║    查看状态: systemctl status $SERVICE_NAME"
echo "║    查看日志: journalctl -u $SERVICE_NAME -f"
echo "║    重启:     systemctl restart $SERVICE_NAME"
echo "║    停止:     systemctl stop $SERVICE_NAME"
echo "╚══════════════════════════════════════════════════╝"
echo ""
