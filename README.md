# AIoT Edge — 基于AIoT与边缘计算的智能网络设备感知与协同管理系统

## 项目简介

本项目为本科毕业设计，旨在构建一套基于 **AIoT（人工智能物联网）** 与 **边缘计算** 的智能网络设备感知与协同管理系统。

系统通过 Docker 容器模拟真实运行的网络设备节点（路由器、交换机、传感器等），容器内 Agent 使用 `psutil` 采集真实的 CPU、内存、网络等运行指标。数据经采集器汇聚后，由 **FastAPI 后端服务** 接收并持久化到 MySQL 数据库。核心创新点在于 **边缘计算引擎**：采用「规则引擎 + 统计分析 + 孤立森林（Isolation Forest）」三层检测体系，在数据入库前完成实时异常检测与告警判定。前端基于 **Vue 3 + ECharts** 提供实时可视化仪表盘、设备管理、告警中心等功能。

## 技术架构

```
Docker容器群（模拟设备节点，psutil采集真实负载）
    ↓
采集器 device_collector.py（定时拉取 → HTTP转发）
    ↓
FastAPI 后端（REST API + JWT认证）
    ↓
边缘计算引擎（规则+统计+孤立森林 → 异常检测）
    ↓
MySQL 数据库（设备/数据/告警持久化）
    ↓
Vue3 + ECharts 前端（实时可视化）
```

## 功能模块

| 模块 | 功能 | 接口前缀 |
|------|------|----------|
| M0 用户认证 | 注册/登录/JWT鉴权 | `/api/auth` |
| M1 设备管理 | 设备增删改查（含分区归属） | `/api/devices` |
| M2 真实数据采集 | Docker+psutil容器采集 | — |
| M3 数据采集接口 | 接收并存储运行数据 | `/api/ingest` |
| M4 边缘计算引擎 | 三层检测 → 异常告警 | — |
| M5 告警管理 | 告警记录查询 | `/api/alerts` |
| M6 可视化展示 | 实时趋势/告警面板 | `/api/stats` |
| M7 校园安防 | 边缘节点/安防事件/平面图（端—边—云协同） | `/api/security` |

## 校园安防子系统（端—边—云协同）

在原有网络设备感知体系之上，扩展了面向高校安防场景的「端—边—云」协同预警能力：

```
端（虚拟感知设备：数据集回放 + 仿真模型）
    ↓  MQTT/帧流
边（分区边缘节点：本地AI推理 + 多源融合 + 本地联动，毫秒级闭环）
    ↓  仅上报结构化事件 + 快照（原始视频不出边缘）
云（FastAPI：幂等去重 → 60s合并升级 → 四级定级 → 分级推送 → 处置闭环）
```

**核心机制**

- **多源证据融合降误报**：同分区同类型事件在 60 秒窗口内由**不同设备**先后触发时合并为一条，证据源取并集；独立证据源 ≥ 2 时自动升一级（如周界"画面人形"单源二级 → 视频+振动双源一级确认）。
- **同设备重复上报**不参与融合（视为指标抖动），独立成条，避免污染多源互证语义。
- **四级分级**：1 紧急 / 2 严重 / 3 一般 / 4 提示，级别驱动推送通道路由。
- **处置状态机**：`待确认 → 已确认 → 处置中 → 已闭环`，未闭环状态可标记 `误报`（误报样本留存用于阈值优化）。
- **幂等续传**：`event_id` 全局唯一，边缘断网恢复后重传同一事件不会重复入库。

**安防事件类型（五大场景）**

| 场景 | 事件类型 | 默认级别 |
|------|---------|---------|
| 视频行为 | 徘徊逗留 / 人员聚集 / 跌倒检测 | 2 / 3 / 2 |
| 门禁认证 | 人脸认证失败 / 黑名单布控 / 强行闯入 | 4 / 2 / 1 |
| 周界防范 | 周界越线 / 周界入侵确认 | 2 / 1 |
| 消防隐患 | 烟雾检测 / 火情确认 / 气体泄漏 / 温度异常 | 2 / 1 / 2 / 3 |
| 人流统计 | 人流拥挤预警 / 人流密度危险 | 3 / 1 |

