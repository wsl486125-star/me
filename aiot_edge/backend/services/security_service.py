"""
校园安防 · 安防事件处理服务（云端慢环）

本模块是「端—边—云」协同架构中云侧的核心业务逻辑，与
edge_engine.py（设备运行指标检测）互补：

  边缘快环（模拟器/边缘节点本地完成）：
    感知 → AI推理 → 多源融合 → 本地规则判定 → 本地联动（声光/门禁/广播）
    → 仅将结构化事件上报云端（本地毫秒级闭环，原始视频不出边缘）

  云端慢环（本模块）：
    事件接收 → 幂等去重 → 合并升级 → 定级 → 分级推送路由
    → 人工处置状态机闭环 → 统计可视化

核心设计（对应论文创新点）：
  1. 多源证据融合降误报：
     同一分区同一类型事件在60秒窗口内被多台设备（不同证据源）
     先后触发时合并为一条，证据源取并集；当独立证据源数 ≥ 2 时
     自动升一级（如周界"风吹振动"单源三级疑似 → 振动+画面人形
     双源二级确认），直接回应传统周界防范"单源误报率超90%"痛点。
  2. 四级分级与推送路由：
     一级紧急/二级严重/三级一般/四级提示，级别驱动推送通道
     （弹窗/短信网关/邮件/站内/仅记录），避免告警风暴。
  3. 幂等续传：
     event_id 全局唯一，边缘断网恢复后重传同一事件不会重复入库。
"""
import json
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from models import Device, EdgeNode, SecurityEvent

# ═══════════════════════════════════════════════════════════
# 校园分区与事件类型注册表
# ═══════════════════════════════════════════════════════════

# 校园三大安防分区（平面图固定布局，未知分区动态追加）
CAMPUS_ZONES = ['校门区', '实验楼区', '周界宿舍区']

# 事件类型注册表：五大安防场景 → 事件类型 → 默认级别
#   level: 1紧急 / 2严重 / 3一般 / 4提示（与告警四级分级体系一致）
EVENT_TYPES = {
    # 场景一：视频监控与异常行为（虚拟摄像头 · 数据集剧本回放）
    'loitering':   {'label': '徘徊逗留',     'default_level': 2, 'scene': '视频行为'},
    'gathering':   {'label': '人员聚集',     'default_level': 3, 'scene': '视频行为'},
    'fall_detected': {'label': '跌倒检测',  'default_level': 2, 'scene': '视频行为'},

    # 场景二：智能门禁与身份认证（人脸图片流 · 本地比对）
    'face_denied':     {'label': '人脸认证失败', 'default_level': 4, 'scene': '门禁'},
    'face_blacklist':  {'label': '黑名单布控',   'default_level': 2, 'scene': '门禁'},
    'door_forced':     {'label': '强行闯入',     'default_level': 1, 'scene': '门禁'},

    # 场景三：周界防范与入侵检测（越线视频 + 振动/红外）
    'line_crossing':      {'label': '周界越线', 'default_level': 2, 'scene': '周界'},
    'perimeter_intrusion': {'label': '周界入侵确认', 'default_level': 1, 'scene': '周界'},

    # 场景四：火灾与安全隐患监测（烟温气体传感 + 烟火视觉）
    #   烟雾默认二级（单源高置信）；烟感+视觉双源融合后升级为一级（火情确认）
    'smoke_detected': {'label': '烟雾检测',   'default_level': 2, 'scene': '消防'},
    'fire_confirmed': {'label': '火情确认',   'default_level': 1, 'scene': '消防'},
    'gas_leak':       {'label': '气体泄漏',   'default_level': 2, 'scene': '消防'},
    'temp_abnormal':  {'label': '温度异常',   'default_level': 3, 'scene': '消防'},

    # 场景五：人流统计与拥挤预警（密集人流视频流）
    'crowd_warning': {'label': '人流拥挤预警', 'default_level': 3, 'scene': '人流'},
    'crowd_danger':  {'label': '人流密度危险', 'default_level': 1, 'scene': '人流'},

    # 设备自身状态
    'device_offline': {'label': '设备离线', 'default_level': 4, 'scene': '设备'},
}

# 告警级别 → 展示信息（前端复用同一份语义）
LEVELS = {
    1: {'label': '紧急', 'color': 'var(--danger)',  'push_channels': ['websocket', 'sms_webhook', 'email', 'screen_top']},
    2: {'label': '严重', 'color': 'var(--orange)',  'push_channels': ['websocket', 'email']},
    3: {'label': '一般', 'color': 'var(--warning)', 'push_channels': ['web_message']},
    4: {'label': '提示', 'color': 'var(--primary)', 'push_channels': ['log']},
}

