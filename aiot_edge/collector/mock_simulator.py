"""
AIoT Edge — 模拟数据生成器（Mock Data Simulator）

无需 Docker 容器，直接生成模拟的设备运行数据并发送到后端。
支持：
  1. 自动注册用户 + 登录获取 JWT
  2. 自动创建4台模拟设备（路由器/交换机/网关/传感器）
  3. 定时生成模拟运行数据（含正常波动 + 随机异常）
  4. 手动触发异常（--trigger 参数）

用法：
  python mock_simulator.py                        # 正常模式，每5秒发送一轮数据
  python mock_simulator.py --interval 3           # 每3秒一轮
  python mock_simulator.py --trigger DEV-001      # 手动让 DEV-001 产生一次异常数据
  python mock_simulator.py --anomaly-rate 0.15    # 15%概率产生异常（默认8%）
"""
import time
import random
import argparse
import sys

import httpx

# ═══════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════
BACKEND_URL = 'http://localhost:8000'
DEFAULT_USERNAME = 'admin'
DEFAULT_PASSWORD = 'admin123'

# 4台模拟设备
DEVICES = [
    {'device_code': 'DEV-001', 'name': '核心路由器-01', 'device_type': '路由器', 'location': 'A栋-3F机房'},
    {'device_code': 'DEV-002', 'name': '核心交换机-01', 'device_type': '交换机', 'location': 'A栋-3F机房'},
    {'device_code': 'DEV-003', 'name': '边界网关-01',   'device_type': '网关',   'location': 'B栋-1F网络中心'},
    {'device_code': 'DEV-004', 'name': '温湿度传感器-01', 'device_type': '传感器', 'location': 'C栋-2F实验室'},
]

# 全局开关
_running = True
_token = None
_manual_trigger_device = None  # 由 --trigger 设置

# 基准值：每台设备有不同的"正常范围"，让数据看起来更真实
DEVICE_BASELINES = {
    # device_code: (cpu_mean, cpu_std, mem_mean, mem_std, lat_mean, lat_std, bw_mean, bw_std)
    'DEV-001': (35, 10, 55, 8,  12, 8,  80, 30),   # 路由器：CPU中等，带宽较高
    'DEV-002': (25, 8,  45, 10, 5,  3,  120, 40),  # 交换机：CPU较低，带宽很高
    'DEV-003': (40, 12, 60, 10, 20, 12, 60, 25),   # 网关：CPU偏高，延迟中等
    'DEV-004': (15, 5,  30, 8,  8,  5,  10, 5),    # 传感器：资源占用低
}


