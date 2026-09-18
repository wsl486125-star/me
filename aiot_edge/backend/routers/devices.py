"""
AIoT Edge — 设备管理路由
设备的增删改查 + 历史数据查询（均需JWT认证）
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func

from core.database import get_db
from core.security import get_current_user
from schemas import DeviceCreate, DeviceUpdate, DeviceOut, DeviceMetricOut
from models import User, Device, DeviceMetric, Alert, SecurityEvent

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get('', response_model=List[dict])
def list_devices(db: Session = Depends(get_db)):
    """获取设备列表（含最新一条metric摘要数据）"""
    devices = db.query(Device).order_by(Device.created_at.desc()).all()

    result = []
    for dev in devices:
        # 获取该设备最新一条 metric
        latest_metric = (
            db.query(DeviceMetric)
            .filter(DeviceMetric.device_id == dev.id)
            .order_by(desc(DeviceMetric.collected_at))
            .first()
        )

        item = dev.to_dict()
        if latest_metric:
            item['latest_cpu'] = latest_metric.cpu_usage
            item['latest_memory'] = latest_metric.memory_usage
            item['latest_latency'] = latest_metric.network_latency
        else:
            item['latest_cpu'] = None
            item['latest_memory'] = None
            item['latest_latency'] = None
        result.append(item)

    return result


@router.get('/{device_id}')
def get_device(device_id: int, db: Session = Depends(get_db)):
    """获取单个设备详情 + 最近24小时数据统计"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail='设备不存在')

    # 24小时统计
    since = datetime.now() - timedelta(hours=24)
    stats = (
        db.query(
            func.count(DeviceMetric.id).label('count'),
            func.avg(DeviceMetric.cpu_usage).label('avg_cpu'),
            func.max(DeviceMetric.cpu_usage).label('max_cpu'),
            func.avg(DeviceMetric.memory_usage).label('avg_memory'),
            func.avg(DeviceMetric.network_latency).label('avg_latency'),
        )
        .filter(
            DeviceMetric.device_id == device_id,
            DeviceMetric.collected_at >= since,
        )
        .first()
    )

    return {
        **device.to_dict(),
        'stats_24h': {
            'data_count': stats.count or 0,
            'avg_cpu': round(stats.avg_cpu, 2) if stats.avg_cpu else None,
            'max_cpu': round(stats.max_cpu, 2) if stats.max_cpu else None,
            'avg_memory': round(stats.avg_memory, 2) if stats.avg_memory else None,
            'avg_latency': round(stats.avg_latency, 2) if stats.avg_latency else None,
        },
    }


@router.post('', status_code=status.HTTP_201_CREATED)
def create_device(
    payload: DeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动添加设备"""
    # 检查 device_code 唯一性
    existing = db.query(Device).filter(Device.device_code == payload.device_code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'设备编号 {payload.device_code} 已存在',
        )

    device = Device(
        device_code=payload.device_code,
        name=payload.name,
        device_type=payload.device_type,
        location=payload.location,
        zone=payload.zone,
        owner_id=current_user.id,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device.to_dict()


@router.put('/{device_id}')
def update_device(
    device_id: int,
    payload: DeviceUpdate,
    db: Session = Depends(get_db),
):
    """编辑设备信息"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail='设备不存在')

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(device, key, value)

    db.commit()
    db.refresh(device)
    return device.to_dict()


@router.delete('/{device_id}')
def delete_device(device_id: int, db: Session = Depends(get_db)):
    """删除设备（级联删除其 metric 和告警记录）"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail='设备不存在')

    # 级联删除关联数据；安防事件作为审计记录保留，解除设备外键。
    db.query(SecurityEvent).filter(SecurityEvent.device_id == device_id).update(
        {SecurityEvent.device_id: None},
        synchronize_session=False,
    )
    db.query(DeviceMetric).filter(DeviceMetric.device_id == device_id).delete()
    db.query(Alert).filter(Alert.device_id == device_id).delete()
    db.delete(device)
    db.commit()

    return {'message': f'设备 {device.name} 已删除', 'success': True}


@router.get('/{device_id}/history', response_model=List[DeviceMetricOut])
def get_device_history(
    device_id: int,
    hours: int = Query(24, ge=1, le=168, description='查询最近N小时'),
    db: Session = Depends(get_db),
):
    """获取设备历史运行数据（用于ECharts折线图）

    返回指定小时数内的所有 metric 记录，按采集时间升序排列。
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail='设备不存在')

    since = datetime.now() - timedelta(hours=hours)

    metrics = (
        db.query(DeviceMetric)
        .filter(
            DeviceMetric.device_id == device_id,
            DeviceMetric.collected_at >= since,
        )
        .order_by(DeviceMetric.collected_at.asc())
        .all()
    )

    return metrics
