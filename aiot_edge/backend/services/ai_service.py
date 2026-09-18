"""
AIoT Edge — AI 助手服务
基于 DeepSeek 的智能运维助手：注入系统实时数据作为上下文，
以 SSE 流式方式调用 DeepSeek（OpenAI 兼容接口）并转发 token。
"""
import json
from typing import List

import httpx
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from core.config import settings
from models import Device, DeviceMetric, Alert

# ═══════════════════════════════════════════════════════════
# 系统提示词模板
# ═══════════════════════════════════════════════════════════
SYSTEM_PROMPT_TEMPLATE = """你是「AIoT Edge 智能网络设备感知与协同管理系统」的 AI 运维助手，\
帮助用户了解和分析系统内的设备运行状态、告警情况与异常事件。

下面是最新的系统实时数据（由边缘计算引擎采集汇总）：

{context}

回答要求：
1. 优先基于上面的实时数据作答；数据中没提到的内容，请如实说明「未获取到相关数据」。
2. 使用简体中文，语气简洁专业。
3. 涉及设备状态或告警时，请引用具体的设备编号与数值。
4. 若用户询问的是与本系统无关的通用问题，也可以正常回答。
"""


# ═══════════════════════════════════════════════════════════
# SSE 格式化
# ═══════════════════════════════════════════════════════════
def _sse(data) -> str:
    """把 dict 或字符串包装成 SSE 事件"""
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f'data: {payload}\n\n'


# ═══════════════════════════════════════════════════════════
# 系统上下文构建
# ═══════════════════════════════════════════════════════════
def build_system_context(db: Session) -> str:
    """汇总设备状态、最新指标与当前告警，生成给模型看的上下文文本"""
    devices = db.query(Device).order_by(Device.created_at.asc()).all()

    total = len(devices)
    online = sum(1 for d in devices if d.status == 'online')
    offline = total - online
    firing = (
        db.query(func.count(Alert.id))
        .filter(Alert.status == 'firing')
        .scalar()
    ) or 0

    lines = [
        f'- 设备总数 {total} 台，在线 {online} 台，离线 {offline} 台',
        f'- 当前未解决告警（firing）{firing} 条',
        '',
        '设备明细：',
    ]

    for d in devices:
        latest = (
            db.query(DeviceMetric)
            .filter(DeviceMetric.device_id == d.id)
            .order_by(desc(DeviceMetric.collected_at))
            .first()
        )
        if latest:
            cpu = latest.cpu_usage if latest.cpu_usage is not None else 0.0
            mem = latest.memory_usage if latest.memory_usage is not None else 0.0
            lat = latest.network_latency if latest.network_latency is not None else 0.0
            disk = latest.disk_usage if latest.disk_usage is not None else 0.0
            seen = latest.collected_at.strftime('%m-%d %H:%M:%S') if latest.collected_at else '无'
            lines.append(
                f'  · {d.device_code} {d.name}（{d.device_type}）[{d.status}] '
                f'CPU {cpu:.1f}% / 内存 {mem:.1f}% / 延迟 {lat:.1f}ms / 磁盘 {disk:.1f}%，'
                f'最近上报 {seen}'
            )
        else:
            lines.append(f'  · {d.device_code} {d.name}（{d.device_type}）[{d.status}] 暂无数据')

    recent = (
        db.query(Alert)
        .filter(Alert.status == 'firing')
        .order_by(desc(Alert.triggered_at))
        .limit(10)
        .all()
    )
    lines.append('')
    if recent:
        lines.append('当前告警（最近10条）：')
        for a in recent:
            device = db.query(Device).filter(Device.id == a.device_id).first()
            name = f'{device.device_code} {device.name}' if device else f'设备#{a.device_id}'
            t = a.triggered_at.strftime('%m-%d %H:%M') if a.triggered_at else ''
            lines.append(f'  · [{a.severity}] {name}：{a.message or a.alert_type}（{t}）')
    else:
        lines.append('当前告警：无')

    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════
# 流式对话
# ═══════════════════════════════════════════════════════════
def stream_chat(messages: List[dict], db: Session):
    """调用 DeepSeek 并逐 token 产出 SSE 事件

    产出格式：
      data: {"content": "..."}   — 一段回复文本
      data: {"error": "..."}     — 错误信息
      data: [DONE]               — 结束标记
    """
    if not settings.DEEPSEEK_API_KEY:
        yield _sse({'error': '未配置 DEEPSEEK_API_KEY，请在 backend/.env 中填入 API Key 后重启后端'})
        return

    context = build_system_context(db)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context)

    payload_messages = [{'role': 'system', 'content': system_prompt}, *messages]
    url = f"{settings.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        'Authorization': f'Bearer {settings.DEEPSEEK_API_KEY}',
        'Content-Type': 'application/json',
    }
    body = {
        'model': settings.DEEPSEEK_MODEL,
        'messages': payload_messages,
        'stream': True,
        'temperature': 0.7,
    }

    try:
        # read 不限时（流式），connect/其它 30s
        timeout = httpx.Timeout(30.0, read=None)
        with httpx.Client(timeout=timeout) as client:
            with client.stream('POST', url, headers=headers, json=body) as resp:
                if resp.status_code != 200:
                    detail = resp.text[:300]
                    yield _sse({'error': f'DeepSeek 接口返回 {resp.status_code}：{detail}'})
                    return

                for line in resp.iter_lines():
                    if not line or not line.startswith('data:'):
                        continue
                    data_str = line[len('data:'):].strip()
                    if data_str == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get('choices') or []
                    if not choices:
                        continue
                    delta = choices[0].get('delta') or {}
                    content = delta.get('content')
                    if content:
                        yield _sse({'content': content})

        yield _sse('[DONE]')
    except httpx.HTTPError as e:
        yield _sse({'error': f'请求 DeepSeek 失败：{e}'})
