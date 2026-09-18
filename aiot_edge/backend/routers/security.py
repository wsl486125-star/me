"""
AIoT Edge — 校园安防路由

「端—边—云」协同架构的云侧接口：
  开放接口（与 /api/ingest 一致的机器上报风格，无需JWT）：
    POST /event            边缘节点上报结构化安防事件（幂等/合并/定级/推送）
    POST /nodes/heartbeat  边缘节点心跳（附带下属设备在线清单）
  管理接口（JWT认证）：
    GET  /nodes            边缘节点列表（含下属设备数）
    GET  /events           安防事件列表（级别/类型/分区/状态筛选 + 分页）
    GET  /events/{id}      事件详情
    PUT  /events/{id}/status  处置状态机流转（确认/处置/闭环/误报）
    GET  /map              校园平面图数据（分区着色/事件统计）
    GET  /stats            安防事件统计（级别分布/类型分布/趋势）
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from core.database import get_db
from core.security import get_current_user
from models import Device, EdgeNode, SecurityEvent
from schemas import (
    NodeCreate, NodeHeartbeat, SecurityEventIngest, EventStatusUpdate,
)
from services.security_service import (
    EVENT_STATUS_LABELS,
    EVENT_TYPES,
    LEVELS,
    ingest_event,
    transition_status,
    campus_map_data,
    event_type_label,
    scene_label,
)

# 机器上报接口（无需JWT，与数据采集接口风格一致）
pub_router = APIRouter()
# 管理查询接口（JWT认证）
router = APIRouter(dependencies=[Depends(get_current_user)])

# 节点离线判定：超过该时长无心跳视为离线
NODE_OFFLINE_SECONDS = 60


# ═══════════════════════════════════════════════════════════
# 开放接口 · 边缘上报
# ═══════════════════════════════════════════════════════════

@pub_router.post('/event')
def receive_event(payload: SecurityEventIngest, db: Session = Depends(get_db)):
    """接收边缘节点上报的结构化安防事件

    数据来源：边缘节点（Docker容器模拟）在本地完成 AI 推理、
    多源融合与规则判定后上报。云端完成幂等去重 → 60秒窗口
    合并升级 → 四级定级 → 分级推送路由。

    返回 action：
      created  新事件入库并推送
      merged   合并进已有事件（可能触发升级）
      duplicate 幂等去重（断网续传重复上报）
    """
    # 事件类型白名单校验（未知类型拒绝，防止脏数据）
    if payload.event_type not in EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'未知事件类型: {payload.event_type}，'
                   f'支持: {", ".join(EVENT_TYPES.keys())}',
        )

    result = ingest_event(db, payload)
    return {
        'success': True,
        'action': result['action'],
        'message': result['message'],
        'event': result['event'],
    }


@pub_router.post('/nodes/heartbeat')
def node_heartbeat(payload: NodeHeartbeat, db: Session = Depends(get_db)):
    """边缘节点心跳上报

    心跳携带下属在线设备编号列表，云端统一刷新设备在线状态
    （边缘节点代理上报，安防设备无需单独心跳）。
    节点停止心跳60秒后由 /nodes 查询侧判定为离线。
    """
    node = db.query(EdgeNode).filter(
        EdgeNode.node_code == payload.node_code
    ).first()
    if node is None:
        raise HTTPException(status_code=404, detail=f'边缘节点 {payload.node_code} 未注册')

    now = datetime.now()
    node.status = 'online'
    node.last_heartbeat_at = now

    # 刷新下属设备的在线状态
    refreshed = 0
    for code in payload.devices:
        device = db.query(Device).filter(Device.device_code == code).first()
        if device:
            device.status = 'online'
            device.last_seen_at = now
            if device.node_id is None:
                device.node_id = node.id
            refreshed += 1

    db.commit()
    return {
        'success': True,
        'message': f'节点 {node.name} 心跳已更新（刷新 {refreshed} 台设备状态）',
    }


# ═══════════════════════════════════════════════════════════
# 管理接口 · 节点 / 事件 / 平面图 / 统计
# ═══════════════════════════════════════════════════════════

@router.post('/nodes', status_code=status.HTTP_201_CREATED)
def create_node(payload: NodeCreate, db: Session = Depends(get_db)):
    """注册边缘节点（模拟器启动时调用，幂等：已存在返回现有节点）"""
    existing = db.query(EdgeNode).filter(
        EdgeNode.node_code == payload.node_code
    ).first()
    if existing:
        return {**existing.to_dict(), 'message': '节点已存在，跳过注册'}

    node = EdgeNode(
        node_code=payload.node_code,
        name=payload.name,
        zone=payload.zone,
        description=payload.description,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node.to_dict()


@router.get('/nodes')
def list_nodes(db: Session = Depends(get_db)):
    """边缘节点列表（含下属设备数、心跳超时自动判离线）"""
    nodes = db.query(EdgeNode).order_by(EdgeNode.id).all()
    timeout = timedelta(seconds=NODE_OFFLINE_SECONDS)

    items = []
    for node in nodes:
        # 心跳超时判定（查询侧兜底，与后台离线检测互补）
        if (
            node.status == 'online'
            and node.last_heartbeat_at
            and datetime.now() - node.last_heartbeat_at > timeout
        ):
            node.status = 'offline'
            db.commit()

        devices = db.query(Device).filter(Device.node_id == node.id).all()
        item = node.to_dict()
        item['device_count'] = len(devices)
        item['online_devices'] = sum(1 for d in devices if d.status == 'online')
        items.append(item)

    return {
        'items': items,
        'online_count': sum(1 for n in items if n['status'] == 'online'),
    }


@router.get('/events')
def list_events(
    level: int = Query(None, ge=1, le=4, description='级别筛选(1紧急/2严重/3一般/4提示)'),
    event_type: str = Query(None, description='事件类型筛选'),
    zone: str = Query(None, description='分区筛选'),
    status_filter: str = Query('all', alias='status', description='处置状态: pending/confirmed/processing/closed/false_alarm/all/active'),
    device_id: int = Query(None, description='按设备ID筛选'),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """安防事件列表（分页，附带类型中文标签）"""
    query = db.query(SecurityEvent)

    if level is not None:
        query = query.filter(SecurityEvent.level == level)
    if event_type:
        query = query.filter(SecurityEvent.event_type == event_type)
    if zone:
        query = query.filter(SecurityEvent.zone == zone)
    if device_id is not None:
        query = query.filter(SecurityEvent.device_id == device_id)

    if status_filter == 'active':
        query = query.filter(SecurityEvent.status.in_(['pending', 'confirmed', 'processing']))
    elif status_filter != 'all':
        query = query.filter(SecurityEvent.status == status_filter)

    total = query.count()
    events = (
        query.order_by(desc(SecurityEvent.occurred_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    items = []
    for ev in events:
        item = ev.to_dict()
        item['type_label'] = event_type_label(ev.event_type)
        item['scene'] = scene_label(ev.event_type)
        item['status_label'] = EVENT_STATUS_LABELS.get(ev.status, ev.status)
        items.append(item)

    return {
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': max(1, (total + per_page - 1) // per_page),
    }


@router.get('/events/{event_id}')
def get_event(event_id: int, db: Session = Depends(get_db)):
    """安防事件详情（含完整证据链：证据源/本地联动/推送通道/合并过程）"""
    event = db.query(SecurityEvent).filter(SecurityEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail='事件不存在')

    item = event.to_dict()
    item['type_label'] = event_type_label(event.event_type)
    item['scene'] = scene_label(event.event_type)
    item['status_label'] = EVENT_STATUS_LABELS.get(event.status, event.status)
    return item


@router.put('/events/{event_id}/status')
def update_event_status(
    event_id: int,
    payload: EventStatusUpdate,
    db: Session = Depends(get_db),
):
    """处置状态机流转

    合法迁移：pending → confirmed → processing → closed，
    未闭环状态可标记 false_alarm（误报）。
    """
    ok, event, err = transition_status(db, event_id, payload.status, payload.note)
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    item = event.to_dict()
    item['type_label'] = event_type_label(event.event_type)
    item['status_label'] = EVENT_STATUS_LABELS.get(event.status, event.status)
    return {'message': f'事件已流转为「{item["status_label"]}」', 'success': True, 'event': item}


@router.get('/map')
def campus_map(db: Session = Depends(get_db)):
    """校园平面图数据（分区设备/事件统计 + 最高活动级别）"""
    return campus_map_data(db)


@router.get('/stats')
def security_stats(db: Session = Depends(get_db)):
    """安防事件统计（级别分布/场景分布/24小时趋势/处置概况）"""
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since_24h = now - timedelta(hours=24)

    # 级别分布（今日）
    #   注意：Python 字典的整型键经 JSON 序列化后会变成字符串（"1"/"2"...），
    #   前端 level_distribution[1] 将取不到值，故此处显式转成字符串键，
    #   前端统一用 level_distribution[String(level)] 访问。
    level_rows = (
        db.query(SecurityEvent.level, func.count(SecurityEvent.id))
        .filter(SecurityEvent.occurred_at >= today_start)
        .group_by(SecurityEvent.level)
        .all()
    )
    level_dist = {str(lv): 0 for lv in (1, 2, 3, 4)}
    for lv, cnt in level_rows:
        level_dist[str(lv)] = cnt

    # 场景分布（今日）
    scene_rows = (
        db.query(SecurityEvent.event_type, func.count(SecurityEvent.id))
        .filter(SecurityEvent.occurred_at >= today_start)
        .group_by(SecurityEvent.event_type)
        .all()
    )
    type_dist = [
        {'event_type': t, 'label': event_type_label(t), 'count': cnt}
        for t, cnt in scene_rows
    ]

    # 24小时逐小时趋势（按级别）
    trend_rows = (
        db.query(SecurityEvent)
        .filter(SecurityEvent.occurred_at >= since_24h)
        .order_by(SecurityEvent.occurred_at.asc())
        .all()
    )
    trend = []
    for hour in range(24):
        h_start = since_24h + timedelta(hours=hour)
        h_end = h_start + timedelta(hours=1)
        bucket = [e for e in trend_rows if h_start <= e.occurred_at < h_end]
        trend.append({
            'hour': h_start.strftime('%H:00'),
            'level_1': sum(1 for e in bucket if e.level == 1),
            'level_2': sum(1 for e in bucket if e.level == 2),
            'level_3': sum(1 for e in bucket if e.level == 3),
            'level_4': sum(1 for e in bucket if e.level == 4),
            'total': len(bucket),
        })

    # 处置概况
    status_rows = (
        db.query(SecurityEvent.status, func.count(SecurityEvent.id))
        .group_by(SecurityEvent.status)
        .all()
    )
    status_dist = {k: 0 for k in EVENT_STATUS_LABELS}
    for s, cnt in status_rows:
        status_dist[s] = cnt

    return {
        'today_total': sum(level_dist.values()),
        'level_distribution': level_dist,
        'type_distribution': type_dist,
        'trend_24h': trend,
        'status_distribution': status_dist,
        'pending_count': status_dist.get('pending', 0),
        'levels': {lv: info['label'] for lv, info in LEVELS.items()},
    }
