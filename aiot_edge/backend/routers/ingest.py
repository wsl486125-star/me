"""
AIoT Edge — 数据采集接口
接收采集器转发的Docker容器真实运行数据
"""
from typing import List
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.database import get_db
from schemas import DeviceMetricIngest, DeviceMetricOut
from models import Device, DeviceMetric
from services.edge_engine import clean_data, detect_anomaly, ml_detect_anomaly
from services.alert_service import create_alert, auto_resolve_stale_alerts, schedule_ai_review

router = APIRouter()


@router.post('/metric')
def receive_metric(payload: DeviceMetricIngest, db: Session = Depends(get_db)):
    """接收设备上报的实时运行数据

    数据来源：Docker容器内 agent.py 通过 psutil 采集，
    经 collector/device_collector.py 转发至此接口。

    处理流程：
      1. 根据 device_code 查找/自动创建设备
      2. 更新设备在线状态
      3. 数据清洗 → 写入 DeviceMetric 记录
      4. 依次调用三层检测体系（阈值→滑动窗口统计→孤立森林）
      5. 若检测到异常则创建告警，否则自动解决该设备的过期告警
    """
    # 1. 查找设备，不存在则自动创建
    device = db.query(Device).filter(
        Device.device_code == payload.device_code
    ).first()

    if device is None:
        device = Device(
            device_code=payload.device_code,
            name=payload.device_code,         # 默认名称=编号
            device_type='未知',                # 后续可手动修改
            status='online',
            last_seen_at=datetime.now(),
        )
        db.add(device)
        db.flush()   # 获取 device.id

    # 2. 更新设备在线状态
    device.status = 'online'
    device.last_seen_at = datetime.now()

    # 3. 数据清洗
    metric_raw = {
        'cpu_usage': payload.cpu_usage,
        'memory_usage': payload.memory_usage,
        'network_latency': payload.network_latency,
    }
    cleaned = clean_data(metric_raw)

    # 4. 写入 DeviceMetric 记录
    metric = DeviceMetric(
        device_id=device.id,
        cpu_usage=cleaned['cpu_usage'],
        memory_usage=cleaned['memory_usage'],
        network_latency=cleaned['network_latency'],
        bandwidth_usage=payload.bandwidth_usage,
        disk_usage=payload.disk_usage,
    )
    db.add(metric)
    db.commit()
    db.refresh(metric)

    # 5. 边缘计算三层检测体系
    #   第一层（阈值规则）+ 第二层（滑动窗口统计）
    result = detect_anomaly(device.id, cleaned, db)

    #   若前两层未检出异常，尝试第三层（孤立森林模型）
    if not result['is_anomaly']:
        result = ml_detect_anomaly(device.id, cleaned, db)

    # 6. 告警处理
    anomaly_detected = result['is_anomaly']
    if anomaly_detected:
        # 构建"证据快照"：结构化记录触发瞬间的设备指标 + 检测依据 + 阈值
        evidence_snapshot = {
            'device_code': device.device_code,
            'cpu_usage': cleaned['cpu_usage'],
            'memory_usage': cleaned['memory_usage'],
            'network_latency': cleaned['network_latency'],
            'bandwidth_usage': payload.bandwidth_usage,
            'disk_usage': payload.disk_usage,
            'alert_type': result.get('alert_type'),
            'severity': result.get('severity'),
            'metric_value': result.get('metric_value'),
            'threshold': result.get('threshold'),
            'detected_by': '边缘计算三层检测（阈值/滑动窗口/孤立森林）',
        }
        alert = create_alert(db, device.id, result, metric_snapshot=evidence_snapshot)
        # 异步触发 DeepSeek 语义复核（后台线程，不阻塞采集）
        # 注意：必须在 commit 前调用，此时 alert 对象尚未 expire
        if alert is not None:
            from core.database import SessionLocal
            schedule_ai_review(alert, SessionLocal)
        db.commit()
    else:
        auto_resolve_stale_alerts(db, device.id, cleaned)

    db.commit()

    return {
        'success': True,
        'message': '数据已接收',
        'anomaly_detected': anomaly_detected,
        'device_id': device.id,
    }


@router.get('/recent', response_model=List[DeviceMetricOut])
def get_recent_metrics(
    device_code: str = Query(None, description='设备编号（可选筛选）'),
    limit: int = Query(20, ge=1, le=200, description='返回条数'),
    db: Session = Depends(get_db),
):
    """查看最近上报的运行数据（调试用）

    用于确认 Docker 容器采集的真实数据是否已正确写入数据库。
    """
    query = db.query(DeviceMetric)

    if device_code:
        device = db.query(Device).filter(
            Device.device_code == device_code
        ).first()
        if device:
            query = query.filter(DeviceMetric.device_id == device.id)
        else:
            return []

    return (
        query.order_by(DeviceMetric.collected_at.desc())
        .limit(limit)
        .all()
    )
