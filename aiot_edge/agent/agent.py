"""
AIoT Edge — Docker容器内轻量级数据采集Agent
每个容器运行此程序，代表一台被模拟的真实网络设备节点。

使用 psutil 采集容器真实的 CPU / 内存 / 网络数据，
提供 stress 负载控制接口供演示和测试使用。
"""
import os
import time
import signal
import socket
import subprocess
import threading
from datetime import datetime

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
import psutil

# ═══════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════
# 延迟目标默认用阿里公共 DNS 的 443 端口：国内网络对 TCP:53（DNS over TCP）普遍封锁，
# 而 8.8.8.8（Google DNS）在国内不可达，会导致 TCP 连接超时、延迟恒为 999ms 兜底值。
# 223.5.5.5:443 国内可达且稳定（约 15~25ms），用它作为连通性测试目标更真实。
LATENCY_TARGET = os.getenv('LATENCY_TARGET', '223.5.5.5')
LATENCY_PORT = int(os.getenv('LATENCY_PORT', '443'))

# ═══════════════════════════════════════════════════════════
# 带宽计算：记录上一次 net_io_counters 快照
# ═══════════════════════════════════════════════════════════
_last_net_io = None
_last_net_time = None

_net_lock = threading.Lock()


def _measure_network_latency() -> float:
    """通过 socket 连接耗时测量网络延迟（毫秒）

    对固定目标地址做一次 TCP 连接，测量耗时。
    在容器 CPU 负载高时，进程调度竞争会导致耗时自然增加，
    比纯随机数更有说服力。
    """
    try:
        start = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        sock.connect((LATENCY_TARGET, LATENCY_PORT))
        sock.close()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return round(elapsed_ms, 2)
    except (socket.timeout, OSError):
        # 超时或不可达时返回一个大值，表示网络状况差
        return 999.0


def _measure_bandwidth_mbps() -> float:
    """通过两次采样间 net_io_counters 字节差计算带宽（Mbps）

    每次调用计算与上一次采样之间的平均吞吐量。
    首次调用返回 0.0（无历史数据）。
    """
    global _last_net_io, _last_net_time

    with _net_lock:
        current_io = psutil.net_io_counters()
        current_time = time.perf_counter()

        if _last_net_io is None or _last_net_time is None:
            _last_net_io = current_io
            _last_net_time = current_time
            return 0.0

        # 两次采样间的收发总字节差
        bytes_delta = (
            (current_io.bytes_sent - _last_net_io.bytes_sent)
            + (current_io.bytes_recv - _last_net_io.bytes_recv)
        )
        time_delta = current_time - _last_net_time

        _last_net_io = current_io
        _last_net_time = current_time

        if time_delta <= 0:
            return 0.0

        # 转换为 Mbps：bytes → bits → / 1_000_000 → per second
        mbps = (bytes_delta * 8) / (time_delta * 1_000_000)
        return round(mbps, 4)


# ═══════════════════════════════════════════════════════════
# 容器级 CPU / 内存测量（cgroup v2）
# ═══════════════════════════════════════════════════════════
# psutil.cpu_percent() / virtual_memory() 在容器里读到的是宿主(VM)的
# /proc/stat 与 /proc/meminfo，而不是本容器的 cgroup 配额，会跟
# `docker stats` 严重对不上。这里直接读 cgroup v2 统计文件，
# 得到“本容器相对自身限额”的真实占用，与 docker stats 口径一致。
_CGROUP_DIR = '/sys/fs/cgroup'

_last_cpu_usage_usec = None
_last_cpu_time = None
_cpu_ncpus_cache = None


def _cgroup_ncpus() -> float:
    """本容器的 CPU 配额（单位：核）。

    cpus: 1.0 -> cpu.max = '100000 100000' -> 1 核；
    未限制时 cpu.max = 'max ...' -> 退化为 psutil 核数。
    """
    global _cpu_ncpus_cache
    if _cpu_ncpus_cache is not None:
        return _cpu_ncpus_cache
    try:
        with open(os.path.join(_CGROUP_DIR, 'cpu.max')) as f:
            parts = f.read().split()
        quota = int(parts[0]) if parts and parts[0] != 'max' else 0
        period = int(parts[1]) if len(parts) > 1 and parts[1] != 'max' else 100000
        _cpu_ncpus_cache = (quota / period) if (quota > 0 and period > 0) else float(psutil.cpu_count() or 1)
    except (OSError, ValueError):
        _cpu_ncpus_cache = float(psutil.cpu_count() or 1)
    return _cpu_ncpus_cache


def _measure_cpu_percent() -> float:
    """容器级 CPU 使用率（%），对 cpu.stat 的 usage_usec 做两次采样求差值。

    与 psutil.cpu_percent(interval=0.3) 不同，这里不阻塞，返回自上一次采样
    以来的平均占用。采集器每 5s 拉取一次，因此得到的是 5s 窗口的平均 CPU，
    跑 stress 时能真实飙到接近 100%（相对 1 核限额）。
    """
    global _last_cpu_usage_usec, _last_cpu_time
    try:
        with open(os.path.join(_CGROUP_DIR, 'cpu.stat')) as f:
            usage = None
            for line in f:
                if line.startswith('usage_usec'):
                    usage = int(line.split()[1])
                    break
        if usage is None:
            return 0.0

        now = time.perf_counter()
        if _last_cpu_usage_usec is None or _last_cpu_time is None:
            _last_cpu_usage_usec = usage
            _last_cpu_time = now
            return 0.0

        delta_us = usage - _last_cpu_usage_usec
        delta_s = now - _last_cpu_time
        _last_cpu_usage_usec = usage
        _last_cpu_time = now
        if delta_s <= 0:
            return 0.0

        ncpus = _cgroup_ncpus()
        pct = (delta_us / (delta_s * 1_000_000)) / ncpus * 100.0
        return round(max(0.0, min(pct, 100.0 * ncpus)), 2)
    except (OSError, ValueError):
        return 0.0


