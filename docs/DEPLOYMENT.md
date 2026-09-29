# 部署说明文档（Deployment Guide）

本文档说明如何将 **高校安防 AIoT 边缘协同预警系统** 从 GitHub 仓库持续部署到云服务器（Linux）。

> 项目采用「后端 FastAPI + 前端 Vue3 + SQLite」本地双服务架构，模拟设备节点通过 Docker Compose 编排。
> 本文档覆盖：环境准备、本地运行、生产部署、以及基于 GitHub Actions 的持续部署（CD）流程。

---

## 一、系统架构与端口

| 组件 | 技术栈 | 默认端口 | 说明 |
|------|--------|---------|------|
| 后端 API | FastAPI + Uvicorn | `8000` | REST 接口 + JWT 认证 + 边缘计算引擎 |
| 前端 | Vue 3 + Vite + ECharts | `5173`（dev）/ `80`（nginx） | 可视化仪表盘 |
| 数据库 | SQLite（默认）/ MySQL（可选） | — | 默认零依赖开箱即用 |
| 模拟设备 | Docker Compose（10 台 agent） | `9101~9110` | 可选，用于演示真实数据采集 |

```
浏览器 ──► Nginx (80) ──► 前端静态资源 (dist)
                              │ /api 反向代理
                              ▼
                        Uvicorn (8000) ──► SQLite / MySQL
                              ▲
Docker Compose 模拟设备 (9101~9110) ──► 采集器 device_collector.py
```

---

## 二、环境要求

- **Python** 3.10+（后端）
- **Node.js** 18+（前端构建）
- **Docker & Docker Compose**（可选，仅模拟设备节点需要）
- **Nginx**（生产环境反向代理）

---

## 三、本地开发运行

### 1. 克隆仓库

```bash
git clone https://github.com/<your-name>/me.git
cd me/aiot_edge
```

### 2. 启动后端

```bash
cd backend
cp .env.example .env        # 按需填入 DeepSeek API Key 等
python -m venv venv && source venv/bin/activate   # 建议使用虚拟环境
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

> 默认使用 SQLite（`DATABASE_TYPE=sqlite`），首次启动自动建表，无需额外配置数据库。

### 3. 启动前端

```bash
cd ../frontend
npm install
npm run dev                  # 访问 http://localhost:5173
```

> 开发模式下 Vite 已配置 `/api` 代理到 `http://localhost:8000`。

### 4. （可选）启动模拟设备节点

```bash
cd ..
docker-compose up -d --build   # 启动 10 台模拟设备
```

---

## 四、生产部署（云服务器）

### 4.1 一键部署脚本

仓库提供了自动化部署脚本 `deploy/deploy.sh`，在服务器上执行：

```bash
git clone https://github.com/<your-name>/me.git
cd me
chmod +x deploy/deploy.sh
sudo ./deploy/deploy.sh
```

脚本会自动完成：安装依赖 → 构建前端 → 配置 systemd 服务 → 配置 Nginx 反向代理 → 启动后端。

### 4.2 手动部署步骤

#### Step 1 — 后端

```bash
cd aiot_edge/backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 生产环境务必修改 JWT_SECRET_KEY 等敏感值
```

#### Step 2 — 前端构建

```bash
cd ../frontend
npm install
npm run build           # 产物在 dist/
```

#### Step 3 — 后端服务（systemd）

创建 `/etc/systemd/system/aiot-backend.service`：

```ini
[Unit]
Description=AIoT Edge Backend
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/aiot/aiot_edge/backend
ExecStart=/opt/aiot/aiot_edge/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aiot-backend
```

#### Step 4 — Nginx 反向代理

创建 `/etc/nginx/sites-available/aiot`：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端静态资源
    root /opt/aiot/aiot_edge/frontend/dist;
    index index.html;

    # SPA 路由回退
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/aiot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 五、持续部署（CI/CD）

### 5.1 GitHub Actions 工作流

仓库已内置 `.github/workflows/deploy.yml`，实现「推送 main 分支 → 自动构建 → SSH 部署到服务器」的完整流水线。

**前置准备（一次性配置）：**

1. 在 GitHub 仓库 **Settings → Secrets and variables → Actions** 中配置以下 Secrets：

| Secret 名 | 说明 |
|-----------|------|
| `DEPLOY_HOST` | 云服务器公网 IP |
| `DEPLOY_USER` | SSH 登录用户（如 `root`） |
| `DEPLOY_SSH_KEY` | 服务器私钥（`~/.ssh/id_rsa` 的内容） |
| `DEPLOY_PATH` | 部署目录（如 `/opt/aiot`） |

2. 在服务器上安装公钥：

```bash
# 将本地公钥 id_rsa.pub 追加到服务器
ssh-copy-id user@your-server-ip
```

### 5.2 部署流程

```
push to main
    │
    ├─ 后端：checkout → 安装依赖 → 运行测试
    ├─ 前端：npm install → npm run build → 产出 dist/
    │
    └─ 通过 SSH 上传产物 → 服务器执行 deploy.sh → 重启服务
```

---

## 六、环境变量说明（`backend/.env`）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_TYPE` | `sqlite` | `sqlite` / `mysql` |
| `JWT_SECRET_KEY` | — | JWT 签名密钥（**生产必须修改**） |
| `APP_PORT` | `8000` | 后端监听端口 |
| `CPU_THRESHOLD` | `85.0` | CPU 告警阈值（%） |
| `LATENCY_THRESHOLD` | `200.0` | 延迟告警阈值（ms） |
| `OFFLINE_TIMEOUT_SECONDS` | `30` | 离线判定超时（秒） |
| `DEEPSEEK_API_KEY` | — | DeepSeek AI 助手密钥 |
| `SMTP_*` | — | 邮箱验证码 SMTP 配置（可选） |

> ⚠️ `.env` 已被 `.gitignore` 排除，**严禁将真实密钥提交到仓库**。部署时在服务器上手动创建 `.env`，或通过 CI Secrets 注入。

---

## 七、安全清单

- [x] `.env`（含真实密钥）不入库
- [x] 数据库文件（`*.db`）不入库
- [x] 模型缓存（`models_cache/`）不入库
- [x] 编译产物（`__pycache__/`、`dist/`）不入库
- [ ] 生产环境更换 `JWT_SECRET_KEY`
- [ ] 生产环境使用 HTTPS（配置 TLS 证书）
- [ ] 若已误提交过密钥，立即轮换密钥并清理 git 历史

---

## 八、常见问题

**Q：后端启动报 `QueuePool limit ... timed out`？**
已通过 `database.py` 放大连接池解决；若仍有问题，检查并发采集器数量。

**Q：前端访问 API 404？**
确认 Nginx `/api/` 反向代理指向 `127.0.0.1:8000`，且后端已启动。

**Q：模拟设备无数据？**
确认 `docker-compose up -d` 已启动，且 `device_collector.py` 正在运行。
