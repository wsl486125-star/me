"""
AIoT Edge — 设备分组路由（协同管理）

将多个网络设备划入同一分组，实现分组级的运行状态总览与协同处置，
是「感知与协同管理」中协同能力的载体。
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from core.database import get_db
from core.security import get_current_user
from models import User, Device, DeviceGroup, DeviceMetric
from schemas import GroupCreate, GroupUpdate, GroupDeviceAssign

router = APIRouter(dependencies=[Depends(get_current_user)])


def _device_summary(db: Session, device: Device) -> dict:
    """附加设备最新运行指标到设备字典"""
    latest = (
        db.query(DeviceMetric)
        .filter(DeviceMetric.device_id == device.id)
        .order_by(desc(DeviceMetric.collected_at))
        .first()
    )
    item = device.to_dict()
    item['latest_cpu'] = latest.cpu_usage if latest else None
    item['latest_memory'] = latest.memory_usage if latest else None
    item['latest_latency'] = latest.network_latency if latest else None
    return item


@router.get('')
def list_groups(db: Session = Depends(get_db)):
    """分组列表（含每组设备数与在线设备数）"""
    groups = db.query(DeviceGroup).order_by(desc(DeviceGroup.created_at)).all()

    items = []
    for g in groups:
        devices = db.query(Device).filter(Device.group_id == g.id).all()
        online = sum(1 for d in devices if d.status == 'online')
        item = g.to_dict()
        item['device_count'] = len(devices)
        item['online_count'] = online
        items.append(item)

    ungrouped_count = (
        db.query(func.count(Device.id)).filter(Device.group_id.is_(None)).scalar()
    ) or 0

    return {'items': items, 'ungrouped_count': ungrouped_count}


@router.get('/{group_id}')
def get_group(group_id: int, db: Session = Depends(get_db)):
    """获取单个分组详情（含组内设备与最新指标）"""
    group = db.query(DeviceGroup).filter(DeviceGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail='分组不存在')

    devices = (
        db.query(Device)
        .filter(Device.group_id == group_id)
        .order_by(desc(Device.created_at))
        .all()
    )

    return {
        **group.to_dict(),
        'devices': [_device_summary(db, d) for d in devices],
    }


@router.post('', status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建分组"""
    existing = db.query(DeviceGroup).filter(DeviceGroup.name == payload.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'分组 {payload.name} 已存在',
        )

    group = DeviceGroup(
        name=payload.name,
        description=payload.description,
        owner_id=current_user.id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group.to_dict()


@router.put('/{group_id}')
def update_group(group_id: int, payload: GroupUpdate, db: Session = Depends(get_db)):
    """编辑分组信息"""
    group = db.query(DeviceGroup).filter(DeviceGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail='分组不存在')

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(group, key, value)

    db.commit()
    db.refresh(group)
    return group.to_dict()


@router.delete('/{group_id}')
def delete_group(group_id: int, db: Session = Depends(get_db)):
    """删除分组（解除组内设备的关联，不删除设备本身）"""
    group = db.query(DeviceGroup).filter(DeviceGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail='分组不存在')

    db.query(Device).filter(Device.group_id == group_id).update({'group_id': None})
    db.delete(group)
    db.commit()

    return {'message': f'分组 {group.name} 已删除', 'success': True}


@router.post('/{group_id}/devices')
def assign_devices(
    group_id: int,
    payload: GroupDeviceAssign,
    db: Session = Depends(get_db),
):
    """将多个设备划入指定分组"""
    group = db.query(DeviceGroup).filter(DeviceGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail='分组不存在')

    assigned = 0
    for device_id in payload.device_ids:
        device = db.query(Device).filter(Device.id == device_id).first()
        if device:
            device.group_id = group_id
            assigned += 1

    db.commit()
    return {'message': f'已将 {assigned} 台设备划入分组', 'success': True, 'count': assigned}


@router.delete('/{group_id}/devices/{device_id}')
def remove_device(group_id: int, device_id: int, db: Session = Depends(get_db)):
    """将设备移出分组（设备本身保留，仅解除关联）"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device or device.group_id != group_id:
        raise HTTPException(status_code=404, detail='设备不在该分组中')

    device.group_id = None
    db.commit()
    return {'message': f'设备 {device.name} 已移出分组', 'success': True}
