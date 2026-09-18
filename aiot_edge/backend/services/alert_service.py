"""
AIoT Edge — 告警判定与记录服务
"""
from __future__ import annotations
import json
import threading
from datetime import datetime

from sqlalchemy.orm import Session

from models import Alert
from services.edge_engine import detect_anomaly


def create_alert(db: Session, device_id: int, anomaly_result: dict, metric_snapshot: dict = None) -> Alert | None:
    """根据异常检测结果创建告警记录

    去重逻辑：
      检查该设备同类型(alert_type)是否已有未闭环的告警，
      若有则跳过创建，避免重复刷屏。

    metric_snapshot：触发时的设备指标快照（CPU/内存/延迟等），
      结构化存为 evidence_snapshot，作为"现场证据"展示
      （用真实数据替代伪造的抓拍图片，体现"真实数据支撑"）。

    返回：
      新创建的 Alert 对象，或 None（被去重跳过）
    """
    alert_type = anomaly_result.get('alert_type', 'unknown')

    # 去重：同一设备同类型告警且仍为 firing 状态 → 跳过
    existing = (
        db.query(Alert)
        .filter(
            Alert.device_id == device_id,
            Alert.alert_type == alert_type,
            Alert.status == 'firing',
        )
        .first()
    )
    if existing:
        return None

    alert = Alert(
        device_id=device_id,
        alert_type=alert_type,
        severity=anomaly_result.get('severity', 'medium'),
        metric_value=anomaly_result.get('metric_value'),
        threshold=anomaly_result.get('threshold'),
        message=anomaly_result.get('message', ''),
        status='firing',
        triggered_at=datetime.now(),
        # 证据快照：结构化记录触发瞬间的设备指标 + 检测依据 + 阈值
        evidence_snapshot=json.dumps(metric_snapshot, ensure_ascii=False) if metric_snapshot else None,
    )
    db.add(alert)
    db.flush()  # 获取 alert.id，供异步 AI 复核回填使用
    return alert


def resolve_alert(db: Session, alert_id: int) -> bool:
    """手动解决指定告警

    将告警状态设为 resolved，记录解决时间。
    返回 True 表示成功，False 表示未找到告警。
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert is None:
        return False

    alert.status = 'resolved'
    alert.resolved_at = datetime.now()
    return True


def transition_alert(
    db: Session,
    alert_id: int,
    target_status: str,
    handler: str = '',
    note: str = '',
) -> tuple[bool, str]:
    """告警处置闭环状态流转

    状态机：firing → confirmed → processing → resolved / false_alarm
           （resolved 语义等价 closed；false_alarm 为误报闭环）

    返回 (是否成功, 提示信息)。
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert is None:
        return False, '告警不存在'

    now = datetime.now()
    old = alert.status

    # 合法流转规则（resolved/closed 语义等价，false_alarm 任意未闭环可直达）
    allowed = {
        'firing': ['confirmed', 'false_alarm'],
        'confirmed': ['processing', 'false_alarm'],
        'processing': ['resolved', 'closed', 'false_alarm'],
    }
    if target_status not in allowed.get(old, []):
        return False, f'当前状态「{old}」不能流转到「{target_status}」'

    # 统一 closed → resolved（对外语义一致，存储用 resolved）
    store_status = 'resolved' if target_status == 'closed' else target_status

    alert.status = store_status
    if handler:
        alert.handler = handler
    if note:
        alert.handle_note = note

    if target_status == 'confirmed':
        alert.confirmed_at = now
    elif target_status == 'processing':
        alert.processing_at = now
    elif target_status in ('resolved', 'closed'):
        alert.resolved_at = now
    elif target_status == 'false_alarm':
        alert.resolved_at = now

    return True, '操作成功'


def auto_resolve_stale_alerts(db: Session, device_id: int, current_metric: dict):
    """自动解决过期告警

    当设备本次上报的数据不再异常时（即 detect_anomaly 判定无异常），
    自动将该设备所有未闭环（firing/confirmed/processing）的告警标记为 resolved。

    这样告警面板能实时反映"问题是否已恢复"，不需要人工逐一关闭。
    """
    # 确认当前数据确实无异常
    result = detect_anomaly(device_id, current_metric, db)
    if result['is_anomaly']:
        return  # 仍有异常，不自动解决

    firing_alerts = (
        db.query(Alert)
        .filter(
            Alert.device_id == device_id,
            Alert.status.in_(['firing', 'confirmed', 'processing']),
        )
        .all()
    )

    now = datetime.now()
    for alert in firing_alerts:
        alert.status = 'resolved'
        alert.resolved_at = now


# ═══════════════════════════════════════════════════════════
# AI 语义复核（DeepSeek 异常原因解读）
# ═══════════════════════════════════════════════════════════

def generate_ai_review(alert: dict) -> str:
    """调用 DeepSeek 生成告警的「异常原因解读」（语义复核/后处理）

    用一次非流式短请求，让模型基于告警的指标快照与检测依据，
    输出一句专业、简洁的异常原因分析，模拟视觉方案里的"AI 理解"环节。

    失败时静默返回空串（不阻塞告警主链路）。
    """
    try:
        from core.config import settings
        import httpx

        if not settings.DEEPSEEK_API_KEY:
            return ''

        prompt = (
            '你是边缘计算告警系统的运维专家。下面是一条异常告警，请用一两句话'
            '简明分析可能的原因，并给出处置建议。直接输出结论，不要客套。\n\n'
            f"告警类型：{alert.get('alert_type')}\n"
            f"严重程度：{alert.get('severity')}\n"
            f"指标值：{alert.get('metric_value')}\n"
            f"阈值：{alert.get('threshold')}\n"
            f"说明：{alert.get('message')}\n"
        )
        if alert.get('evidence'):
            prompt += f"现场指标快照：{json.dumps(alert['evidence'], ensure_ascii=False)}\n"

        url = f"{settings.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            'Authorization': f'Bearer {settings.DEEPSEEK_API_KEY}',
            'Content-Type': 'application/json',
        }
        body = {
            'model': settings.DEEPSEEK_MODEL,
            'messages': [
                {'role': 'system', 'content': '你是专业的边缘计算与网络运维专家，回答简洁专业。'},
                {'role': 'user', 'content': prompt},
            ],
            'stream': False,
            'temperature': 0.3,
            'max_tokens': 200,
        }
        timeout = httpx.Timeout(15.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=body)
            if resp.status_code != 200:
                return ''
            data = resp.json()
            return data['choices'][0]['message']['content'].strip()
    except Exception:
        return ''


def ai_review_worker(session_factory, alert_id: int, alert_payload: dict):
    """后台线程：生成 AI 语义复核并回填数据库

    独立线程 + 独立会话，避免阻塞采集接口，也避免与主链路争用连接。
    """
    try:
        review = generate_ai_review(alert_payload)
        if not review:
            return
        db = session_factory()
        try:
            alert = db.query(Alert).filter(Alert.id == alert_id).first()
            if alert:
                alert.ai_review = review
                db.commit()
        finally:
            db.close()
    except Exception:
        pass


def schedule_ai_review(alert: Alert, session_factory):
    """告警创建后，异步触发一次 AI 语义复核（后台线程，不阻塞主链路）

    在调用方 db.commit() 之前调用本函数（此时 alert.id 已由 flush 生成，
    且 to_dict() 读取的是内存中的字段，不触发额外查询）。
    """
    if not alert or not alert.id:
        return
    payload = alert.to_dict()
    alert_id = alert.id
    t = threading.Thread(
        target=ai_review_worker,
        args=(session_factory, alert_id, payload),
        daemon=True,
    )
    t.start()
