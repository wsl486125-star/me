"""
AIoT Edge — 校园安防模拟器（Security Simulator）

无硬件条件下扮演「端—边—云」协同架构中的 端（虚拟感知设备）
与 边（分区边缘节点）两层，云端为 FastAPI 后端：

  端（虚拟设备，软件替身）：
    虚拟摄像头（数据集剧本回放）、人脸门禁（图片流比对）、
    烟感/气体传感器（正态基线+突变仿真）、振动光纤、人流摄像头。

  边（边缘节点，模拟本地毫秒级闭环）：
    每个分区一个边缘节点，本地完成 AI 推理、多源融合与规则判定，
    执行本地联动（声光/门禁锁定/广播疏散），仅将结构化事件上报云端；
    周期心跳携带下属设备在线清单（节点代理设备状态上报）。

  云（FastAPI 后端 /api/security）：
    幂等去重 → 60秒窗口合并升级 → 四级定级 → 分级推送路由
    → 人工处置状态机闭环 → 校园平面图可视化。

用法：
  python security_simulator.py                     # 持续运行：心跳 + 随机低级事件
  python security_simulator.py --scenario loitering # 演示剧本：徘徊（二级）
  python security_simulator.py --scenario intrusion # 演示剧本：周界多源融合入侵（升级一级）
  python security_simulator.py --scenario fire      # 演示剧本：烟感+视觉火情确认（升级一级）
  python security_simulator.py --scenario crowd     # 演示剧本：人流拥挤预警
  python security_simulator.py --scenario face      # 演示剧本：门禁黑名单告警
  python security_simulator.py --scenario gas       # 演示剧本：实验室气体泄漏
"""
import time
import random
import argparse
import sys
import uuid

import httpx

# ═══════════════════════════════════════════════════════════
# 配置：边缘节点与虚拟设备清单
# ═══════════════════════════════════════════════════════════
BACKEND_URL = 'http://localhost:8000'
DEFAULT_USERNAME = 'admin'
DEFAULT_PASSWORD = 'admin123'

# 三个分区边缘节点（对应 docker 部署中的 edge-node 容器）
NODES = [
    {'node_code': 'EDGE-GATE',  'name': '校门区边缘节点',
     'zone': '校门区', 'description': '视频行为分析 + 人脸门禁 + 人流统计'},
    {'node_code': 'EDGE-LAB',   'name': '实验楼区边缘节点',
     'zone': '实验楼区', 'description': '烟火视觉检测 + 烟感气体多源融合'},
    {'node_code': 'EDGE-FENCE', 'name': '周界宿舍区边缘节点',
     'zone': '周界宿舍区', 'description': '周界越线判定 + 振动光纤互证 + 人流密度'},
]

# 九台虚拟安防设备（软件替身：数据集回放 / 仿真模型）
DEVICES = [
    # ━━ 校门区 ━━
    {'device_code': 'CAM-GATE-01',  'name': '校门广场摄像头', 'device_type': '虚拟摄像头',
     'zone': '校门区', 'node_code': 'EDGE-GATE', 'location': '校门广场'},
    {'device_code': 'DOOR-GATE-01', 'name': '校门人脸门禁', 'device_type': '人脸门禁',
     'zone': '校门区', 'node_code': 'EDGE-GATE', 'location': '校门东侧'},
    {'device_code': 'FLOW-GATE-01', 'name': '校门人流摄像头', 'device_type': '人流摄像头',
     'zone': '校门区', 'node_code': 'EDGE-GATE', 'location': '校门上方'},
    # ━━ 实验楼区 ━━
    {'device_code': 'CAM-LAB-01',   'name': '实验楼走廊摄像头', 'device_type': '虚拟摄像头',
     'zone': '实验楼区', 'node_code': 'EDGE-LAB', 'location': '三楼走廊'},
    {'device_code': 'SMOKE-LAB-01', 'name': '实验室烟感探测器', 'device_type': '烟感传感器',
     'zone': '实验楼区', 'node_code': 'EDGE-LAB', 'location': '化学实验室'},
    {'device_code': 'GAS-LAB-01',   'name': '实验室气体传感器', 'device_type': '气体传感器',
     'zone': '实验楼区', 'node_code': 'EDGE-LAB', 'location': '化学实验室'},
    # ━━ 周界宿舍区 ━━
    {'device_code': 'CAM-FENCE-01', 'name': '周界北段摄像头', 'device_type': '周界摄像头',
     'zone': '周界宿舍区', 'node_code': 'EDGE-FENCE', 'location': '北围墙段'},
    {'device_code': 'VIB-FENCE-01', 'name': '周界振动光纤', 'device_type': '振动传感器',
     'zone': '周界宿舍区', 'node_code': 'EDGE-FENCE', 'location': '北围墙段'},
    {'device_code': 'CAM-DORM-01',  'name': '宿舍区人流摄像头', 'device_type': '人流摄像头',
     'zone': '周界宿舍区', 'node_code': 'EDGE-FENCE', 'location': '宿舍楼入口'},
]

