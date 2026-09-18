"""
AIoT Edge — 告警管理路由
告警查询、处置流转、统计（均需JWT认证）
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from core.database import get_db
from core.security import get_current_user
from models import Device, Alert
from services.alert_service import resolve_alert, transition_alert

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get('')
def list_alerts(
    status_filter: str = Query('all', alias='status', description='告警状态: firing/confirmed/processing/resolved/false_alarm/all'),
    severity: str = Query(None, description='严重程度筛选: critical/high/medium/low'),
    device_id: int = Query(None, description='按设备ID筛选'),
    page: int = Query(1, ge=1, description='页码'),
    per_page: int = Query(20, ge=1, le=100, description='每页条数'),
    db: Session = Depends(get_db),
):
    """获取告警列表（分页，含设备名称）"""
    query = db.query(Alert)

    # 状态筛选
    if status_filter == 'firing':
        query = query.filter(Alert.status == 'firing')
    elif status_filter == 'resolved':
        query = query.filter(Alert.status == 'resolved')
    elif status_filter == 'confirmed':
        query = query.filter(Alert.status == 'confirmed')
    elif status_filter == 'processing':
        query = query.filter(Alert.status == 'processing')
    elif status_filter == 'false_alarm':
        query = query.filter(Alert.status == 'false_alarm')
    elif status_filter == 'open':
        # 未闭环：待处理 + 已确认 + 处理中
        query = query.filter(Alert.status.in_(['firing', 'confirmed', 'processing']))

    # 严重程度筛选
    if severity:
        query = query.filter(Alert.severity == severity)

    # 设备筛选（用于设备详情页的告警历史）
    if device_id is not None:
        query = query.filter(Alert.device_id == device_id)

    # 总数
    total = query.count()

    # 分页
    alerts = (
        query.order_by(desc(Alert.triggered_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # 附加设备名称
    items = []
    for alert in alerts:
        device = db.query(Device).filter(Device.id == alert.device_id).first()
        item = alert.to_dict()
        item['device_name'] = device.name if device else '未知设备'
        item['device_code'] = device.device_code if device else '未知'
        items.append(item)

    return {
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': max(1, (total + per_page - 1) // per_page),
    }


@router.put('/{alert_id}/transition')
def transition_alert_endpoint(
    alert_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    """告警处置流转（闭环状态机）

    请求体：{ "status": "confirmed|processing|resolved|false_alarm", "handler": "...", "note": "..." }
    """
    target = payload.get('status', '')
    handler = payload.get('handler', '')
    note = payload.get('note', '')

    ok, msg = transition_alert(db, alert_id, target, handler, note)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    db.commit()
    return {'message': msg, 'success': True}


@router.put('/{alert_id}/resolve')
def resolve_alert_endpoint(alert_id: int, db: Session = Depends(get_db)):
    """手动标记告警为已解决（兼容旧接口，直接闭环）"""
    success = resolve_alert(db, alert_id)
    if not success:
        raise HTTPException(status_code=404, detail='告警不存在')
    db.commit()
    return {'message': '告警已标记为已解决', 'success': True}


@router.get('/stats')
def alert_stats(db: Session = Depends(get_db)):
    """告警统计：闭环状态计数（用于统计卡片）"""
    def _count(cond):
        return db.query(func.count(Alert.id)).filter(cond).scalar() or 0

    stats = {
        # 闭环状态机各阶段数量
        'firing': _count(Alert.status == 'firing'),          # 待处理
        'confirmed': _count(Alert.status == 'confirmed'),    # 已确认
        'processing': _count(Alert.status == 'processing'),  # 处理中
        'resolved': _count(Alert.status == 'resolved'),      # 已解决
        'false_alarm': _count(Alert.status == 'false_alarm'),# 误报
        # 汇总
        'total_open': _count(Alert.status.in_(['firing', 'confirmed', 'processing'])),
        'total_resolved': _count(Alert.status == 'resolved'),
        'total_false_alarm': _count(Alert.status == 'false_alarm'),
    }

    return stats


@router.get('/efficiency')
def alert_efficiency(db: Session = Depends(get_db)):
    """系统效能指标（对应四类验收指标，纯软件统计）

    事件发现率 = 有效告警 / 总告警（有效 = resolved + false_alarm，排除仍在途的 firing/confirmed/processing）
    告警准确率 = 1 - 误报率 = resolved / (resolved + false_alarm)
    平均处置时长 = 已闭环告警的 (resolved_at - triggered_at) 平均值（秒）
    闭环率 = 已闭环 / 总告警
    """
    def _count(cond):
        return db.query(func.count(Alert.id)).filter(cond).scalar() or 0

    total = _count(True)  # 全部告警
    resolved = _count(Alert.status == 'resolved')
    false_alarm = _count(Alert.status == 'false_alarm')
    open_count = _count(Alert.status.in_(['firing', 'confirmed', 'processing']))

    closed_count = resolved + false_alarm  # 已闭环（解决 + 误报）
    valid_count = closed_count             # 有效告警（已确认的闭环）

    # 平均处置时长（秒）：仅统计有 resolved_at 且非误报的告警
    rows = (
        db.query(Alert.triggered_at, Alert.resolved_at)
        .filter(Alert.status == 'resolved')
        .filter(Alert.resolved_at.isnot(None))
        .filter(Alert.triggered_at.isnot(None))
        .all()
    )
    durations = []
    for trig, res in rows:
        if trig and res:
            secs = (res - trig).total_seconds()
            if secs >= 0:
                durations.append(secs)
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0.0

    return {
        'total': total,
        'open': open_count,
        'resolved': resolved,
        'false_alarm': false_alarm,
        'closed': closed_count,
        # 四类验收指标
        'discovery_rate': round(valid_count / total, 4) if total else 0.0,      # 事件发现率
        'accuracy_rate': round(resolved / closed_count, 4) if closed_count else 0.0,  # 告警准确率
        'avg_handle_duration': avg_duration,                                     # 平均处置时长(秒)
        'closure_rate': round(closed_count / total, 4) if total else 0.0,        # 闭环率
    }
