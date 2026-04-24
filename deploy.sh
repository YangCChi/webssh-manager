#!/bin/bash
# WebSSH Manager - 一键部署脚本（适用于 Linux Ubuntu/CentOS/Debian）
set -e

INSTALL_DIR="/opt/webssh-manager"
DATA_DIR="/data/webssh"
SERVICE_NAME="webssh-manager"

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
echo "╚══════════════════════════════════════╝"
echo ""

# 检查 root
[[ $EUID -eq 0 ]] || err "请以 root 用户运行此脚本"

# 检查 Docker
if ! command -v docker &> /dev/null; then
    warn "Docker 未安装，开始安装..."
    curl -fsSL https://get.docker.com | sh || \
    curl -fsSL https://get.docker.com | sed 's|download.docker.com|mirrors.aliyun.com/docker-ce|g' | sh
    systemctl enable docker && systemctl start docker
    log "Docker 安装完成"
fi

# 检查 Docker Compose
if ! command -v docker &> /dev/null || ! docker compose version &> /dev/null; then
    warn "Docker Compose 插件未安装..."
    apt-get install -y docker-compose-plugin 2>/dev/null || \
    yum install -y docker-compose-plugin 2>/dev/null || true
fi

# 读取配置
read -p "请输入管理员用户名 [默认: admin]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}

read -s -p "请输入管理员密码 [默认: 请自行设置]: " ADMIN_PWD
echo ""
[[ -z "$ADMIN_PWD" ]] && err "管理员密码不能为空，请重新运行"

read -p "请输入访问端口 [默认: 8080]: " APP_PORT
APP_PORT=${APP_PORT:-8080}

# 生成密钥
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -hex 32)

# 创建目录
mkdir -p "$INSTALL_DIR" "$DATA_DIR/data" "$DATA_DIR/logs"

# 复制项目文件
cp -r . "$INSTALL_DIR/"

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

# 修改 docker-compose.yml 中的卷挂载为实际目录
sed -i "s|webssh-data:|webssh-data:\n    driver_opts:\n      type: none\n      device: $DATA_DIR/data\n      o: bind|" \
    "$INSTALL_DIR/docker-compose.yml" 2>/dev/null || true

# 构建并启动
cd "$INSTALL_DIR"
docker compose --env-file .env build
docker compose --env-file .env up -d webssh

# 等待启动
info "等待服务启动..."
for i in {1..30}; do
    if curl -sf "http://localhost:$APP_PORT/api/health" &>/dev/null; then
        log "服务启动成功！"
        break
    fi
    sleep 2
    echo -n "."
done
echo ""

# 防火墙（可选）
if command -v ufw &> /dev/null; then
    ufw allow "$APP_PORT/tcp" &>/dev/null || true
elif command -v firewall-cmd &> /dev/null; then
    firewall-cmd --permanent --add-port="$APP_PORT/tcp" &>/dev/null || true
    firewall-cmd --reload &>/dev/null || true
fi

# 获取公网 IP
PUBLIC_IP=$(curl -sf https://api.ipify.org 2>/dev/null || curl -sf https://ifconfig.me 2>/dev/null || echo "YOUR_SERVER_IP")

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║              🎉 部署成功！                        ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║  访问地址: http://$PUBLIC_IP:$APP_PORT"
echo "║  用户名:   $ADMIN_USER"
echo "║  密码:     已设置（不显示）"
echo "║"
echo "║  配置文件: $INSTALL_DIR/.env"
echo "║  数据目录: $DATA_DIR"
echo "║"
echo "║  管理命令:"
echo "║    启动: cd $INSTALL_DIR && docker compose up -d"
echo "║    停止: cd $INSTALL_DIR && docker compose down"
echo "║    日志: cd $INSTALL_DIR && docker compose logs -f"
echo "║    更新: cd $INSTALL_DIR && git pull && docker compose build && docker compose up -d"
echo "╚══════════════════════════════════════════════════╝"
echo ""
warn "建议配置 HTTPS 以确保安全，参考 docker/nginx.conf"