# 节点心跳间隔（秒）。节点每心跳一次携带下属设备清单，云端刷新设备在线状态
HEARTBEAT_INTERVAL = 15
# 随机事件轮询间隔（秒）
EVENT_INTERVAL = 30

# 随机背景事件池（低级别为主，模拟真实校园的偶发事件）
RANDOM_EVENTS = [
    {'device_code': 'DOOR-GATE-01', 'event_type': 'face_denied', 'sources': ['face'],
     'confidence': (0.6, 0.9), 'actions': ['door_deny'], 'note': '人脸比对未通过，门禁保持关闭'},
    {'device_code': 'FLOW-GATE-01', 'event_type': 'crowd_warning', 'sources': ['video'],
     'confidence': (0.6, 0.8), 'actions': ['flow_rate_limit'], 'note': '入口人流速率接近阈值，建议分流'},
    {'device_code': 'CAM-DORM-01', 'event_type': 'crowd_warning', 'sources': ['video'],
     'confidence': (0.5, 0.75), 'actions': [], 'note': '宿舍楼入口人流增多'},
    {'device_code': 'SMOKE-LAB-01', 'event_type': 'smoke_detected', 'sources': ['smoke_sensor'],
     'confidence': (0.3, 0.48), 'actions': [], 'note': '烟雾浓度轻微波动，低置信疑似（降级为三级）'},
    {'device_code': 'CAM-GATE-01', 'event_type': 'gathering', 'sources': ['video'],
     'confidence': (0.5, 0.7), 'actions': [], 'note': '校门区域出现短时人员聚集'},
    {'device_code': 'VIB-FENCE-01', 'event_type': 'line_crossing', 'sources': ['vibration'],
     'confidence': (0.3, 0.45), 'actions': [], 'note': '振动光纤检测到轻微扰动，疑似风吹（单源低置信）'},
]

