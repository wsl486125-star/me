"""
AIoT Edge — 真实数据采集器（Device Collector）

功能：
  1. 多线程定时拉取每个 Docker 容器 Agent 的真实运行数据
  2. 将数据转发给 FastAPI 后端 /api/ingest/metric
  3. 提供 trigger_workload() 工具函数，可手动触发设备异常负载

注意：本采集器不生成任何数据，只是从容器 Agent 采集真实数据后转发。
      论文中统一使用"采集器"而非"模拟器"。
"""
import time
import signal
import threading
import argparse

import requests

# ═══════════════════════════════════════════════════════════
# 设备清单
# ═══════════════════════════════════════════════════════════
DEVICES = [
    {'device_code': 'DEV-001', 'device_type': '路由器',
     'agent_url': 'http://localhost:9101'},
    {'device_code': 'DEV-002', 'device_type': '交换机',
     'agent_url': 'http://localhost:9102'},
    {'device_code': 'DEV-003', 'device_type': '网关',
     'agent_url': 'http://localhost:9103'},
    {'device_code': 'DEV-004', 'device_type': '传感器',
     'agent_url': 'http://localhost:9104'},
    {'device_code': 'DEV-005', 'device_type': 'NVR录像机',
     'agent_url': 'http://localhost:9105'},
    {'device_code': 'DEV-006', 'device_type': '边缘服务器',
     'agent_url': 'http://localhost:9106'},
    {'device_code': 'DEV-007', 'device_type': '智能电表',
     'agent_url': 'http://localhost:9107'},
    {'device_code': 'DEV-008', 'device_type': '环境控制器',
     'agent_url': 'http://localhost:9108'},
    {'device_code': 'DEV-009', 'device_type': '路由器',
     'agent_url': 'http://localhost:9109'},
    {'device_code': 'DEV-010', 'device_type': '传感器',
     'agent_url': 'http://localhost:9110'},
]

# 全局开关：Ctrl+C 优雅退出
_running = True

# 后端地址（可通过命令行参数覆盖）
BACKEND_URL = 'http://localhost:8000'


def _device_name(dev: dict) -> str:
    """格式化设备显示名称"""
    return f'{dev["device_code"]}({dev["device_type"]})'