# ═══════════════════════════════════════════════════════════
# 用户认证
# ═══════════════════════════════════════════════════════════
def ensure_user():
    """确保测试用户存在：先尝试注册（忽略已存在错误），再登录获取 token"""
    global _token
    print(f'[认证] 注册/登录用户 {DEFAULT_USERNAME}...')

    # 尝试注册（可能已存在）
    try:
        resp = httpx.post(f'{BACKEND_URL}/api/auth/register', json={
            'username': DEFAULT_USERNAME,
            'email': f'{DEFAULT_USERNAME}@aiot.local',
            'password': DEFAULT_PASSWORD,
        }, timeout=5)
        if resp.status_code == 201:
            print(f'[认证] 用户 {DEFAULT_USERNAME} 注册成功')
        elif resp.status_code == 409:
            print(f'[认证] 用户已存在，跳过注册')
        else:
            print(f'[认证] 注册返回 {resp.status_code}: {resp.text}')
    except Exception as e:
        print(f'[认证] 注册异常: {e}')
        return False

    # 登录获取 token
    try:
        resp = httpx.post(f'{BACKEND_URL}/api/auth/login', json={
            'username': DEFAULT_USERNAME,
            'password': DEFAULT_PASSWORD,
        }, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            _token = data['access_token']
            print(f'[认证] 登录成功，Token: {_token[:20]}...')
            return True
        else:
            print(f'[认证] 登录失败: {resp.text}')
            return False
    except Exception as e:
        print(f'[认证] 登录异常: {e}')
        return False


def auth_header():
    """返回带 JWT 的请求头"""
    return {'Authorization': f'Bearer {_token}'} if _token else {}


# ═══════════════════════════════════════════════════════════
# 设备管理
# ═══════════════════════════════════════════════════════════
def ensure_devices():
    """确保4台设备已注册（先查询，不存在则创建）"""
    print('[设备] 检查设备注册状态...')
    headers = auth_header()

    # 获取已有设备列表
    try:
        resp = httpx.get(f'{BACKEND_URL}/api/devices', headers=headers, timeout=5)
        existing_codes = set()
        if resp.status_code == 200:
            for dev in resp.json():
                existing_codes.add(dev['device_code'])
        print(f'[设备] 已有设备: {existing_codes if existing_codes else "无"}')
    except Exception as e:
        print(f'[设备] 获取设备列表失败: {e}')
        existing_codes = set()

    # 创建缺失的设备
    created = 0
    for dev in DEVICES:
        if dev['device_code'] in existing_codes:
            continue
        try:
            resp = httpx.post(f'{BACKEND_URL}/api/devices', json={
                'device_code': dev['device_code'],
                'name': dev['name'],
                'device_type': dev['device_type'],
                'location': dev['location'],
            }, headers=headers, timeout=5)
            if resp.status_code == 201:
                print(f'[设备] OK 创建 {dev["device_code"]} ({dev["name"]})')
                created += 1
            elif resp.status_code == 409:
                print(f'[设备] {dev["device_code"]} 已存在，跳过')
            else:
                print(f'[设备] WARN {dev["device_code"]} 创建失败: {resp.text}')
        except Exception as e:
            print(f'[设备] WARN {dev["device_code"]} 创建异常: {e}')

    if created:
        print(f'[设备] 共创建 {created} 台新设备')
    print(f'[设备] 设备就绪 OK')


# ═══════════════════════════════════════════════════════════
# 模拟数据生成
# ═══════════════════════════════════════════════════════════
def generate_metric(device_code: str, force_anomaly: bool = False, anomaly_rate: float = 0.08):
    """根据设备基准值生成一条模拟运行数据

    正常数据：在基准值附近正态分布
    异常数据：有一定概率生成超标数据（CPU>85% / 延迟>200ms）
    """
    bl = DEVICE_BASELINES.get(device_code)
    if bl is None:
        bl = (30, 10, 50, 10, 15, 10, 50, 20)

    cpu_mean, cpu_std, mem_mean, mem_std, lat_mean, lat_std, bw_mean, bw_std = bl

    # 生成正常值（截断正态分布）
    cpu = max(1.0, min(95.0, random.gauss(cpu_mean, cpu_std)))
    mem = max(1.0, min(95.0, random.gauss(mem_mean, mem_std)))
    lat = max(0.5, random.gauss(lat_mean, lat_std))
    bw = max(0.1, random.gauss(bw_mean, bw_std))

    # 是否触发异常？
    is_anomaly = force_anomaly or (random.random() < anomaly_rate)

    if is_anomaly:
        anomaly_type = random.choice(['cpu', 'latency', 'cpu_spike', 'combo'])
        if anomaly_type == 'cpu':
            cpu = random.uniform(86, 98)
        elif anomaly_type == 'latency':
            lat = random.uniform(210, 800)
        elif anomaly_type == 'cpu_spike':
            cpu = random.uniform(70, 95)  # 相对自身均值突增
        elif anomaly_type == 'combo':
            cpu = random.uniform(78, 92)
            lat = random.uniform(160, 350)

    return {
        'device_code': device_code,
        'cpu_usage': round(cpu, 2),
        'memory_usage': round(mem, 2),
        'network_latency': round(lat, 2),
        'bandwidth_usage': round(bw, 2),
    }


# ═══════════════════════════════════════════════════════════
# 单次上报
# ═══════════════════════════════════════════════════════════
def send_metric(device_code: str, anomaly_rate: float):
    """生成并发送一台设备的数据"""
    force = (_manual_trigger_device == device_code)
    metric = generate_metric(device_code, force_anomaly=force, anomaly_rate=anomaly_rate)

    anomaly_marker = ''
    if force:
        anomaly_marker = ' [手动触发异常!]'

    try:
        resp = httpx.post(
            f'{BACKEND_URL}/api/ingest/metric',
            json=metric,
            timeout=5,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            flag = 'ANOMALY!' if data.get('anomaly_detected') else 'OK'
            print(
                f'[{device_code}] CPU:{metric["cpu_usage"]:5.1f}%  '
                f'MEM:{metric["memory_usage"]:5.1f}%  '
                f'LAT:{metric["network_latency"]:6.1f}ms  '
                f'BW:{metric["bandwidth_usage"]:6.1f}Mbps  -> {flag}{anomaly_marker}'
            )
        else:
            print(f'[{device_code}] 后端返回 {resp.status_code}: {resp.text}')
    except Exception as e:
        print(f'[{device_code}] WARN 后端连接失败: {e}')


def send_all_devices(anomaly_rate: float):
    """向所有设备发送一轮数据"""
    for dev in DEVICES:
        send_metric(dev['device_code'], anomaly_rate)


# ═══════════════════════════════════════════════════════════
# 主循环
# ═══════════════════════════════════════════════════════════
def run_simulator(interval: float, anomaly_rate: float):
    """持续运行模拟器"""
    global _running

    print('=' * 60)
    print('AIoT Edge 模拟数据生成器')
    print(f'后端地址: {BACKEND_URL}')
    print(f'发送间隔: {interval}s')
    print(f'异常概率: {anomaly_rate * 100:.0f}%')
    print(f'设备数量: {len(DEVICES)}')
    print('=' * 60)

    # 初始化用户和设备
    if not ensure_user():
        print('[错误] 无法完成认证，请确认后端已启动')
        return
    ensure_devices()

    print('-' * 60)
    print('模拟器运行中，按 Ctrl+C 停止...')
    print('-' * 60)

    while _running:
        send_all_devices(anomaly_rate)

        # 分段 sleep 以响应 Ctrl+C
        for _ in range(int(interval * 10)):
            if not _running:
                break
            time.sleep(0.1)


# ═══════════════════════════════════════════════════════════
# 手动触发异常
# ═══════════════════════════════════════════════════════════
def do_trigger(device_code: str):
    """手动触发一次设备异常数据"""
    print(f'[触发] 向 {device_code} 发送异常数据...')
    metric = generate_metric(device_code, force_anomaly=True)
    print(f'  CPU: {metric["cpu_usage"]}%, MEM: {metric["memory_usage"]}%, '
          f'LAT: {metric["network_latency"]}ms, BW: {metric["bandwidth_usage"]}Mbps')

    try:
        resp = httpx.post(
            f'{BACKEND_URL}/api/ingest/metric',
            json=metric,
            timeout=5,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            if data.get('anomaly_detected'):
                print(f'  OK 异常已被边缘计算引擎检测到！')
            else:
                print(f'  - 数据已接收，未触发告警')
        else:
            print(f'  WARN 后端返回 {resp.status_code}: {resp.text}')
    except Exception as e:
        print(f'  WARN 后端连接失败: {e}')


# ═══════════════════════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════════════════════
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='AIoT Edge 模拟数据生成器 — 无需Docker即可生成模拟设备数据',
    )
    parser.add_argument(
        '--interval', '-i',
        type=float,
        default=5.0,
        help='数据发送间隔（秒），默认 5',
    )
    parser.add_argument(
        '--backend', '-b',
        type=str,
        default='http://localhost:8000',
        help='后端地址，默认 http://localhost:8000',
    )
    parser.add_argument(
        '--trigger', '-t',
        type=str,
        default=None,
        help='手动触发指定设备的异常数据（如 DEV-001），发送一次后退出',
    )
    parser.add_argument(
        '--anomaly-rate', '-a',
        type=float,
        default=0.08,
        help='每轮每台设备产生异常的概率，默认 0.08（8%%）',
    )
    args = parser.parse_args()

    BACKEND_URL = args.backend.rstrip('/')

    if args.trigger:
        do_trigger(args.trigger)
        sys.exit(0)

    try:
        run_simulator(interval=args.interval, anomaly_rate=args.anomaly_rate)
    except KeyboardInterrupt:
        print('\n模拟器已停止')
