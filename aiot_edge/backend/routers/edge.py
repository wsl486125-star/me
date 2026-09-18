"""
AIoT Edge — 边缘计算中心路由

将边缘引擎的三层检测体系与孤立森林模型状态暴露给前端，
使「边缘计算」这一核心能力在界面上可观测、可解释。
"""
import time
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from core.database import get_db
from core.security import get_current_user
from models import Device, Alert
from services.edge_engine import MODELS_CACHE_DIR, MODEL_TTL_SECONDS

router = APIRouter(dependencies=[Depends(get_current_user)])

# 告警类型 → 检测层映射
ALERT_TYPE_LAYER = {
    'cpu_high': 'threshold',
    'latency_high': 'threshold',
    'memory_high': 'threshold',
    'cpu_spike': 'sliding_window',
    'ml_anomaly': 'isolation_forest',
    'offline': 'offline',
}

# 检测层展示信息（顺序即前端展示顺序）
LAYERS = [
    {'key': 'threshold', 'label': '第一层 · 阈值规则',
     'desc': '即时判断单项指标是否超过硬性上限（CPU>85% / 延迟>200ms / 内存>90%），响应最快'},
    {'key': 'sliding_window', 'label': '第二层 · 滑动窗口统计',
     'desc': '对比近期均值（mean+2σ）识别指标相对自身历史的突增，比静态阈值更灵活'},
    {'key': 'isolation_forest', 'label': '第三层 · 孤立森林',
     'desc': '联合CPU/内存/延迟三维度，发现前两层漏判的组合异常'},
    {'key': 'offline', 'label': '离线检测',
     'desc': '超过30秒无上报即判定设备离线，触发 critical 级告警'},
]


@router.get('/status')
def edge_status(db: Session = Depends(get_db)):
    """边缘计算中心总览状态

    返回：
      1. layers — 各检测层触发的告警数（含各告警类型细分）
      2. models — 每台设备的孤立森林模型状态（是否已训练/样本数/训练时间/缓存年龄）
      3. 汇总统计（累计告警、当前激活告警、已训练模型数）
    """
    # ━━ 1. 各检测层告警统计 ━━
    type_counts = (
        db.query(Alert.alert_type, func.count(Alert.id))
        .group_by(Alert.alert_type)
        .all()
    )

    layer_agg = {l['key']: {'count': 0, 'types': {}} for l in LAYERS}
    total_alerts = 0
    for alert_type, cnt in type_counts:
        layer = ALERT_TYPE_LAYER.get(alert_type, 'threshold')
        layer_agg[layer]['count'] += cnt
        layer_agg[layer]['types'][alert_type] = cnt
        total_alerts += cnt

    firing_alerts = (
        db.query(func.count(Alert.id)).filter(Alert.status == 'firing').scalar()
    ) or 0

    layers = [
        {
            'key': l['key'],
            'label': l['label'],
            'desc': l['desc'],
            'count': layer_agg[l['key']]['count'],
            'types': layer_agg[l['key']]['types'],
        }
        for l in LAYERS
    ]

    # ━━ 2. 孤立森林模型状态 ━━
    devices = db.query(Device).order_by(Device.id).all()
    models = []
    for d in devices:
        cache_path = MODELS_CACHE_DIR / f'device_{d.id}.joblib'
        entry = {
            'device_id': d.id,
            'device_code': d.device_code,
            'device_name': d.name,
            'status': d.status,
            'trained': False,
            'n_samples': 0,
            'trained_at': None,
            'age_seconds': None,
            'expired': False,
        }
        if cache_path.exists():
            try:
                import joblib
                cached = joblib.load(cache_path)
                trained_at = cached.get('trained_at', 0)
                age = time.time() - trained_at if trained_at else None
                entry.update({
                    'trained': True,
                    'n_samples': cached.get('n_samples', 0),
                    'trained_at': (
                        datetime.fromtimestamp(trained_at).isoformat()
                        if trained_at else None
                    ),
                    'age_seconds': round(age, 1) if age else None,
                    'expired': age is not None and age >= MODEL_TTL_SECONDS,
                })
            except Exception:
                pass  # 缓存损坏，视为未训练
        models.append(entry)

    trained_count = sum(1 for m in models if m['trained'])

    return {
        'layers': layers,
        'models': models,
        'summary': {
            'total_alerts': total_alerts,
            'firing_alerts': firing_alerts,
            'trained_models': trained_count,
            'total_devices': len(devices),
        },
    }
