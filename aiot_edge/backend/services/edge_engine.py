"""
边缘计算规则引擎

本模块模拟在网络边缘侧（靠近设备）进行的轻量级实时数据处理，
区别于云端集中式处理：数据先在此层完成清洗、统计与异常判定，
只有判定结果（是否异常+告警信息）才需要进一步处理，
降低了对云端/中心节点算力和带宽的依赖。

本系统不使用深度学习等复杂AI模型，而是采用基于规则的方法
（阈值判断 + 滑动窗口统计 + 孤立森林），原因：
  1. 物联网边缘设备通常算力和内存有限，复杂模型部署成本高
  2. 规则引擎延迟极低，满足实时性要求
  3. 规则可解释、可审计，便于运维人员理解告警原因并快速处置
  4. 对中小型场景，规则引擎的检测效果已能满足实际需求

三层检测体系：
  第一层 - 阈值规则：即时判断单项指标是否超过硬性上限（如CPU>85%），
           响应最快，逻辑最简单，负责'明确超标'的情况。
  第二层 - 滑动窗口统计：判断单项指标相对近期均值是否突增，
           能发现'相对自己历史的异常'，比静态阈值更灵活。
  第三层 - 孤立森林模型：联合cpu_usage/memory_usage/network_latency
           三个维度，判断'组合起来是否反常'，能发现前两层都漏判的
           深层异常（例如三项指标都接近但不超过各自阈值，但三者
           同时偏高的组合在历史上从未出现过）。
"""
import os
import time
import math
import threading
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import desc

from core.config import settings
from models import Device, DeviceMetric

# ═══════════════════════════════════════════════════════════
# 模型缓存路径
# ═══════════════════════════════════════════════════════════
MODELS_CACHE_DIR = Path(__file__).parent.parent / 'models_cache'
MODEL_TTL_SECONDS = 3600  # 模型缓存1小时过期

# ━━ 进程内模型缓存 ━━
# ml_detect_anomaly 会在「前两层未报警」的每一条数据上被调用（正常数据下几乎
# 每条都走这里）。若每次都 joblib.load 反序列化 100 棵树的孤立森林，CPU 开销大
# 且会延长数据库连接的持有时间，10 台设备并发时足以拖垮连接池。
# 这里在进程内缓存已加载的模型对象，把每条数据的开销降到一次字典查找。
#   key   → device_id
#   value → (加载时间戳, 模型对象或 None)
#           None 表示「历史数据不足、暂时无法训练」，用较短 TTL 负缓存避免
#           每条数据都重复查询 200 行。
_MODEL_MEM_CACHE: dict = {}
_MODEL_NEGATIVE_TTL = 60      # 负缓存 60s
_MODEL_LOCK = threading.Lock()  # 保证同一时刻只有一个线程在训练，避免冷启动惊群

# 严重程度排序（值越大越严重，用于多规则取最高）
SEVERITY_ORDER = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}


def _max_severity(a: dict, b: dict) -> dict:
    """返回两个异常结果中严重程度更高的那个"""
    if SEVERITY_ORDER.get(a.get('severity', 'low'), 0) >= SEVERITY_ORDER.get(b.get('severity', 'low'), 0):
        return a
    return b


# ═══════════════════════════════════════════════════════════
# 第一层 + 第二层：规则引擎
# ═══════════════════════════════════════════════════════════

def clean_data(raw_data: dict) -> dict:
    """数据清洗

    防御性编程：对采集器转发过来的数据进行范围校验，
    应对转发过程中可能出现的数据异常。
    psutil 采集的真实数据理论上不会越界，但这一步保证了
    后续规则引擎处理的可靠性。
    """
    cpu = raw_data.get('cpu_usage', 0)
    mem = raw_data.get('memory_usage', 0)
    lat = raw_data.get('network_latency', 0)

    # 数值范围校验：cpu/memory 限制在 [0, 100]
    cpu = max(0.0, min(100.0, float(cpu)))
    mem = max(0.0, min(100.0, float(mem)))

    # 延迟不能为负数
    lat = max(0.0, float(lat))

    return {
        'cpu_usage': cpu,
        'memory_usage': mem,
        'network_latency': lat,
    }


