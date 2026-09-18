"""
AIoT Edge — 数据库模型定义
核心表：User（用户）、Device（设备）、DeviceMetric（运行数据）、Alert（告警记录）
安防扩展表：EdgeNode（边缘节点）、SecurityEvent（安防事件）
"""
import json
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from core.database import Base


def _json_list(value):
    """Return a JSON array column as a list without letting dirty data break APIs."""
    if not value:
        return []
    try:
        data = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


class User(Base):
    """用户表 — 系统登录认证"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='用户ID')
    username = Column(String(50), unique=True, nullable=False, comment='用户名')
    email = Column(String(100), unique=True, nullable=False, comment='邮箱地址')
    hashed_password = Column(String(255), nullable=False, comment='哈希密码')
    is_active = Column(Boolean, default=True, comment='是否激活')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    # 关系
    devices = relationship('Device', back_populates='owner')
    device_groups = relationship('DeviceGroup', back_populates='owner')

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Device(Base):
    """设备表 — 管理的网络设备节点"""
    __tablename__ = 'devices'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='设备ID')
    device_code = Column(String(50), unique=True, nullable=False, comment='设备编号（如DEV-001）')
    name = Column(String(100), nullable=False, comment='设备名称')
    device_type = Column(String(50), nullable=False, comment='设备类型（路由器/交换机/传感器/虚拟摄像头等）')
    location = Column(String(200), nullable=True, comment='部署位置')
    zone = Column(String(50), nullable=True, comment='所属校园分区（校门区/实验楼区/周界宿舍区）')
    node_id = Column(Integer, ForeignKey('edge_nodes.id'), nullable=True, comment='所属边缘节点ID')
    status = Column(String(20), default='offline', comment='在线状态（online/offline）')
    last_seen_at = Column(DateTime, nullable=True, comment='最近上报时间')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True, comment='所属用户ID')
    group_id = Column(Integer, ForeignKey('device_groups.id'), nullable=True, comment='所属分组ID')

    # 关系
    owner = relationship('User', back_populates='devices')
    group = relationship('DeviceGroup', back_populates='devices')
    node = relationship('EdgeNode', back_populates='devices')
    metrics = relationship('DeviceMetric', back_populates='device')
    alerts = relationship('Alert', back_populates='device')

    def to_dict(self):
        return {
            'id': self.id,
            'device_code': self.device_code,
            'name': self.name,
            'device_type': self.device_type,
            'location': self.location,
            'zone': self.zone,
            'node_id': self.node_id,
            'status': self.status,
            'last_seen_at': self.last_seen_at.isoformat() if self.last_seen_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'owner_id': self.owner_id,
            'group_id': self.group_id,
        }


class DeviceGroup(Base):
    """设备分组表 — 设备协同管理的分组单元

    用于将多个网络设备划入同一分组，实现分组级的运行状态总览与协同处置，
    是「协同管理」能力的载体。
    """
    __tablename__ = 'device_groups'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='分组ID')
    name = Column(String(100), nullable=False, comment='分组名称')
    description = Column(String(200), nullable=True, comment='分组描述')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True, comment='所属用户ID')

    # 关系
    owner = relationship('User', back_populates='device_groups')
    devices = relationship('Device', back_populates='group')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'owner_id': self.owner_id,
        }


class DeviceMetric(Base):
    """设备运行数据表 — Docker容器真实采集的运行指标
    注意：不设置 temperature 字段，因为数据来自Docker容器内的psutil真实采集，
    容器内没有真实温度传感器，伪造该字段会削弱"真实数据支撑"这一卖点。
    """
    __tablename__ = 'device_metrics'
    __table_args__ = (
        Index('idx_device_collected', 'device_id', 'collected_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='记录ID')
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False, comment='设备ID')
    cpu_usage = Column(Float, nullable=True, comment='CPU使用率(%)')
    memory_usage = Column(Float, nullable=True, comment='内存使用率(%)')
    network_latency = Column(Float, nullable=True, comment='网络延迟(ms)')
    bandwidth_usage = Column(Float, nullable=True, comment='带宽使用(Mbps)')
    disk_usage = Column(Float, nullable=True, comment='磁盘使用率(%)')
    collected_at = Column(DateTime, default=datetime.now, comment='采集时间')

    # 关系
    device = relationship('Device', back_populates='metrics')

    def to_dict(self):
        return {
            'id': self.id,
            'device_id': self.device_id,
            'cpu_usage': self.cpu_usage,
            'memory_usage': self.memory_usage,
            'network_latency': self.network_latency,
            'bandwidth_usage': self.bandwidth_usage,
            'disk_usage': self.disk_usage,
            'collected_at': self.collected_at.isoformat() if self.collected_at else None,
        }


class Alert(Base):
    """告警记录表 — 边缘计算引擎检测到的异常事件

    状态机（处置闭环）：
      firing(待处理) → confirmed(已确认) → processing(处理中) → resolved(已解决/closed)
                                                          ↘ false_alarm(误报)
    """
    __tablename__ = 'alerts'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='告警ID')
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False, comment='设备ID')
    alert_type = Column(String(50), nullable=False, comment='告警类型（cpu_high/latency_high/offline等）')
    severity = Column(String(20), nullable=False, comment='严重程度（critical/high/medium/low）')
    metric_value = Column(Float, nullable=True, comment='触发时的指标值')
    threshold = Column(Float, nullable=True, comment='阈值')
    message = Column(Text, nullable=True, comment='告警说明')
    status = Column(String(20), default='firing', comment='状态（firing/confirmed/processing/resolved/closed/false_alarm）')
    triggered_at = Column(DateTime, default=datetime.now, comment='触发时间')
    confirmed_at = Column(DateTime, nullable=True, comment='确认时间')
    processing_at = Column(DateTime, nullable=True, comment='开始处理时间')
    resolved_at = Column(DateTime, nullable=True, comment='解决/关闭时间')
    handler = Column(String(50), nullable=True, comment='处置人')
    handle_note = Column(Text, nullable=True, comment='处置备注')
    # 证据快照（软件模拟"现场取证"，替代真实抓拍图片）
    evidence_snapshot = Column(Text, nullable=True, comment='触发时设备指标快照(JSON)')
    # AI 语义复核（DeepSeek 生成的异常原因解读）
    ai_review = Column(Text, nullable=True, comment='AI语义复核·异常原因解读')

    # 关系
    device = relationship('Device', back_populates='alerts')

    def _handle_duration(self):
        """处置时长（秒）：从触发到闭环的耗时，用于闭环率/效率统计"""
        end = self.resolved_at
        if end and self.triggered_at:
            return max(0, int((end - self.triggered_at).total_seconds()))
        return None

    def _evidence(self):
        """解析证据快照 JSON 为 dict"""
        if not self.evidence_snapshot:
            return None
        try:
            return json.loads(self.evidence_snapshot)
        except (TypeError, json.JSONDecodeError):
            return None

    def to_dict(self):
        return {
            'id': self.id,
            'device_id': self.device_id,
            'alert_type': self.alert_type,
            'severity': self.severity,
            'metric_value': self.metric_value,
            'threshold': self.threshold,
            'message': self.message,
            'status': self.status,
            'triggered_at': self.triggered_at.isoformat() if self.triggered_at else None,
            'confirmed_at': self.confirmed_at.isoformat() if self.confirmed_at else None,
            'processing_at': self.processing_at.isoformat() if self.processing_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'handler': self.handler,
            'handle_note': self.handle_note,
            'handle_duration': self._handle_duration(),
            'evidence': self._evidence(),
            'ai_review': self.ai_review,
        }


class EdgeNode(Base):
    """边缘节点表 — 部署在校园各分区的边缘计算节点（Docker容器模拟）

    每个边缘节点下辖一个分区内的多台感知设备，在本地完成
    AI推理、多源融合与实时预警（本地毫秒级闭环），仅将
    结构化事件上报云端，是「端—边—云」协同架构的边侧载体。
    """
    __tablename__ = 'edge_nodes'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='节点ID')
    node_code = Column(String(50), unique=True, nullable=False, comment='节点编号（如EDGE-GATE）')
    name = Column(String(100), nullable=False, comment='节点名称')
    zone = Column(String(50), nullable=False, comment='负责的校园分区')
    description = Column(String(200), nullable=True, comment='节点说明')
    status = Column(String(20), default='offline', comment='在线状态（online/offline）')
    last_heartbeat_at = Column(DateTime, nullable=True, comment='最近心跳时间')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    # 关系
    devices = relationship('Device', back_populates='node')
    events = relationship('SecurityEvent', back_populates='node')

    def to_dict(self):
        return {
            'id': self.id,
            'node_code': self.node_code,
            'name': self.name,
            'zone': self.zone,
            'description': self.description,
            'status': self.status,
            'last_heartbeat_at': self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class SecurityEvent(Base):
    """安防事件表 — 边缘节点上报的结构化安防事件

    与 Alert（设备运行指标告警）互补：Alert 关心网络设备自身的
    CPU/内存/延迟异常；SecurityEvent 关心校园安防场景事件
    （徘徊/越线/烟火/人流/门禁），由边缘侧完成检测与本地联动后
    上报，云端负责去重合并、定级、推送与处置闭环。

    event_id 全局唯一，用于断网续传场景下的幂等去重。
    """
    __tablename__ = 'security_events'
    __table_args__ = (
        Index('idx_sec_event_zone_type', 'zone', 'event_type'),
        Index('idx_sec_event_occurred', 'occurred_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='事件ID')
    event_id = Column(String(64), unique=True, nullable=False, comment='边缘生成的全局事件ID（幂等去重）')
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=True, comment='触发设备ID')
    node_id = Column(Integer, ForeignKey('edge_nodes.id'), nullable=True, comment='上报的边缘节点ID')
    event_type = Column(String(50), nullable=False, comment='事件类型（loitering/line_crossing/fire_confirmed等）')
    level = Column(Integer, nullable=False, default=3, comment='告警级别（1紧急/2严重/3一般/4提示）')
    zone = Column(String(50), nullable=False, comment='发生分区')
    confidence = Column(Float, nullable=True, comment='边缘判定置信度(0~1)')
    sources = Column(Text, nullable=True, comment='证据源列表(JSON数组，如["video","vibration"])')
    local_actions = Column(Text, nullable=True, comment='边缘本地已执行的联动动作(JSON数组)')
    local_latency_ms = Column(Integer, nullable=True, comment='边缘本地判定耗时(毫秒)')
    message = Column(Text, nullable=True, comment='事件说明')
    status = Column(String(20), default='pending', comment='处置状态（pending/confirmed/processing/closed/false_alarm）')
    merge_count = Column(Integer, default=1, comment='合并次数（60s窗口内同分区同类型事件合并计数）')
    merged_event_ids = Column(Text, nullable=True, comment='已合并的边缘事件ID列表(JSON数组)')
    pushed_channels = Column(Text, nullable=True, comment='已推送通道列表(JSON数组)')
    occurred_at = Column(DateTime, default=datetime.now, comment='事件发生时间')
    created_at = Column(DateTime, default=datetime.now, comment='入库时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 关系
    device = relationship('Device')
    node = relationship('EdgeNode', back_populates='events')

    def to_dict(self):
        return {
            'id': self.id,
            'event_id': self.event_id,
            'device_id': self.device_id,
            'device_name': self.device.name if self.device else None,
            'device_code': self.device.device_code if self.device else None,
            'node_id': self.node_id,
            'node_name': self.node.name if self.node else None,
            'node_code': self.node.node_code if self.node else None,
            'event_type': self.event_type,
            'level': self.level,
            'zone': self.zone,
            'confidence': self.confidence,
            'sources': _json_list(self.sources),
            'local_actions': _json_list(self.local_actions),
            'local_latency_ms': self.local_latency_ms,
            'message': self.message,
            'status': self.status,
            'merge_count': self.merge_count,
            'merged_event_ids': _json_list(self.merged_event_ids),
            'pushed_channels': _json_list(self.pushed_channels),
            'occurred_at': self.occurred_at.isoformat() if self.occurred_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