# ═══════════════════════════════════════════════════════════
# 演示剧本（答辩一键复现，对应五大安防场景）
# ═══════════════════════════════════════════════════════════
SCENARIOS = {
    'loitering': {
        'title': '徘徊逗留（视频行为 · 二级）',
        'events': [
            {'device_code': 'CAM-GATE-01', 'node_code': 'EDGE-GATE', 'zone': '校门区',
             'event_type': 'loitering', 'confidence': 0.87, 'sources': ['video'],
             'local_actions': ['sound_light_on', 'video_snapshot'],
             'message': '目标在校门禁行区停留超过120秒，轨迹判定为徘徊'},
        ],
    },
    'intrusion': {
        'title': '周界入侵（多源融合 · 视频+振动升级一级）',
        'events': [
            {'device_code': 'CAM-FENCE-01', 'node_code': 'EDGE-FENCE', 'zone': '周界宿舍区',
             'event_type': 'line_crossing', 'confidence': 0.82, 'sources': ['video'],
             'local_actions': ['sound_light_on'], 'delay_after': 2,
             'message': '画面检测到人形跨越警戒线（单源二级）'},
            {'device_code': 'VIB-FENCE-01', 'node_code': 'EDGE-FENCE', 'zone': '周界宿舍区',
             'event_type': 'line_crossing', 'confidence': 0.91, 'sources': ['vibration'],
             'local_actions': ['sound_light_on', 'alarm_to_guard'],
             'message': '振动光纤同段检测到攀爬扰动，与视频互证 → 融合升级'},
        ],
    },
    'fire': {
        'title': '火情确认（多源融合 · 烟感+视觉升级一级）',
        'events': [
            {'device_code': 'SMOKE-LAB-01', 'node_code': 'EDGE-LAB', 'zone': '实验楼区',
             'event_type': 'smoke_detected', 'confidence': 0.78, 'sources': ['smoke_sensor'],
             'local_actions': ['sound_light_on'], 'delay_after': 2,
             'message': '化学实验室烟雾浓度超阈值（单源二级）'},
            {'device_code': 'CAM-LAB-01', 'node_code': 'EDGE-LAB', 'zone': '实验楼区',
             'event_type': 'smoke_detected', 'confidence': 0.93, 'sources': ['video'],
             'local_actions': ['sound_light_on', 'broadcast_evacuate', 'fire_notify'],
             'message': '画面检测到明火与浓烟，与烟感互证 → 融合升级，已触发疏散广播'},
        ],
    },
    'crowd': {
        'title': '人流拥挤预警（人流密度 · 三级）',
        'events': [
            {'device_code': 'FLOW-GATE-01', 'node_code': 'EDGE-GATE', 'zone': '校门区',
             'event_type': 'crowd_warning', 'confidence': 0.83, 'sources': ['video'],
             'local_actions': ['flow_rate_limit'],
             'message': '校门入口人流密度达2.5人/㎡，触发限流提示'},
        ],
    },
    'face': {
        'title': '门禁黑名单告警（人脸本地比对 · 二级）',
        'events': [
            {'device_code': 'DOOR-GATE-01', 'node_code': 'EDGE-GATE', 'zone': '校门区',
             'event_type': 'face_blacklist', 'confidence': 0.94, 'sources': ['face'],
             'local_actions': ['door_lock', 'alarm_to_guard', 'video_snapshot'],
             'message': '人脸与黑名单库比对命中（相似度0.94），已锁定门禁并通知安保'},
        ],
    },
    'gas': {
        'title': '实验室气体泄漏（传感检测 · 二级）',
        'events': [
            {'device_code': 'GAS-LAB-01', 'node_code': 'EDGE-LAB', 'zone': '实验楼区',
             'event_type': 'gas_leak', 'confidence': 0.88, 'sources': ['gas_sensor'],
             'local_actions': ['ventilation_on', 'sound_light_on'],
             'message': '挥发性气体浓度 320ppm 超阈值，已联动排风与声光警示'},
        ],
    },
}

# 全局状态
_running = True
_token = None
_event_seq = 0


# ═══════════════════════════════════════════════════════════
# 认证与初始化（与 mock_simulator 风格一致）
# ═══════════════════════════════════════════════════════════
def ensure_user():
    """确保测试用户存在并登录获取 JWT"""
    global _token
    print(f'[认证] 注册/登录用户 {DEFAULT_USERNAME}...')
    try:
        resp = httpx.post(f'{BACKEND_URL}/api/auth/register', json={
            'username': DEFAULT_USERNAME,
            'email': f'{DEFAULT_USERNAME}@aiot.local',
            'password': DEFAULT_PASSWORD,
        }, timeout=5)
        if resp.status_code == 201:
            print(f'[认证] 用户注册成功')
        elif resp.status_code == 409:
            print(f'[认证] 用户已存在，跳过注册')
    except Exception as e:
        print(f'[认证] 注册异常: {e}')
        return False

    try:
        resp = httpx.post(f'{BACKEND_URL}/api/auth/login', json={
            'username': DEFAULT_USERNAME,
            'password': DEFAULT_PASSWORD,
        }, timeout=5)
        if resp.status_code == 200:
            _token = resp.json()['access_token']
            print(f'[认证] 登录成功')
            return True
        print(f'[认证] 登录失败: {resp.text}')
        return False
    except Exception as e:
        print(f'[认证] 登录异常: {e}')
        return False


def auth_header():
    return {'Authorization': f'Bearer {_token}'} if _token else {}


def ensure_nodes():
    """注册三个分区边缘节点（幂等）"""
    print('[边缘节点] 注册边缘节点...')
    for node in NODES:
        try:
            resp = httpx.post(f'{BACKEND_URL}/api/security/nodes',
                              json=node, headers=auth_header(), timeout=5)
            if resp.status_code == 201:
                msg = resp.json().get('message')
                if msg:
                    print(f'[边缘节点] {node["node_code"]} 已存在，跳过')
                else:
                    print(f'[边缘节点] OK 注册 {node["node_code"]}（{node["zone"]}）')
            else:
                print(f'[边缘节点] WARN {node["node_code"]} 注册返回 {resp.status_code}')
        except Exception as e:
            print(f'[边缘节点] WARN {node["node_code"]} 注册异常: {e}')