def _measure_memory_percent() -> float:
    """容器级内存使用率（%）：memory.current / memory.max。

    与 `docker stats` 的 MEM% 同一口径（相对 compose 里 mem_limit: 256m）。
    """
    try:
        with open(os.path.join(_CGROUP_DIR, 'memory.current')) as f:
            current = int(f.read().strip())
        with open(os.path.join(_CGROUP_DIR, 'memory.max')) as f:
            raw = f.read().strip()
        if raw == 'max':  # 未设内存上限
            return 0.0
        limit = int(raw)
        if limit <= 0:
            return 0.0
        return round(current / limit * 100.0, 2)
    except (OSError, ValueError):
        return 0.0


# ═══════════════════════════════════════════════════════════
# 负载控制
# ═══════════════════════════════════════════════════════════
_stress_process: subprocess.Popen | None = None
_stress_end_time: float = 0.0
_stress_lock = threading.Lock()


def _stop_stress():
    """终止当前运行的 stress 进程"""
    global _stress_process, _stress_end_time
    with _stress_lock:
        if _stress_process is not None:
            try:
                os.killpg(os.getpgid(_stress_process.pid), signal.SIGTERM)
            except Exception:
                try:
                    _stress_process.kill()
                except Exception:
                    pass
            try:
                _stress_process.wait(timeout=3)
            except Exception:
                try:
                    _stress_process.kill()
                except Exception:
                    pass
            _stress_process = None
        _stress_end_time = 0.0


def _start_stress(cpu_workers: int, duration_seconds: int):
    """在子进程中启动 stress 工具消耗 CPU"""
    global _stress_process, _stress_end_time

    # 先停掉旧的
    _stop_stress()

    with _stress_lock:
        try:
            _stress_process = subprocess.Popen(
                ['stress', '--cpu', str(cpu_workers),
                 '--timeout', f'{duration_seconds}s'],
                preexec_fn=os.setsid,   # 创建新进程组，方便后续 killpg
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _stress_end_time = time.time() + duration_seconds
        except FileNotFoundError:
            _stress_process = None
            _stress_end_time = 0.0
            raise RuntimeError(
                'stress 工具未安装，请在 Dockerfile 中 apt-get install -y stress'
            )


# ═══════════════════════════════════════════════════════════
# Pydantic 模型
# ═══════════════════════════════════════════════════════════
class WorkloadRequest(BaseModel):
    cpu_workers: int = Field(1, ge=1, le=8, description='stress CPU 线程数')
    duration_seconds: int = Field(20, ge=1, le=300, description='负载持续时间(秒)')


# ═══════════════════════════════════════════════════════════
# FastAPI 应用
# ═══════════════════════════════════════════════════════════
app = FastAPI(title='AIoT Agent — 容器数据采集', version='1.0.0')


@app.get('/metrics')
def get_metrics():
    """返回本容器真实的资源使用情况

    - cpu_usage：容器 cgroup 真实 CPU 使用率
    - memory_usage：容器 cgroup 真实内存使用率
    - disk_usage：psutil 真实磁盘使用率（宿主盘）
    - network_latency：socket 连接耗时（真实测量，非随机数）
    - bandwidth_usage：两次采样间网络吞吐量差值（Mbps）
    - workload_active：当前是否有 stress 负载在运行
    - workload_remaining_seconds：剩余负载时间
    """
    # CPU / 内存：读本容器 cgroup v2 统计，与 `docker stats` 口径一致
    cpu_usage = _measure_cpu_percent()

    # 内存
    memory_usage = _measure_memory_percent()

    # 磁盘
    disk_usage = round(psutil.disk_usage('/').percent, 2)

    # 网络延迟（真实 socket 连接耗时）
    network_latency = _measure_network_latency()

    # 带宽（两次采样间差值）
    bandwidth_usage = _measure_bandwidth_mbps()

    # 负载状态
    with _stress_lock:
        workload_active = _stress_process is not None and _stress_process.poll() is None
        remaining = max(0.0, _stress_end_time - time.time()) if workload_active else 0.0

    return {
        'cpu_usage': cpu_usage,
        'memory_usage': memory_usage,
        'disk_usage': disk_usage,
        'network_latency': network_latency,
        'bandwidth_usage': bandwidth_usage,
        'workload_active': workload_active,
        'workload_remaining_seconds': int(remaining),
        'timestamp': datetime.now().isoformat(),
    }


@app.post('/workload/start')
def workload_start(req: WorkloadRequest):
    """启动一段真实消耗 CPU 的负载

    调用系统 stress 工具，让容器 CPU 真实飙升一段时间，
    模拟"设备正在高负载运行"。多次调用前自动停掉上一个 stress 进程。
    """
    try:
        _start_stress(req.cpu_workers, req.duration_seconds)
        return {
            'status': 'started',
            'cpu_workers': req.cpu_workers,
            'duration_seconds': req.duration_seconds,
            'message': f'stress --cpu {req.cpu_workers} --timeout {req.duration_seconds}s',
        }
    except RuntimeError as e:
        return {'status': 'error', 'message': str(e)}


@app.post('/workload/stop')
def workload_stop():
    """提前停止当前负载（杀掉 stress 进程）"""
    _stop_stress()
    return {'status': 'stopped', 'message': 'stress 进程已终止'}


@app.get('/health')
def health():
    """健康检查"""
    return {'status': 'ok'}


# ═══════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=9100)
