"""
AIoT Edge — 数据库连接管理
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from core.config import settings

# SQLite 需要额外参数；MySQL 需要 pool 参数
if settings.DATABASE_TYPE == 'sqlite':
    # ━━ 连接池说明 ━━
    # 本系统用 SQLite 承载「多设备高频上报」：采集器 10 个线程每 5s 各发一次
    # /api/ingest/metric，加上离线检测后台任务与前端轮询，会出现 15~25 个并发
    # 连接需求。QueuePool 默认 pool_size=5 + max_overflow=10（共 15）在这种
    # 并发下会被打满，抛 `QueuePool limit ... connection timed out`，进而导致
    # 后端整体阻塞（表现为 /api/devices 返回空、/api/health 超时）。
    # 故显式放大连接池，并把 pool_timeout 压到 10s（小于采集器 5s×重试窗口之外的
    # 服务端等待），保证拿不到连接时快速失败而不是无限堆积。
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={
            'check_same_thread': False,  # 允许跨线程复用连接（FastAPI 线程池）
            'timeout': 15,               # pysqlite 层写锁等待（秒）
        },
        pool_size=20,
        max_overflow=40,
        pool_timeout=10,
        pool_recycle=1800,
        pool_pre_ping=True,
    )

    # 启用 SQLite 外键约束 + WAL 并发模式
    @event.listens_for(engine, 'connect')
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        # WAL：读写可并发，多线程写入不再相互阻塞（显著缓解 database is locked）
        cursor.execute('PRAGMA journal_mode=WAL')
        # 写锁等待 15s，避免瞬时并发写直接报 database is locked
        cursor.execute('PRAGMA busy_timeout=15000')
        # WAL 下 synchronous=NORMAL 兼顾安全与吞吐
        cursor.execute('PRAGMA synchronous=NORMAL')
        cursor.close()
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
