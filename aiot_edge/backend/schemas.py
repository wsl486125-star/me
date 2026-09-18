"""
AIoT Edge — Pydantic v2 数据校验模型
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# User 用户相关
# ═══════════════════════════════════════════════════════════
class UserCreate(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description='用户名')
    email: str = Field(..., max_length=100, description='邮箱地址')
    password: str = Field(..., min_length=6, max_length=128, description='密码')
    code: str = Field(..., description='邮箱验证码')


class UserLogin(BaseModel):
    """用户登录请求

    支持两种登录方式（二选一）：
      - password：用户名/邮箱 + 密码
      - code：邮箱 + 验证码
    """
    username: str = Field(..., description='用户名或邮箱')
    password: Optional[str] = Field(None, description='密码（密码登录时必填）')
    code: Optional[str] = Field(None, description='邮箱验证码（验证码登录时必填）')
    login_type: str = Field('password', description='登录方式：password / code')


class SendCodeRequest(BaseModel):
    """发送邮箱验证码请求"""
    email: str = Field(..., max_length=100, description='接收验证码的邮箱地址')


class UserOut(BaseModel):
    """用户信息响应"""
    id: int
    username: str
    email: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    """JWT 令牌响应"""
    access_token: str
    token_type: str = 'bearer'


# ═══════════════════════════════════════════════════════════
# Device 设备相关
# ═══════════════════════════════════════════════════════════
class DeviceCreate(BaseModel):
    """创建设备请求"""
    device_code: str = Field(..., max_length=50, description='设备编号（如DEV-001）')
    name: str = Field(..., max_length=100, description='设备名称')
    device_type: str = Field(..., max_length=50, description='设备类型（路由器/交换机/传感器/虚拟摄像头等）')
    location: Optional[str] = Field(None, max_length=200, description='部署位置')
    zone: Optional[str] = Field(None, max_length=50, description='所属校园分区')


class DeviceUpdate(BaseModel):
    """更新设备请求"""
    name: Optional[str] = Field(None, max_length=100)
    device_type: Optional[str] = Field(None, max_length=50)
    location: Optional[str] = Field(None, max_length=200)
    status: Optional[str] = Field(None, max_length=20)
    group_id: Optional[int] = Field(None, description='所属分组ID')
    zone: Optional[str] = Field(None, max_length=50, description='所属校园分区')


class DeviceOut(BaseModel):
    """设备信息响应"""
    id: int
    device_code: str
    name: str
    device_type: str
    location: Optional[str]
    status: str
    zone: Optional[str]
    node_id: Optional[int]
    last_seen_at: Optional[datetime]
    created_at: datetime
    owner_id: Optional[int]
    group_id: Optional[int]

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════
# DeviceMetric 设备运行数据相关
# ═══════════════════════════════════════════════════════════
class DeviceMetricIngest(BaseModel):
    """接收采集器转发的容器真实运行数据

    数据来源：Docker容器内 agent.py 通过 psutil 采集，
    经 collector/device_collector.py 转发至此后端接口。
    """
    device_code: str = Field(..., description='设备编号')
    cpu_usage: float = Field(..., ge=0, le=100, description='CPU使用率(%)')
    memory_usage: float = Field(..., ge=0, le=100, description='内存使用率(%)')
    network_latency: float = Field(..., ge=0, description='网络延迟(ms)')
    bandwidth_usage: float = Field(..., ge=0, description='带宽使用(Mbps)')
    disk_usage: Optional[float] = Field(None, ge=0, le=100, description='磁盘使用率(%)')


class DeviceMetricOut(BaseModel):
    """设备运行数据响应"""
    id: int
    device_id: int
    cpu_usage: Optional[float]
    memory_usage: Optional[float]
    network_latency: Optional[float]
    bandwidth_usage: Optional[float]
    disk_usage: Optional[float]
    collected_at: datetime

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════
# Alert 告警相关
# ═══════════════════════════════════════════════════════════
class AlertOut(BaseModel):
    """告警记录响应"""
    id: int
    device_id: int
    alert_type: str
    severity: str
    metric_value: Optional[float]
    threshold: Optional[float]
    message: Optional[str]
    status: str
    triggered_at: datetime
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True


class AlertUpdate(BaseModel):
    """更新告警状态请求"""
    status: str = Field(..., description='告警状态（firing/resolved）')


# ═══════════════════════════════════════════════════════════
# DeviceGroup 设备分组相关
# ═══════════════════════════════════════════════════════════
class GroupCreate(BaseModel):
    """创建分组请求"""
    name: str = Field(..., max_length=100, description='分组名称')
    description: Optional[str] = Field(None, max_length=200, description='分组描述')


class GroupUpdate(BaseModel):
    """更新分组请求"""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=200)


class GroupDeviceAssign(BaseModel):
    """分组设备分配请求"""
    device_ids: List[int] = Field(..., description='要加入分组的设备ID列表')


# ═══════════════════════════════════════════════════════════
# 统计查询相关
# ═══════════════════════════════════════════════════════════
class StatsQuery(BaseModel):
    """历史数据查询参数"""
    device_id: Optional[int] = Field(None, description='设备ID')
    hours: int = Field(1, ge=1, le=168, description='查询最近N小时的数据')


# ═══════════════════════════════════════════════════════════
# AI 助手相关
# ═══════════════════════════════════════════════════════════
class AiChatMessage(BaseModel):
    """单条对话消息"""
    role: str = Field(..., description='消息角色：user / assistant')
    content: str = Field(..., description='消息内容')


class AiChatRequest(BaseModel):
    """AI 助手对话请求（携带完整对话历史）"""
    messages: List[AiChatMessage] = Field(..., description='对话历史，最后一条为最新用户提问')


# ═══════════════════════════════════════════════════════════
# 校园安防 · 边缘节点 / 安防事件相关
# ═══════════════════════════════════════════════════════════
class NodeCreate(BaseModel):
    """注册边缘节点请求"""
    node_code: str = Field(..., max_length=50, description='节点编号（如EDGE-GATE）')
    name: str = Field(..., max_length=100, description='节点名称')
    zone: str = Field(..., max_length=50, description='负责的校园分区')
    description: Optional[str] = Field(None, max_length=200, description='节点说明')


class NodeHeartbeat(BaseModel):
    """边缘节点心跳上报

    心跳同时携带该节点下属的在线设备编号列表，
    云端据此统一刷新设备在线状态（边缘节点代理上报）。
    """
    node_code: str = Field(..., max_length=50, description='节点编号')
    devices: List[str] = Field(default_factory=list, description='下属在线设备编号列表')


class SecurityEventIngest(BaseModel):
    """接收边缘节点上报的结构化安防事件

    数据来源：边缘节点在本地完成 AI 推理、多源融合与规则判定后，
    仅将结构化事件（不含原始视频流）经 HTTP 上报至云端。
    event_id 由边缘侧生成并全局唯一，用于断网续传的幂等去重。
    """
    event_id: str = Field(..., max_length=64, description='边缘生成的全局事件ID')
    device_code: str = Field(..., max_length=50, description='触发设备编号')
    node_code: str = Field(..., max_length=50, description='上报的边缘节点编号')
    event_type: str = Field(..., max_length=50, description='事件类型（loitering/line_crossing/fire_confirmed等）')
    zone: str = Field(..., max_length=50, description='发生分区')
    confidence: Optional[float] = Field(None, ge=0, le=1, description='边缘判定置信度(0~1)')
    sources: List[str] = Field(default_factory=list, description='证据源列表（如["video","vibration"]）')
    local_actions: List[str] = Field(default_factory=list, description='边缘本地已执行的联动动作')
    local_latency_ms: Optional[int] = Field(None, ge=0, description='边缘本地判定耗时(毫秒)')
    message: Optional[str] = Field(None, max_length=500, description='事件说明')
    occurred_at: Optional[datetime] = Field(None, description='事件发生时间（缺省为云端入库时间）')


class EventStatusUpdate(BaseModel):
    """安防事件处置状态流转请求

    状态机：pending → confirmed → processing → closed，
    任意未闭环状态可流转为 false_alarm（误报）。
    """
    status: str = Field(..., description='目标状态（pending/confirmed/processing/closed/false_alarm）')
    note: Optional[str] = Field(None, max_length=200, description='处置备注')