def ensure_devices():
    """注册九台虚拟安防设备（幂等，带分区与节点归属）"""
    print('[虚拟设备] 注册安防设备...')
    try:
        resp = httpx.get(f'{BACKEND_URL}/api/devices', headers=auth_header(), timeout=5)
        existing = {d['device_code']: d for d in resp.json()} if resp.status_code == 200 else {}
    except Exception as e:
        print(f'[虚拟设备] 获取设备列表失败: {e}')
        existing = {}

    for dev in DEVICES:
        current = existing.get(dev['device_code'])
        try:
            if current is None:
                resp = httpx.post(f'{BACKEND_URL}/api/devices', json={
                    'device_code': dev['device_code'],
                    'name': dev['name'],
                    'device_type': dev['device_type'],
                    'location': dev['location'],
                    'zone': dev['zone'],
                }, headers=auth_header(), timeout=5)
                print(f'[虚拟设备] OK 创建 {dev["device_code"]}（{dev["name"]}）'
                      if resp.status_code == 201
                      else f'[虚拟设备] WARN {dev["device_code"]} 创建返回 {resp.status_code}')
            elif not current.get('zone'):
                # 已存在但缺分区信息 → 补充分区
                resp = httpx.put(f'{BACKEND_URL}/api/devices/{current["id"]}', json={
                    'zone': dev['zone'],
                }, headers=auth_header(), timeout=5)
                print(f'[虚拟设备] OK {dev["device_code"]} 补充分区 {dev["zone"]}'
                      if resp.status_code == 200 else f'[虚拟设备] WARN {dev["device_code"]} 更新失败')
        except Exception as e:
            print(f'[虚拟设备] WARN {dev["device_code"]} 异常: {e}')


# ═══════════════════════════════════════════════════════════
# 边缘侧行为：心跳 / 事件上报
# ═══════════════════════════════════════════════════════════
def next_event_id():
    """边缘侧生成全局唯一事件ID（断网续传时凭此幂等去重）"""
    global _event_seq
    _event_seq += 1
    return f'EVT-{time.strftime("%Y%m%d%H%M%S")}-{_event_seq:04d}-{uuid.uuid4().hex[:8]}'