# 处置状态机：状态 → 允许流转的目标状态
#   pending（待确认）→ confirmed（已确认）→ processing（处置中）→ closed（已闭环）
#   任意未闭环状态可标记 false_alarm（误报）
EVENT_STATUS_FLOW = {
    'pending':    ['confirmed', 'false_alarm'],
    'confirmed':  ['processing', 'closed', 'false_alarm'],
    'processing': ['closed', 'false_alarm'],
    'closed':     [],
    'false_alarm': [],
}

EVENT_STATUS_LABELS = {
    'pending': '待确认',
    'confirmed': '已确认',
    'processing': '处置中',
    'closed': '已闭环',
    'false_alarm': '误报',
}

# 合并窗口与升级阈值
MERGE_WINDOW_SECONDS = 60      # 同分区同类型事件合并窗口
MERGE_UPGRADE_COUNT = 3        # 窗口内合并次数达到该值时升一级
FUSION_UPGRADE_SOURCES = 2     # 独立证据源数达到该值时升一级
LOW_CONFIDENCE = 0.5           # 低于该置信度视为"疑似"，降一级


def event_type_label(event_type: str) -> str:
    """事件类型的中文标签（未知类型原样返回）"""
    return EVENT_TYPES.get(event_type, {}).get('label', event_type)


def scene_label(event_type: str) -> str:
    """事件类型所属的安防场景"""
    return EVENT_TYPES.get(event_type, {}).get('scene', '其他')


# ═══════════════════════════════════════════════════════════
# 定级与推送路由
# ═══════════════════════════════════════════════════════════

def determine_level(event_type: str, confidence: float | None,
                    sources: list) -> int:
    """云端定级规则（在边缘默认级别基础上二次校正）

    1. 基准：事件类型注册表中的默认级别；
    2. 融合升级：独立证据源数 ≥ 2 → 升一级（多源互证，最低到1级）；
    3. 低置信降级：置信度 < 0.5 → 降一级（单源疑似，最高到4级）。
    """
    base = EVENT_TYPES.get(event_type, {}).get('default_level', 3)

    level = base
    if sources and len(set(sources)) >= FUSION_UPGRADE_SOURCES:
        level = max(1, level - 1)
    if confidence is not None and confidence < LOW_CONFIDENCE:
        level = min(4, level + 1)

    return level


def push_channels_for_level(level: int) -> list:
    """按级别返回推送通道路由（无硬件条件下短信/邮件以模拟通道记录）"""
    return LEVELS.get(level, LEVELS[3])['push_channels']


def generate_event_id(prefix: str = 'EVT') -> str:
    """生成全局唯一事件ID（云端兜底用；正常由边缘侧生成）"""
    return f'{prefix}-{datetime.now().strftime("%Y%m%d%H%M%S")}-{secrets.token_hex(3)}'


def _load_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _find_duplicate_event(db: Session, event_id: str) -> SecurityEvent | None:
    direct = (
        db.query(SecurityEvent)
        .filter(SecurityEvent.event_id == event_id)
        .first()
    )
    if direct:
        return direct

    candidates = (
        db.query(SecurityEvent)
        .filter(SecurityEvent.merged_event_ids.like(f'%"{event_id}"%'))
        .all()
    )
    for event in candidates:
        if event_id in _load_list(event.merged_event_ids):
            return event
    return None


# ═══════════════════════════════════════════════════════════
# 事件接收：幂等 → 合并升级 → 定级 → 推送
# ═══════════════════════════════════════════════════════════

