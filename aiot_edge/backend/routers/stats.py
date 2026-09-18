"""
AIoT Edge — 可视化统计接口
仪表盘总览 + ECharts趋势数据 + 实时设备概览
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from core.database import get_db
from core.security import get_current_user
from models import Device, DeviceMetric, Alert

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get('/dashboard')
def get_dashboard(db: Session = Depends(get_db)):
    """仪表盘总览统计"""
    # 设备统计
    total_devices = db.query(func.count(Device.id)).scalar() or 0
    online_devices = (
        db.query(func.count(Device.id))
        .filter(Device.status == 'online')
        .scalar()
    ) or 0
    offline_devices = total_devices - online_devices

    # 当前未闭环告警数（待处理 + 已确认 + 处理中）
    firing_alerts = (
        db.query(func.count(Alert.id))
        .filter(Alert.status.in_(['firing', 'confirmed', 'processing']))
        .scalar()
    ) or 0

    # 所有设备最新一次 metric 的平均CPU和平均延迟
    # 用子查询取每个设备的最新一条metric
    latest_subquery = (
        db.query(
            DeviceMetric.device_id,
            func.max(DeviceMetric.collected_at).label('max_time'),
        )
        .group_by(DeviceMetric.device_id)
        .subquery()
    )

    latest_metrics = (
        db.query(DeviceMetric)
        .join(
            latest_subquery,
            (DeviceMetric.device_id == latest_subquery.c.device_id)
            & (DeviceMetric.collected_at == latest_subquery.c.max_time),
        )
        .all()
    )

    if latest_metrics:
        n = len(latest_metrics)
        avg_cpu = round(sum(m.cpu_usage or 0 for m in latest_metrics) / n, 1)
        avg_memory = round(sum(m.memory_usage or 0 for m in latest_metrics) / n, 1)
        avg_disk = round(sum(m.disk_usage or 0 for m in latest_metrics) / n, 1)
        avg_latency = round(sum(m.network_latency or 0 for m in latest_metrics) / n, 1)
    else:
        avg_cpu = avg_memory = avg_disk = avg_latency = 0.0

    return {
        'total_devices': total_devices,
        'online_devices': online_devices,
        'offline_devices': offline_devices,
        'firing_alerts_count': firing_alerts,
        'avg_cpu': avg_cpu,
        'avg_memory': avg_memory,
        'avg_disk': avg_disk,
        'avg_latency': avg_latency,
    }


@router.get('/devices/overview')
def get_devices_overview(db: Session = Depends(get_db)):
    """设备状态总览（含最新指标，用于仪表盘表格）"""
    devices = db.query(Device).order_by(Device.created_at.desc()).all()

    items = []
    for dev in devices:
        latest = (
            db.query(DeviceMetric)
            .filter(DeviceMetric.device_id == dev.id)
            .order_by(desc(DeviceMetric.collected_at))
            .first()
        )

        items.append({
            'id': dev.id,
            'device_code': dev.device_code,
            'name': dev.name,
            'device_type': dev.device_type,
            'status': dev.status,
            'last_seen_at': dev.last_seen_at.isoformat() if dev.last_seen_at else None,
            'cpu_usage': latest.cpu_usage if latest else None,
            'memory_usage': latest.memory_usage if latest else None,
            'network_latency': latest.network_latency if latest else None,
        })

    return items


@router.get('/trend')
def get_trend(
    device_id: int = Query(..., description='设备ID'),
    hours: int = Query(6, ge=1, le=168, description='查询最近N小时'),
    metric: str = Query('cpu', description='指标类型: cpu/memory/disk/latency/all'),
    db: Session = Depends(get_db),
):
    """获取设备历史趋势数据（ECharts格式）

    返回格式：
      {
        "xAxis": ["2024-01-01 10:00:00", ...],
        "series": [{"name": "CPU使用率", "data": [45.2, ...]}, ...]
      }
    """
    # 验证设备存在
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None:
        return {'xAxis': [], 'series': []}

    since = datetime.now() - timedelta(hours=hours)

    rows = (
        db.query(DeviceMetric)
        .filter(
            DeviceMetric.device_id == device_id,
            DeviceMetric.collected_at >= since,
        )
        .order_by(DeviceMetric.collected_at.asc())
        .all()
    )

    x_axis = []
    series = []

    if metric == 'cpu':
        series = [{'name': 'CPU使用率(%)', 'data': []}]
        for r in rows:
            x_axis.append(r.collected_at.strftime('%H:%M:%S') if r.collected_at else '')
            series[0]['data'].append(round(r.cpu_usage, 1) if r.cpu_usage is not None else None)
    elif metric == 'memory':
        series = [{'name': '内存使用率(%)', 'data': []}]
        for r in rows:
            x_axis.append(r.collected_at.strftime('%H:%M:%S') if r.collected_at else '')
            series[0]['data'].append(round(r.memory_usage, 1) if r.memory_usage is not None else None)
    elif metric == 'disk':
        series = [{'name': '磁盘使用率(%)', 'data': []}]
        for r in rows:
            x_axis.append(r.collected_at.strftime('%H:%M:%S') if r.collected_at else '')
            series[0]['data'].append(round(r.disk_usage, 1) if r.disk_usage is not None else None)
    elif metric == 'latency':
        series = [{'name': '网络延迟(ms)', 'data': []}]
        for r in rows:
            x_axis.append(r.collected_at.strftime('%H:%M:%S') if r.collected_at else '')
            series[0]['data'].append(round(r.network_latency, 1) if r.network_latency is not None else None)
    elif metric == 'all':
        # 三指标：CPU + 内存 + 磁盘（均为百分比，单Y轴）
        series = [
            {'name': 'CPU使用率(%)', 'data': []},
            {'name': '内存使用率(%)', 'data': []},
            {'name': '磁盘使用率(%)', 'data': []},
        ]
        for r in rows:
            x_axis.append(r.collected_at.strftime('%H:%M:%S') if r.collected_at else '')
            series[0]['data'].append(round(r.cpu_usage, 1) if r.cpu_usage is not None else None)
            series[1]['data'].append(round(r.memory_usage, 1) if r.memory_usage is not None else None)
            series[2]['data'].append(round(r.disk_usage, 1) if r.disk_usage is not None else None)
    else:
        series = [{'name': '数据', 'data': []}]
        for r in rows:
            x_axis.append(r.collected_at.strftime('%H:%M:%S') if r.collected_at else '')
            series[0]['data'].append(0)

    return {'xAxis': x_axis, 'series': series}
