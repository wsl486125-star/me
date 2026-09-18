#!/usr/bin/env python3
"""
AIoT Edge — 答辩演示：手动触发设备异常负载

用法：
  python trigger_demo.py DEV-001 --cpu 2 --duration 30

效果：
  让 DEV-001 对应的容器真实运行 2 个 stress 线程 30 秒，
  CPU 会真实飙升，几秒后可以在前端仪表盘和告警中心看到
  数据变化和告警生成 —— 这是"真实数据支撑"最直观的演示方式。
"""
import argparse
import sys
import os

# 确保能导入同目录的 device_collector 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from device_collector import trigger_workload, DEVICES

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='AIoT Edge 答辩演示工具 — 手动触发设备异常负载',
        epilog=f'可用设备: {", ".join(d["device_code"] for d in DEVICES)}',
    )
    parser.add_argument(
        'device_code',
        type=str,
        help='目标设备编号，如 DEV-001',
    )
    parser.add_argument(
        '--cpu', '-c',
        type=int,
        default=2,
        help='stress CPU 线程数，默认 2',
    )
    parser.add_argument(
        '--duration', '-d',
        type=int,
        default=30,
        help='负载持续时间（秒），默认 30',
    )

    args = parser.parse_args()
    trigger_workload(args.device_code, cpu_workers=args.cpu, duration=args.duration)