def detect_anomaly(device_id: int, metric: dict, db: Session) -> dict:
    """核心异常检测 — 结合阈值判断与滑动窗口统计分析

    规则A（阈值判断 — 即时检测）：
      - cpu_usage > 85% → cpu_high, severity=high
      - network_latency > 200ms → latency_high, severity=medium
      - memory_usage > 90% → memory_high, severity=high

    规则B（滑动窗口统计 — 需要历史数据累积）：
      - 查询该设备最近10条 CPU 数据
      - 若本次 > mean + 2*std（需>=5条历史才启用）→ cpu_spike, severity=medium

    若同时触发多条规则，只返回严重程度最高的一条。
    """
    anomalies = []

    cpu = metric['cpu_usage']
    mem = metric['memory_usage']
    lat = metric['network_latency']

    # ━━ 规则A：阈值判断 ━━
    if cpu > settings.CPU_THRESHOLD:
        anomalies.append({
            'is_anomaly': True,
            'alert_type': 'cpu_high',
            'severity': 'high',
            'metric_value': cpu,
            'threshold': settings.CPU_THRESHOLD,
            'message': f'CPU使用率 {cpu:.1f}% 超过阈值 {settings.CPU_THRESHOLD}%',
        })

    if lat > settings.LATENCY_THRESHOLD:
        anomalies.append({
            'is_anomaly': True,
            'alert_type': 'latency_high',
            'severity': 'medium',
            'metric_value': lat,
            'threshold': settings.LATENCY_THRESHOLD,
            'message': f'网络延迟 {lat:.1f}ms 超过阈值 {settings.LATENCY_THRESHOLD}ms',
        })

    if mem > 90.0:
        anomalies.append({
            'is_anomaly': True,
            'alert_type': 'memory_high',
            'severity': 'high',
            'metric_value': mem,
            'threshold': 90.0,
            'message': f'内存使用率 {mem:.1f}% 超过阈值 90%',
        })

    # ━━ 规则B：滑动窗口统计 ━━
    recent_cpu = (
        db.query(DeviceMetric.cpu_usage)
        .filter(DeviceMetric.device_id == device_id)
        .filter(DeviceMetric.cpu_usage.isnot(None))
        .order_by(desc(DeviceMetric.collected_at))
        .limit(10)
        .all()
    )
    # recent_cpu 是 [(value,), ...] 的列表
    cpu_values = [r[0] for r in recent_cpu if r[0] is not None]

    if len(cpu_values) >= 5:
        mean_cpu = sum(cpu_values) / len(cpu_values)
        # 样本标准差
        variance = sum((x - mean_cpu) ** 2 for x in cpu_values) / len(cpu_values)
        std_cpu = math.sqrt(variance) if variance > 0 else 0.001  # 避免除零

        if cpu > mean_cpu + 2 * std_cpu:
            anomalies.append({
                'is_anomaly': True,
                'alert_type': 'cpu_spike',
                'severity': 'medium',
                'metric_value': cpu,
                'threshold': round(mean_cpu + 2 * std_cpu, 2),
                'message': (
                    f'CPU使用率 {cpu:.1f}% 相较近期均值 {mean_cpu:.1f}% '
                    f'出现显著突增（+{std_cpu:.1f}σ）'
                ),
            })

    # ━━ 取最高严重程度 ━━
    if not anomalies:
        return {'is_anomaly': False}

    result = anomalies[0]
    for a in anomalies[1:]:
        result = _max_severity(result, a)
    return result


# ═══════════════════════════════════════════════════════════
# 离线检测
# ═══════════════════════════════════════════════════════════

def check_offline_devices(db: Session) -> list:
    """离线检测规则

    查询所有 status='online' 的设备，
    若 now() - last_seen_at > OFFLINE_TIMEOUT_SECONDS（默认30秒），
    则判定为离线并更新设备状态。

    返回：触发离线告警的设备列表
    """
    now = datetime.now()
    timeout = timedelta(seconds=settings.OFFLINE_TIMEOUT_SECONDS)

    online_devices = db.query(Device).filter(Device.status == 'online').all()
    offline_devices = []

    for device in online_devices:
        if device.last_seen_at is None:
            continue
        if now - device.last_seen_at > timeout:
            device.status = 'offline'
            offline_devices.append(device)

    return offline_devices


# ═══════════════════════════════════════════════════════════
# 第三层：孤立森林（Isolation Forest）模型检测
# ═══════════════════════════════════════════════════════════