def _poll_device(dev: dict, interval: float):
    """单个设备的采集循环（运行在独立线程中）"""
    name = _device_name(dev)
    agent_url = dev['agent_url']

    while _running:
        try:
            # 1. 从容器 Agent 获取真实运行数据
            resp = requests.get(
                f'{agent_url}/metrics',
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()

            # 2. 转发给后端（透传边缘侧就地判定结果 edge_alerts）
            payload = {
                'device_code': dev['device_code'],
                'cpu_usage': data['cpu_usage'],
                'memory_usage': data['memory_usage'],
                'network_latency': data['network_latency'],
                'bandwidth_usage': data['bandwidth_usage'],
                'disk_usage': data.get('disk_usage', 0.0),
                'edge_alerts': data.get('edge_alerts', []),
            }

            backend_resp = requests.post(
                f'{BACKEND_URL}/api/ingest/metric',
                json=payload,
                timeout=5,
            )

            # 3. 终端打印
            workload_tag = ''
            if data.get('workload_active'):
                workload_tag = f' [负载中:{data["workload_remaining_seconds"]}s]'

            edge_tag = ''
            edge_alerts = data.get('edge_alerts', [])
            if edge_alerts:
                edge_tag = f' [边缘预警:{len(edge_alerts)}]'

            if backend_resp.status_code in (200, 201):
                print(
                    f'[{name}] CPU:{data["cpu_usage"]:5.1f}%  '
                    f'MEM:{data["memory_usage"]:5.1f}%  '
                    f'DISK:{data.get("disk_usage", 0.0):5.1f}%  '
                    f'LAT:{data["network_latency"]:6.1f}ms  '
                    f'BW:{data["bandwidth_usage"]:6.2f}Mbps{workload_tag}{edge_tag}  '
                    f'→ 后端OK'
                )
            else:
                print(f'[{name}] 数据获取成功，但后端返回 {backend_resp.status_code}')

        except requests.ConnectionError:
            print(f'[{name}] ⚠ 容器不可达 ({agent_url})，等待重试...')
        except requests.Timeout:
            print(f'[{name}] ⚠ 请求超时 ({agent_url})，等待重试...')
        except Exception as e:
            print(f'[{name}] ⚠ 错误: {e}')

        # 等待下一个采集周期（分段 sleep 以响应 Ctrl+C），最小步数防止小间隔忙循环。
        remaining = max(0.1, interval)
        while _running and remaining > 0:
            step = min(0.1, remaining)
            time.sleep(step)
            remaining -= step


def start_collector(interval: float = 5.0):
    """启动多线程采集器"""
    print('=' * 60)
    print('AIoT Edge 真实数据采集器')
    print(f'后端地址: {BACKEND_URL}')
    print(f'采集间隔: {interval}s')
    print(f'设备数量: {len(DEVICES)}')
    print('=' * 60)

    threads = []
    for dev in DEVICES:
        t = threading.Thread(
            target=_poll_device,
            args=(dev, interval),
            daemon=True,
            name=dev['device_code'],
        )
        t.start()
        threads.append(t)
        print(f'✓ 已启动 {_device_name(dev)} 采集线程')

    print('-' * 60)
    print('采集器运行中，按 Ctrl+C 停止...')
    print('-' * 60)

    # 等待所有线程
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        pass


def trigger_workload(device_code: str, cpu_workers: int = 2, duration: int = 30):
    """手动触发某个设备的异常负载（用于演示和测试）

    根据 device_code 找到对应容器的 Agent，
    调用 POST /workload/start 启动 stress 负载。

    使用示例：
        from device_collector import trigger_workload
        trigger_workload('DEV-001', cpu_workers=2, duration=30)
    """
    # 查找设备
    dev = next((d for d in DEVICES if d['device_code'] == device_code), None)
    if dev is None:
        print(f'错误: 未找到设备 {device_code}')
        print(f'可用设备: {[d["device_code"] for d in DEVICES]}')
        return

    agent_url = dev['agent_url']
    print(f'正在向 {device_code} 发送负载指令...')
    print(f'  Agent: {agent_url}/workload/start')
    print(f'  CPU线程: {cpu_workers}, 持续: {duration}s')

    try:
        resp = requests.post(
            f'{agent_url}/workload/start',
            json={'cpu_workers': cpu_workers, 'duration_seconds': duration},
            timeout=10,
        )
        result = resp.json()
        print(f'  结果: {result.get("message", result.get("status", "unknown"))}')
    except requests.ConnectionError:
        print(f'  错误: 容器 {agent_url} 不可达，请确认 Docker 容器已启动')
    except Exception as e:
        print(f'  错误: {e}')


def signal_handler(sig, frame):
    """Ctrl+C 信号处理"""
    global _running
    _running = False
    print('\n正在停止采集器...')


signal.signal(signal.SIGINT, signal_handler)


# ═══════════════════════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════════════════════
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='AIoT Edge 真实数据采集器 — 从Docker容器采集psutil数据并转发后端',
    )
    parser.add_argument(
        '--interval', '-i',
        type=float,
        default=5.0,
        help='采集间隔（秒），默认 5',
    )
    parser.add_argument(
        '--backend', '-b',
        type=str,
        default='http://localhost:8000',
        help='后端服务地址，默认 http://localhost:8000',
    )
    args = parser.parse_args()

    if args.interval < 0.1:
        parser.error('--interval 不能小于 0.1 秒')

    BACKEND_URL = args.backend.rstrip('/')
    start_collector(interval=args.interval)
