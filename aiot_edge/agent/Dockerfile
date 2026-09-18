# AIoT Edge — 容器内 Agent 镜像
# 每个容器 = 一台被模拟的真实网络设备节点
FROM python:3.11-slim

# 安装系统 stress 工具（用于模拟CPU高负载）
RUN apt-get update && apt-get install -y stress && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制采集程序
COPY agent.py .

EXPOSE 9100

CMD ["python", "agent.py"]