def train_device_model(device_id: int, db: Session):
    """训练设备的孤立森林异常检测模型

    1. 查询该设备最近 200 条 DeviceMetric 历史记录
    2. 若历史记录数 < 50，返回 None（数据不足，交由前两层规则兜底）
    3. 取 [cpu_usage, memory_usage, network_latency] 三列训练
    4. 用 joblib 将模型缓存到 models_cache/ 目录
    5. 返回训练好的模型对象
    """
    from sklearn.ensemble import IsolationForest
    import joblib

    rows = (
        db.query(
            DeviceMetric.cpu_usage,
            DeviceMetric.memory_usage,
            DeviceMetric.network_latency,
        )
        .filter(DeviceMetric.device_id == device_id)
        .filter(DeviceMetric.cpu_usage.isnot(None))
        .filter(DeviceMetric.memory_usage.isnot(None))
        .filter(DeviceMetric.network_latency.isnot(None))
        .order_by(desc(DeviceMetric.collected_at))
        .limit(200)
        .all()
    )

    if len(rows) < 50:
        return None  # 数据不足，无法训练

    # 构建训练矩阵
    X = np.array(rows, dtype=np.float64)

    # 训练孤立森林
    model = IsolationForest(
        contamination=0.1,       # 预期异常比例 10%
        random_state=42,
        n_estimators=100,
        n_jobs=-1,
    )
    model.fit(X)

    # 缓存到本地
    MODELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = MODELS_CACHE_DIR / f'device_{device_id}.joblib'
    joblib.dump(
        {'model': model, 'trained_at': time.time(), 'n_samples': len(rows)},
        cache_path,
    )

    return model


def get_or_train_model(device_id: int, db: Session):
    """获取或训练孤立森林模型

    查找顺序（逐级兜底，命中即返回）：
      1. 进程内缓存（最快，命中率最高）
      2. 磁盘缓存 models_cache/device_{id}.joblib（未过期）
      3. 现场训练 —— 用全局锁串行化，避免多设备冷启动同时训练打满 CPU

    模型过期时间：1小时，保证模型能跟上设备运行状态的变化。
    """
    now = time.time()

    # ━━ 1. 进程内缓存 ━━
    hit = _MODEL_MEM_CACHE.get(device_id)
    if hit is not None:
        loaded_at, model = hit
        ttl = MODEL_TTL_SECONDS if model is not None else _MODEL_NEGATIVE_TTL
        if now - loaded_at < ttl:
            return model

    # ━━ 2/3. 加锁后二次检查并加载/训练 ━━
    with _MODEL_LOCK:
        # 双重检查：等锁期间可能已被其他线程填充
        hit = _MODEL_MEM_CACHE.get(device_id)
        if hit is not None:
            loaded_at, model = hit
            ttl = MODEL_TTL_SECONDS if model is not None else _MODEL_NEGATIVE_TTL
            if now - loaded_at < ttl:
                return model

        import joblib

        cache_path = MODELS_CACHE_DIR / f'device_{device_id}.joblib'

        # 磁盘缓存（未过期）
        if cache_path.exists():
            try:
                cached = joblib.load(cache_path)
                age = time.time() - cached.get('trained_at', 0)
                if age < MODEL_TTL_SECONDS:
                    model = cached['model']
                    _MODEL_MEM_CACHE[device_id] = (time.time(), model)
                    return model
            except Exception:
                pass  # 缓存损坏，走重新训练

        # 训练新模型
        model = train_device_model(device_id, db)
        # 训练结果（含 None = 数据不足）一并缓存，避免逐条重复查询
        _MODEL_MEM_CACHE[device_id] = (time.time(), model)
        return model


def ml_detect_anomaly(device_id: int, metric: dict, db: Session) -> dict:
    """孤立森林模型异常检测

    联合 cpu_usage / memory_usage / network_latency 三个维度，
    判断'组合起来是否反常'。能发现前两层都漏判的深层异常：
    例如三项指标都接近但不超过各自阈值，但三者同时偏高的
    组合在历史上从未出现过。

    算法原理：异常点因为稀少、和大多数据差异大，随机切分几次就能
    被单独分离出来；正常点因为扎堆，需要切很多次才能分离。
    切分次数越少，越可能是异常。
    """
    model = get_or_train_model(device_id, db)

    if model is None:
        return {'is_anomaly': False}  # 数据不足，跳过此层

    cpu = metric['cpu_usage']
    mem = metric['memory_usage']
    lat = metric['network_latency']

    X = np.array([[cpu, mem, lat]], dtype=np.float64)

    # predict: -1 表示异常，1 表示正常
    prediction = model.predict(X)[0]

    if prediction == -1:
        # 获取异常分数（越负越异常）
        score = model.score_samples(X)[0]
        return {
            'is_anomaly': True,
            'alert_type': 'ml_anomaly',
            'severity': 'medium',
            'metric_value': None,
            'threshold': None,
            'message': (
                f'孤立森林模型检测到多指标组合异常'
                f'（异常分数: {score:.3f}），'
                f'当前 CPU={cpu:.1f}% 内存={mem:.1f}% 延迟={lat:.1f}ms '
                f'的组合在历史数据中较为罕见'
            ),
        }

    return {'is_anomaly': False}
