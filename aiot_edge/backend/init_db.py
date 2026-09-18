"""
数据库初始化脚本
导入所有模型并执行建表操作
"""
from core.database import engine, Base

# 导入所有模型，确保它们注册到 Base.metadata
from models import User, Device, DeviceGroup, DeviceMetric, Alert, EdgeNode, SecurityEvent  # noqa: F401


def init_db():
    print('正在创建数据库表...')
    Base.metadata.create_all(bind=engine)
    print('数据库表已创建/确认：')
    for table_name in Base.metadata.tables:
        print(f'  [OK] {table_name}')


if __name__ == '__main__':
    init_db()
