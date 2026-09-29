#!/usr/bin/env bash
# ============================================================
# AIoT Edge — 服务器一键部署脚本
# 用途：在云服务器上完成依赖安装、前端构建、systemd 服务与 Nginx 配置
# 用法：sudo ./deploy.sh  [--deploy-path /opt/aiot]
# ============================================================
set -euo pipefail

# ---------- 可配置项 ----------
DEPLOY_PATH="${DEPLOY_PATH:-/opt/aiot}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
SERVICE_NAME="aiot-backend"
NGINX_SERVER_NAME="${NGINX_SERVER_NAME:-_}"   # 域名，_ 表示默认站点
PROJECT_DIR="$DEPLOY_PATH/me/aiot_edge"

log() { echo -e "\033[1;32m[deploy]\033[0m $*"; }
err() { echo -e "\033[1;31m[error]\033[0m $*"; exit 1; }

# ---------- 参数解析 ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --deploy-path) DEPLOY_PATH="$2"; shift 2 ;;
    --port) BACKEND_PORT="$2"; shift 2 ;;
    *) err "未知参数: $1" ;;
  esac
done

# ---------- 环境检查 ----------
command -v python3 >/dev/null 2>&1 || err "未找到 python3"
command -v node >/dev/null 2>&1 || command -v nodejs >/dev/null 2>&1 || err "未找到 Node.js"
command -v npm >/dev/null 2>&1 || err "未找到 npm"
[ -d "$PROJECT_DIR" ] || err "项目目录不存在: $PROJECT_DIR（请先 git clone）"

log "部署路径: $DEPLOY_PATH"

# ---------- 1. 后端依赖 ----------
log "安装后端依赖..."
cd "$PROJECT_DIR/backend"
if [ ! -d venv ]; then
  python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
deactivate

# ---------- 2. 后端 .env ----------
if [ ! -f "$PROJECT_DIR/backend/.env" ]; then
  log "未检测到 .env，从模板创建（请修改 JWT_SECRET_KEY 等敏感值）..."
  cp "$PROJECT_DIR/backend/.env.example" "$PROJECT_DIR/backend/.env"
fi

# ---------- 3. 前端构建 ----------
log "构建前端..."
cd "$PROJECT_DIR/frontend"
if [ ! -d node_modules ]; then
  npm install --no-audit --no-fund
fi
npm run build

# ---------- 4. systemd 服务 ----------
log "配置 systemd 服务 ($SERVICE_NAME)..."
cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=AIoT Edge Backend
After=network.target

[Service]
User=$(id -un)
WorkingDirectory=$PROJECT_DIR/backend
ExecStart=$PROJECT_DIR/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT
Restart=always
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
log "后端服务已启动 (端口 $BACKEND_PORT)"

# ---------- 5. Nginx 反向代理 ----------
if command -v nginx >/dev/null 2>&1; then
  log "配置 Nginx 反向代理..."
  cat > "/etc/nginx/sites-available/aiot" <<EOF
server {
    listen 80;
    server_name $NGINX_SERVER_NAME;

    root $PROJECT_DIR/frontend/dist;
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:$BACKEND_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
  ln -sf /etc/nginx/sites-available/aiot /etc/nginx/sites-enabled/aiot
  nginx -t && systemctl reload nginx
  log "Nginx 已配置并重载"
else
  log "未检测到 Nginx，跳过反向代理配置（前端可单独用 nginx 或其他方式托管 dist/）"
fi

# ---------- 完成 ----------
log "✅ 部署完成！"
log "  后端健康检查: http://localhost:$BACKEND_PORT/api/health"
log "  前端访问:     http://<服务器IP>/"
