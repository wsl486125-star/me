"""
AIoT Edge — FastAPI 应用入口
基于AIoT与边缘计算的智能网络设备感知与协同管理系统
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.database import engine, Base, SessionLocal


# ═══════════════════════════════════════════════════════════
# 后台任务：离线设备检测轮询
# ═══════════════════════════════════════════════════════════
async def offline_checker_loop():
    """每10秒检测一次是否有设备离线"""
    # 延迟导入，确保应用已完全启动
    from services.edge_engine import check_offline_devices
    from services.alert_service import create_alert, schedule_ai_review

    await asyncio.sleep(5)  # 启动后先等5秒让数据库连接就绪

    while True:
        db = SessionLocal()
        try:
            offline_devices = check_offline_devices(db)
            for device in offline_devices:
                evidence = {
                    'device_code': device.device_code,
                    'cpu_usage': None,
                    'memory_usage': None,
                    'network_latency': None,
                    'alert_type': 'offline',
                    'severity': 'critical',
                    'metric_value': 0,
                    'threshold': settings.OFFLINE_TIMEOUT_SECONDS,
                    'detected_by': '离线检测（心跳超时）',
                    'last_seen_at': device.last_seen_at.isoformat() if device.last_seen_at else None,
                }
                alert = create_alert(db, device.id, {
                    'is_anomaly': True,
                    'alert_type': 'offline',
                    'severity': 'critical',
                    'metric_value': 0,
                    'threshold': settings.OFFLINE_TIMEOUT_SECONDS,
                    'message': f'{device.name} 已离线超过{settings.OFFLINE_TIMEOUT_SECONDS}秒',
                }, metric_snapshot=evidence)
                if alert is not None:
                    schedule_ai_review(alert, SessionLocal)
            if offline_devices:
                print(f'[离线检测] 发现 {len(offline_devices)} 台设备离线')
            db.commit()
        except Exception as e:
            db.rollback()
            print(f'[离线检测] 异常: {e}')
        finally:
            db.close()

        await asyncio.sleep(10)


# ═══════════════════════════════════════════════════════════
# 轻量迁移：为已存在的 SQLite 表补充新列
# ═══════════════════════════════════════════════════════════
def run_migrations():
    """SQLite 不随 create_all 自动 ALTER 已存在表，这里手动补列。

    针对「设备分组」功能：为已存在的 devices 表补充 group_id 列。
    幂等：列已存在时跳过。新库则由 create_all 直接建全。
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)

    # devices 表：补充 group_id 列（设备分组）
    if 'devices' in insp.get_table_names():
        columns = [c['name'] for c in insp.get_columns('devices')]
        if 'group_id' not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE devices ADD COLUMN group_id INTEGER '
                    'REFERENCES device_groups(id)'
                ))
            print('[迁移] devices 表已补充 group_id 列')

    # device_metrics 表：补充 disk_usage 列（磁盘占用率）
    if 'device_metrics' in insp.get_table_names():
        columns = [c['name'] for c in insp.get_columns('device_metrics')]
        if 'disk_usage' not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE device_metrics ADD COLUMN disk_usage FLOAT'
                ))
            print('[迁移] device_metrics 表已补充 disk_usage 列')

    # devices 表：补充校园安防扩展列（分区 + 所属边缘节点）
    if 'devices' in insp.get_table_names():
        columns = [c['name'] for c in insp.get_columns('devices')]
        if 'zone' not in columns:
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE devices ADD COLUMN zone VARCHAR(50)'))
            print('[迁移] devices 表已补充 zone 列')
        if 'node_id' not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE devices ADD COLUMN node_id INTEGER '
                    'REFERENCES edge_nodes(id)'
                ))
            print('[迁移] devices 表已补充 node_id 列')

    # security_events 表：补充被合并事件ID记录，修复合并路径幂等。
    if 'security_events' in insp.get_table_names():
        columns = [c['name'] for c in insp.get_columns('security_events')]
        if 'merged_event_ids' not in columns:
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE security_events ADD COLUMN merged_event_ids TEXT'))
            print('[迁移] security_events 表已补充 merged_event_ids 列')

    # alerts 表：补充「告警处置闭环」字段（确认/处理时间、处置人、备注）。
    if 'alerts' in insp.get_table_names():
        columns = [c['name'] for c in insp.get_columns('alerts')]
        alert_new_cols = {
            'confirmed_at': 'DATETIME',
            'processing_at': 'DATETIME',
            'handler': 'VARCHAR(50)',
            'handle_note': 'TEXT',
            'evidence_snapshot': 'TEXT',
            'ai_review': 'TEXT',
        }
        for col, coltype in alert_new_cols.items():
            if col not in columns:
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE alerts ADD COLUMN {col} {coltype}'))
                print(f'[迁移] alerts 表已补充 {col} 列')


# ═══════════════════════════════════════════════════════════
# 应用初始化
# ═══════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时自动创建数据库表，启动后台检测任务"""
    Base.metadata.create_all(bind=engine)
    print('数据库表已创建/确认')
    run_migrations()

    # 启动离线检测后台循环
    task = asyncio.create_task(offline_checker_loop())
    print('离线检测任务已启动（每10秒检查一次）')

    yield

    # 关闭时取消后台任务
    task.cancel()


app = FastAPI(
    title='AIoT边缘计算设备管理系统',
    description='基于AIoT与边缘计算的智能网络设备感知与协同管理系统 — 后端API',
    version='1.0.0',
    lifespan=lifespan,
)

# ━━━ CORS 跨域配置 ━━━
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

# ━━━ 注册路由 ━━━
from routers import auth, devices, ingest, alerts, stats, groups, edge, ai, security  # noqa: E402

app.include_router(auth.router,     prefix='/api/auth',     tags=['用户认证'])
app.include_router(devices.router,  prefix='/api/devices',  tags=['设备管理'])
app.include_router(groups.router,   prefix='/api/groups',   tags=['设备分组'])
app.include_router(ingest.router,   prefix='/api/ingest',   tags=['数据采集'])
app.include_router(alerts.router,   prefix='/api/alerts',   tags=['告警管理'])
app.include_router(stats.router,    prefix='/api/stats',    tags=['统计可视化'])
app.include_router(edge.router,     prefix='/api/edge',     tags=['边缘计算'])
app.include_router(ai.router,       prefix='/api/ai',       tags=['AI助手'])
# 校园安防：pub_router 为边缘节点上报接口（开放），router 为管理查询接口（JWT）
app.include_router(security.pub_router, prefix='/api/security', tags=['校园安防·边缘上报'])
app.include_router(security.router,     prefix='/api/security', tags=['校园安防'])


@app.get('/api/health')
def health():
    """健康检查接口"""
    return {'status': 'ok'}