**接口一览**

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/security/event` | 边缘上报结构化安防事件 | 开放 |
| POST | `/api/security/nodes/heartbeat` | 边缘节点心跳（代理设备在线状态） | 开放 |
| POST | `/api/security/nodes` | 注册边缘节点 | JWT |
| GET | `/api/security/nodes` | 边缘节点列表 | JWT |
| GET | `/api/security/events` | 安防事件列表（级别/类型/分区/状态筛选） | JWT |
| GET | `/api/security/events/{id}` | 事件详情与证据链 | JWT |
| PUT | `/api/security/events/{id}/status` | 处置状态机流转 | JWT |
| GET | `/api/security/map` | 校园平面图数据 | JWT |
| GET | `/api/security/stats` | 安防统计（级别/场景/24h趋势） | JWT |

**模拟器用法（无硬件仿真端+边两层）**

```bash
cd aiot_edge/collector

# 持续运行：节点心跳 + 随机低级别事件
python security_simulator.py

# 演示剧本（答辩一键复现，发送后退出）
python security_simulator.py --scenario intrusion  # 周界多源融合 → 升级一级
python security_simulator.py --scenario fire       # 烟感+视觉火情确认 → 升级一级
python security_simulator.py --scenario loitering  # 徘徊逗留（二级）
python security_simulator.py --scenario crowd      # 人流拥挤预警（三级）
python security_simulator.py --scenario face       # 门禁黑名单（二级）
python security_simulator.py --scenario gas        # 实验室气体泄漏（二级）
```

前端「校园安防」页面提供：分区态势平面图（分区按最高活动级别着色）、活动事件侧栏、事件中心（筛选/分页/状态流转），5 秒自动刷新。

## 项目结构

```
aiot_edge/
├── agent/                   # Docker容器内采集程序
│   ├── agent.py             # psutil真实采集 + stress负载控制
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml       # 多容器编排（模拟多台设备节点）
├── collector/
│   ├── device_collector.py  # 真实数据采集器
│   ├── security_simulator.py # 校园安防模拟器（端+边 仿真）
│   ├── mock_simulator.py    # 模拟数据生成器（无需Docker）
│   └── trigger_demo.py      # 答辩演示：手动触发异常负载
├── backend/                 # FastAPI 后端服务
│   ├── main.py              # 应用入口
│   ├── models.py            # SQLAlchemy 数据模型
│   ├── schemas.py           # Pydantic 校验模型
│   ├── init_db.py           # 数据库初始化
│   ├── core/                # 核心配置
│   │   ├── config.py        # 全局配置（含边缘计算阈值常量）
│   │   ├── database.py      # 数据库连接
│   │   └── security.py      # JWT认证 + 密码哈希
│   ├── routers/             # API 路由
│   │   ├── auth.py          # 用户认证
│   │   ├── devices.py       # 设备管理
│   │   ├── ingest.py        # 数据采集接收
│   │   ├── alerts.py        # 告警管理
│   │   ├── stats.py         # 可视化统计
│   │   ├── groups.py        # 设备分组
│   │   ├── edge.py          # 边缘计算中心
│   │   ├── ai.py            # AI 助手
│   │   └── security.py      # 校园安防（节点/事件/平面图/统计）
│   └── services/            # 业务逻辑
│       ├── edge_engine.py   # 边缘计算三层检测体系
│       ├── alert_service.py # 告警判定与记录
│       ├── security_service.py # 安防事件定级/融合/合并/推送
│       └── ai_service.py    # AI 助手服务
└── frontend/                # Vue3 + ECharts 前端
    └── src/
        ├── views/           # 页面（含 SecurityView 校园安防）
        ├── utils/           # 展示映射（alerts/security/status）
        └── ...
```

## 快速启动

### 1. 配置数据库

```bash
cd aiot_edge/backend
cp .env.example .env
# 编辑 .env，修改 MYSQL_USER / MYSQL_PASSWORD 等为实际值
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 初始化数据库

```bash
python init_db.py
```

### 4. 启动服务

```bash
python main.py
# 或
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

访问 http://localhost:8000/docs 查看 Swagger API 文档。