def ingest_event(db: Session, payload) -> dict:
    """接收边缘上报的安防事件（核心入口）

    处理流程：
      1. event_id 幂等：已入库直接返回（断网续传场景）；
      2. 解析设备/边缘节点（设备缺失时自动注册，与 ingest 体系一致）；
      3. 合并窗口查询：同分区同类型且 occurred_at 在60秒内的
         未闭环事件 → 合并（merge_count+1、证据源并集），
           - 新证据源加入导致独立源数达标 → 融合升级；
           - 合并次数 ≥ 3 → 复发升级；
      4. 新事件：云端定级 → 记录推送通道 → 入库；
      5. 返回处理结果（供边缘侧确认上报成功）。
    """
    now = datetime.now()
    occurred_at = payload.occurred_at or now

    # ━━ 1. 幂等去重（event_id 全局唯一）━━
    existing = _find_duplicate_event(db, payload.event_id)
    if existing:
        return {
            'action': 'duplicate',
            'event': existing.to_dict(),
            'message': '事件已存在（幂等去重）',
        }

    # ━━ 2. 解析设备与边缘节点 ━━
    device = db.query(Device).filter(
        Device.device_code == payload.device_code
    ).first()
    if device is None:
        device = Device(
            device_code=payload.device_code,
            name=payload.device_code,
            device_type='安防设备',
            zone=payload.zone,
            status='online',
            last_seen_at=now,
        )
        db.add(device)
        db.flush()
    else:
        # 刷新设备在线状态与分区归属（事件即心跳）
        device.status = 'online'
        device.last_seen_at = now
        if device.zone is None:
            device.zone = payload.zone

    node = db.query(EdgeNode).filter(
        EdgeNode.node_code == payload.node_code
    ).first()
    if node is not None and device.node_id is None:
        device.node_id = node.id

    # ━━ 3. 合并窗口查询（同分区 + 同类型 + 不同设备 + 60秒内 + 未闭环）━━
    #   合并的语义是「多源互证」：必须来自不同物理设备的不同证据源，
    #   例如 CAM-FENCE-01(视频) 与 VIB-FENCE-01(振动) 先后触发越线。
    #   同一台设备在窗口内的重复上报属于"指标抖动"，独立成条，
    #   由 merge_count 之外的重复条数自然体现，不参与融合升级判定。
    window_start = occurred_at - timedelta(seconds=MERGE_WINDOW_SECONDS)
    merge_target = (
        db.query(SecurityEvent)
        .filter(
            SecurityEvent.zone == payload.zone,
            SecurityEvent.event_type == payload.event_type,
            SecurityEvent.device_id != device.id,
            SecurityEvent.status.in_(['pending', 'confirmed', 'processing']),
            SecurityEvent.occurred_at >= window_start,
            SecurityEvent.occurred_at <= occurred_at + timedelta(seconds=MERGE_WINDOW_SECONDS),
        )
        .order_by(SecurityEvent.occurred_at.desc())
        .first()
    )

    if merge_target is not None:
        return _merge_event(db, merge_target, payload, device, occurred_at)

    # ━━ 4. 新事件：定级 → 推送路由 → 入库 ━━
    level = determine_level(payload.event_type, payload.confidence, payload.sources)
    channels = push_channels_for_level(level)

    event = SecurityEvent(
        event_id=payload.event_id,
        device_id=device.id,
        node_id=node.id if node else None,
        event_type=payload.event_type,
        level=level,
        zone=payload.zone,
        confidence=payload.confidence,
        sources=json.dumps(payload.sources, ensure_ascii=False),
        local_actions=json.dumps(payload.local_actions, ensure_ascii=False),
        local_latency_ms=payload.local_latency_ms,
        message=payload.message or event_type_label(payload.event_type),
        status='pending',
        merge_count=1,
        merged_event_ids=json.dumps([], ensure_ascii=False),
        pushed_channels=json.dumps(channels),
        occurred_at=occurred_at,
        created_at=now,
        updated_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return {
        'action': 'created',
        'event': event.to_dict(),
        'push_channels': channels,
        'message': f'事件已入库并推送（{LEVELS[level]["label"]}）',
    }


def _merge_event(db: Session, target: SecurityEvent, payload, device, occurred_at) -> dict:
    """合并窗口命中：合并计数、证据源并集、融合/复发升级

    这是"多源证据融合降误报"的关键路径：
      例：CAM-FENCE-01 上报 line_crossing(sources=[video], level=2)
          2秒后 VIB-FENCE-01 上报 line_crossing(sources=[vibration])
          → 合并为一条，sources=[video, vibration]，独立源数=2 → 升级为一级。
    """
    old_sources = _load_list(target.sources)
    merged_sources = list(dict.fromkeys(old_sources + list(payload.sources)))

    # 升级判定：独立证据源达标 或 合并次数达到阈值
    upgraded = False
    new_level = target.level
    if len(set(merged_sources)) >= FUSION_UPGRADE_SOURCES and len(set(old_sources)) < FUSION_UPGRADE_SOURCES:
        new_level = max(1, new_level - 1)
        upgraded = True
    target.merge_count += 1
    if target.merge_count >= MERGE_UPGRADE_COUNT and target.merge_count - 1 < MERGE_UPGRADE_COUNT:
        new_level = max(1, new_level - 1)
        upgraded = True

    target.level = new_level
    target.sources = json.dumps(merged_sources, ensure_ascii=False)
    # 本地联动动作也取并集（保留完整处置证据链）
    old_actions = _load_list(target.local_actions)
    merged_actions = list(dict.fromkeys(old_actions + list(payload.local_actions)))
    target.local_actions = json.dumps(merged_actions, ensure_ascii=False)
    merged_event_ids = list(dict.fromkeys(_load_list(target.merged_event_ids) + [payload.event_id]))
    target.merged_event_ids = json.dumps(merged_event_ids, ensure_ascii=False)
    if payload.confidence is not None:
        # 置信度取较高值（多源互证提升整体置信度）
        target.confidence = max(target.confidence or 0, payload.confidence)
    # 事件说明追加合并来源，并显式标注多源互证结果（论文可解释性）
    source_labels = '/'.join(merged_sources)
    merge_note = (
        f'；多源互证：并入 {device.device_code} 的同类事件'
        f'（证据源 {source_labels}，第{target.merge_count}次）'
    )
    if not (target.message or '').endswith(merge_note):
        target.message = (target.message or '') + merge_note
    # 升级后按新级别重算推送通道（只增不减）
    channels = push_channels_for_level(new_level)
    old_channels = _load_list(target.pushed_channels)
    target.pushed_channels = json.dumps(list(dict.fromkeys(old_channels + channels)))
    target.updated_at = occurred_at

    db.commit()
    db.refresh(target)

    return {
        'action': 'merged',
        'event': target.to_dict(),
        'push_channels': channels,
        'message': f'事件已合并（第{target.merge_count}次）' + ('并升级' if upgraded else ''),
    }


# ═══════════════════════════════════════════════════════════
# 状态机流转
# ═══════════════════════════════════════════════════════════

def transition_status(db: Session, event_id: int, new_status: str, note: str | None = None) -> tuple:
    """处置状态机流转（校验合法迁移）

    返回 (成功?, 事件, 错误信息)。
    """
    if new_status not in EVENT_STATUS_FLOW:
        return False, None, f'未知状态: {new_status}'

    event = db.query(SecurityEvent).filter(SecurityEvent.id == event_id).first()
    if event is None:
        return False, None, '事件不存在'

    allowed = EVENT_STATUS_FLOW.get(event.status, [])
    if new_status not in allowed:
        return False, event, f'不允许从「{EVENT_STATUS_LABELS[event.status]}」流转到「{EVENT_STATUS_LABELS.get(new_status, new_status)}」'

    event.status = new_status
    if note:
        event.message = (event.message or '') + f'；处置备注: {note}'
    event.updated_at = datetime.now()
    db.commit()
    db.refresh(event)
    return True, event, None


# ═══════════════════════════════════════════════════════════
# 统计聚合（校园平面图 / 大屏）
# ═══════════════════════════════════════════════════════════

def campus_map_data(db: Session) -> dict:
    """校园平面图数据：各分区设备数、事件数、最高活动级别

    活动事件 = 未闭环且非误报的事件（pending/confirmed/processing）。
    分区级别取活动事件中的最高级别（1最高），无活动事件为 None。
    """
    zones = list(CAMPUS_ZONES)
    # 动态追加未知分区（保证兼容手工测试数据）
    extra = [
        r[0] for r in db.query(Device.zone).filter(Device.zone.isnot(None)).distinct().all()
        if r[0] not in zones
    ]
    zones.extend(extra)

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    zone_items = []
    for zone in zones:
        devices = db.query(Device).filter(Device.zone == zone).all()
        active_events = (
            db.query(SecurityEvent)
            .filter(
                SecurityEvent.zone == zone,
                SecurityEvent.status.in_(['pending', 'confirmed', 'processing']),
            )
            .all()
        )
        today_count = (
            db.query(SecurityEvent)
            .filter(
                SecurityEvent.zone == zone,
                SecurityEvent.occurred_at >= today_start,
            )
            .count()
        )
        # 级别分布：键显式转为字符串，避免 JSON 序列化后前端取值类型不一致
        level_dist = {str(lv): 0 for lv in (1, 2, 3, 4)}
        for ev in active_events:
            key = str(ev.level)
            level_dist[key] = level_dist.get(key, 0) + 1
        max_level = min(active_events, key=lambda e: e.level).level if active_events else None

        zone_items.append({
            'zone': zone,
            'device_count': len(devices),
            'online_devices': sum(1 for d in devices if d.status == 'online'),
            'active_events': len(active_events),
            'today_events': today_count,
            'level_distribution': level_dist,
            'max_active_level': max_level,
        })

    return {'zones': zone_items, 'generated_at': now.isoformat()}
