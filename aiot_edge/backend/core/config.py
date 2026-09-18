"""
AIoT Edge — 全局配置
基于 pydantic-settings 读取 .env 环境变量
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ━━━ 数据库配置（默认使用 SQLite，无需外部 MySQL 服务）━━━
    DATABASE_TYPE: str = 'sqlite'         # sqlite 或 mysql
    # MySQL 配置（仅 DATABASE_TYPE=mysql 时使用）
    MYSQL_HOST: str = 'localhost'
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = 'root'
    MYSQL_PASSWORD: str = 'your_password'
    MYSQL_DATABASE: str = 'aiot_edge'

    # ━━━ JWT 认证配置 ━━━
    JWT_SECRET_KEY: str = 'change_this_to_random_32chars'
    JWT_ALGORITHM: str = 'HS256'
    JWT_EXPIRE_HOURS: int = 24

    # ━━━ 应用服务配置 ━━━
    APP_HOST: str = '0.0.0.0'
    APP_PORT: int = 8000

    # ━━━ 边缘计算规则默认阈值常量 ━━━
    CPU_THRESHOLD: float = 85.0           # CPU使用率超过此值触发告警(%)
    LATENCY_THRESHOLD: float = 200.0      # 网络延迟超过此值触发告警(ms)
    OFFLINE_TIMEOUT_SECONDS: int = 30     # 超过此时长无上报视为离线

    # ━━━ DeepSeek AI 助手配置 ━━━
    DEEPSEEK_API_KEY: str = ''                        # DeepSeek API Key（必填）
    DEEPSEEK_BASE_URL: str = 'https://api.deepseek.com'  # OpenAI 兼容接口地址
    DEEPSEEK_MODEL: str = 'deepseek-chat'             # 模型：deepseek-chat / deepseek-reasoner

    # ━━━ 邮件 SMTP 配置（邮箱验证码） ━━━
    SMTP_HOST: str = 'smtp.qq.com'                    # SMTP 服务器
    SMTP_PORT: int = 465                              # 465=SSL / 587=STARTTLS
    SMTP_USER: str = ''                               # 发信邮箱
    SMTP_PASSWORD: str = ''                           # SMTP 授权码
    SMTP_FROM_NAME: str = '高校安防AIoT边缘协同预警系统'  # 发件人显示名

    @property
    def DATABASE_URL(self) -> str:
        """根据 DATABASE_TYPE 返回对应的数据库连接串"""
        if self.DATABASE_TYPE == 'mysql':
            return (
                f'mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}'
                f'@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}'
                f'?charset=utf8mb4'
            )
        else:
            # SQLite — 数据库文件存放在 backend/ 目录下
            import os
            db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(db_dir, 'aiot_edge.db')
            return f'sqlite:///{db_path}'

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'


settings = Settings()