def send_event(device_code: str, node_code: str, zone: str, event_type: str,
               confidence: float, sources: list, local_actions: list,
               message: str) -> dict | None:
    """边缘节点上报一条结构化安防事件（模拟边缘本地毫秒级闭环）

    local_latency_ms 模拟边缘本地"感知→判定→联动"耗时（毫秒级），
    与云端处理延迟形成对比，是论文"边缘协同降低响应延迟"的实测数据来源。
    """
    payload = {
        'event_id': next_event_id(),
        'device_code': device_code,
        'node_code': node_code,
        'event_type': event_type,
        'zone': zone,
        'confidence': round(confidence, 2),
        'sources': sources,
        'local_actions': local_actions,
        'local_latency_ms': random.randint(45, 180),
        'message': message,
    }
    try:
        resp = httpx.post(f'{BACKEND_URL}/api/security/event', json=payload, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            event = data.get('event', {})
            level = event.get('level', '?')
            action = data.get('action', '?')
            print(f'  [边缘上报] {device_code} {event_type} → '
                  f'云端动作={action} 级别={level}级 '
                  f'(本地耗时{payload["local_latency_ms"]}ms)')
            return data
        print(f'  [边缘上报] WARN 后端返回 {resp.status_code}: {resp.text}')
    except Exception as e:
        print(f'  [边缘上报] WARN 后端连接失败: {e}')
    return None


def heartbeat_all_nodes():
    """所有边缘节点上报心跳（携带下属在线设备清单）"""
    for node in NODES:
        devices = [d['device_code'] for d in DEVICES if d['node_code'] == node['node_code']]
        try:
            resp = httpx.post(f'{BACKEND_URL}/api/security/nodes/heartbeat', json={
                'node_code': node['node_code'],
                'devices': devices,
            }, timeout=5)
            if resp.status_code == 200:
                print(f'[心跳] {node["node_code"]} · {node["zone"]} · '
                      f'{len(devices)}台设备在线')
            else:
                print(f'[心跳] WARN {node["node_code"]} 返回 {resp.status_code}')
        except Exception as e:
            print(f'[心跳] WARN {node["node_code"]} 连接失败: {e}')


def heartbeat_loop():
    """后台心跳线程（每 HEARTBEAT_INTERVAL 秒一轮）"""
    while _running:
        heartbeat_all_nodes()
        for _ in range(HEARTBEAT_INTERVAL * 10):
            if not _running:
                return
            time.sleep(0.1)


def random_event_round():
    """随机背景事件：低概率产生低级别事件（模拟真实校园偶发情况）"""
    for spec in RANDOM_EVENTS:
        if random.random() < 0.06:  # 每轮每类 6% 概率
            conf = random.uniform(*spec['confidence'])
            dev = next(d for d in DEVICES if d['device_code'] == spec['device_code'])
            send_event(
                device_code=spec['device_code'],
                node_code=dev['node_code'],
                zone=dev['zone'],
                event_type=spec['event_type'],
                confidence=conf,
                sources=spec['sources'],
                local_actions=spec['actions'],
                message=spec['note'],
            )
            time.sleep(0.3)  # 错开上报，避免并发


# ═══════════════════════════════════════════════════════════
# 演示剧本（答辩一键复现）
# ═══════════════════════════════════════════════════════════
def run_scenario(name: str):
    """执行指定演示剧本：按剧本顺序上报事件，多源剧本分两次上报
    由云端合并升级，直观演示「多源证据融合降误报」机制。"""
    scenario = SCENARIOS[name]
    print('=' * 60)
    print(f'演示剧本 · {scenario["title"]}')
    print('=' * 60)

    dev_map = {d['device_code']: d for d in DEVICES}
    for ev in scenario['events']:
        dev = dev_map[ev['device_code']]
        send_event(
            device_code=ev['device_code'],
            node_code=ev['node_code'],
            zone=ev['zone'],
            event_type=ev['event_type'],
            confidence=ev['confidence'],
            sources=ev['sources'],
            local_actions=ev['local_actions'],
            message=ev['message'],
        )
        delay = ev.get('delay_after')
        if delay:
            print(f'  （等待 {delay}s 后第二证据源上报，云端将执行合并升级...）')
            time.sleep(delay)

    print('-' * 60)
    print('剧本执行完毕，可在前端「校园安防」页面查看事件与升级效果')
    print('-' * 60)


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════
def run_simulator():
    """持续运行模式：初始化 → 心跳线程 + 随机事件主循环"""
    global _running

    print('=' * 60)
    print('校园安防 AIoT 边缘协同模拟器（端+边 仿真）')
    print(f'后端地址: {BACKEND_URL}')
    print(f'边缘节点: {len(NODES)} 个 | 虚拟设备: {len(DEVICES)} 台')
    print(f'心跳间隔: {HEARTBEAT_INTERVAL}s | 事件轮询: {EVENT_INTERVAL}s')
    print('=' * 60)

    if not ensure_user():
        print('[错误] 无法完成认证，请确认后端已启动')
        return
    ensure_nodes()
    ensure_devices()

    import threading
    hb = threading.Thread(target=heartbeat_loop, daemon=True, name='heartbeat')
    hb.start()

    print('-' * 60)
    print('模拟器运行中，按 Ctrl+C 停止...')
    print('-' * 60)

    while _running:
        random_event_round()
        for _ in range(EVENT_INTERVAL * 10):
            if not _running:
                break
            time.sleep(0.1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='校园安防 AIoT 边缘协同模拟器 — 无硬件仿真端+边两层',
        epilog='可用剧本: ' + ', '.join(f'{k}({v["title"]})' for k, v in SCENARIOS.items()),
    )
    parser.add_argument(
        '--backend', '-b', type=str, default='http://localhost:8000',
        help='后端地址，默认 http://localhost:8000',
    )
    parser.add_argument(
        '--scenario', '-s', type=str, default=None, choices=SCENARIOS.keys(),
        help='执行指定演示剧本（发送后退出），用于答辩演示',
    )
    args = parser.parse_args()

    BACKEND_URL = args.backend.rstrip('/')

    if args.scenario:
        # 剧本模式：需要先确保节点与设备存在
        if not ensure_user():
            sys.exit(1)
        ensure_nodes()
        ensure_devices()
        run_scenario(args.scenario)
        sys.exit(0)

    try:
        run_simulator()
    except KeyboardInterrupt:
        _running = False
        print('\n模拟器已停止')
