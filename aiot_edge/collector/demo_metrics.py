"""
AIoT Edge — 演示数据生成器（Demo Metric Generator）

用途：
  真实采集器从 Docker 容器读取的 psutil 空闲数据偏低（CPU ~1-2%、磁盘 ~0.2%），
  不利于演示系统的趋势图 / 设备列表 / 边缘计算告警效果。本脚本生成「偏高但
  真实合理」的运行指标，POST 到 /api/ingest/metric，走完整的三层检测流程，
  让 CPU/内存/磁盘占用率在演示时更有表现力。

用法：
    # 连续生成（默认每 5 秒一轮，Ctrl+C 停止）
    python demo_metrics.py
    # 自定义间隔
    python demo_metrics.py --interval 3
    # 只生成一轮就退出（快速验证）
    python demo_metrics.py --once
    # 指定后端地址
    python demo_metrics.py --backend http://localhost:8000

注意：
  请先停止真实采集器（Ctrl+C），避免两者同时向同一批设备写入数据、
  互相覆盖导致图表忽高忽低。
"""
import argparse
import random
import time

import requests

BACKEND_URL = 'http://localhost:8000'

# ═══════════════════════════════════════════════════════════
# 演示设备清单（含离线传感器 DEV-004，演示时会将其唤醒上线）
# 每项区间为 (min, max)：cpu / mem / disk / latency / bandwidth
# ═══════════════════════════════════════════════════════════
DEMO_DEVICES = [
    {'device_code': 'DEV-001', 'device_type': '路由器',
     'cpu': (52, 74), 'mem': (58, 74), 'disk': (66, 74),
     'lat': (40, 85), 'bw': (120, 190)},
    {'device_code': 'DEV-002', 'device_type': '交换机',
     'cpu': (46, 68), 'mem': (54, 70), 'disk': (60, 68),
     'lat': (16, 42), 'bw': (300, 480)},
    {'device_code': 'DEV-003', 'device_type': '网关',
     'cpu': (60, 86), 'mem': (64, 82), 'disk': (74, 82),
     'lat': (60, 125), 'bw': (200, 320)},
    {'device_code': 'DEV-004', 'device_type': '传感器',
     'cpu': (36, 56), 'mem': (44, 62), 'disk': (52, 60),
     'lat': (110, 280), 'bw': (8, 26)},
]

# 每个设备的随机游走状态
_state = {}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _walk(cur, lo, hi, step):
    """带边界的随机游走，让曲线自然波动"""
    return _clamp(cur + random.uniform(-step, step), lo, hi)


def gen_metrics(dev):
    """为单台设备生成一轮「偏高」指标"""
    code = dev['device_code']
    st = _state.setdefault(code, {
        'cpu': random.uniform(*dev['cpu']),
        'mem': random.uniform(*dev['mem']),
        'disk': dev['disk'][0],          # 磁盘从区间下界开始，缓慢爬升
        'lat': random.uniform(*dev['lat']),
        'bw': random.uniform(*dev['bw']),
    })

    st['cpu'] = _walk(st['cpu'], *dev['cpu'], 7)
    st['mem'] = _walk(st['mem'], *dev['mem'], 3)
    st['disk'] = _clamp(st['disk'] + random.uniform(0, 1.2), *dev['disk'])  # 磁盘只升不降
    st['lat'] = _walk(st['lat'], *dev['lat'], 15)
    st['bw'] = _walk(st['bw'], *dev['bw'], 15)

    # 小概率触发尖峰，便于演示三层检测 / 告警
    if random.random() < 0.08:
        st['cpu'] = random.uniform(90, 98)          # CPU 尖峰 → cpu_high / cpu_spike
    if random.random() < 0.06:
        st['lat'] = random.uniform(300, 600)        # 延迟尖峰 → latency_high

    return {
        'device_code': code,
        'cpu_usage': round(st['cpu'], 2),
        'memory_usage': round(st['mem'], 2),
        'network_latency': round(st['lat'], 2),
        'bandwidth_usage': round(st['bw'], 2),
        'disk_usage': round(st['disk'], 2),
    }


def _post_round():
    """把一轮数据 POST 到后端，逐台打印"""
    for dev in DEMO_DEVICES:
        payload = gen_metrics(dev)
        try:
            resp = requests.post(
                f'{BACKEND_URL}/api/ingest/metric',
                json=payload,
                timeout=5,
            )
            ok = resp.status_code in (200, 201)
            tag = 'OK' if ok else f'FAIL({resp.status_code})'
        except Exception as e:
            tag = f'ERR {e}'
        print(
            f'[{payload["device_code"]}({dev["device_type"]})] '
            f'CPU:{payload["cpu_usage"]:5.1f}%  '
            f'MEM:{payload["memory_usage"]:5.1f}%  '
            f'DISK:{payload["disk_usage"]:5.1f}%  '
            f'LAT:{payload["network_latency"]:6.1f}ms  '
            f'BW:{payload["bandwidth_usage"]:6.2f}Mbps  -> {tag}'
        )


def run(interval, once):
    print('=' * 60)
    print('AIoT Edge 演示数据生成器（Demo Metrics）')
    print(f'后端地址: {BACKEND_URL}')
    print(f'生成间隔: {interval}s')
    print(f'设备数量: {len(DEMO_DEVICES)}')
    print('=' * 60)

    try:
        while True:
            _post_round()
            if once:
                print('已生成一轮，退出。')
                break
            print('-' * 60)
            time.sleep(interval)
    except KeyboardInterrupt:
        print('\n已停止演示数据生成。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='AIoT Edge 演示数据生成器 — 生成偏高的 CPU/内存/磁盘指标用于演示',
    )
    parser.add_argument('--interval', '-i', type=float, default=5.0,
                        help='生成间隔（秒），默认 5')
    parser.add_argument('--backend', '-b', type=str, default='http://localhost:8000',
                        help='后端服务地址，默认 http://localhost:8000')
    parser.add_argument('--once', action='store_true',
                        help='只生成一轮就退出')
    args = parser.parse_args()

    BACKEND_URL = args.backend.rstrip('/')
    run(args.interval, args.once)
