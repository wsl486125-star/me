"""
AIoT Edge — 邮件发送 + 邮箱验证码

- 发送：标准库 smtplib + email，无需第三方依赖
- 验证码：6 位数字，存内存字典（带过期时间），一次性消费
"""
import random
import smtplib
import time
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from core.config import settings


# ━━━ 验证码存储：{email: {'code': str, 'expire': float}} ━━━
_STORE: dict = {}

# 验证码有效期（秒）
TTL = 300

# 同一邮箱发送间隔（秒），防刷
RESEND_INTERVAL = 60


def _cleanup():
    now = time.time()
    for k in [k for k, v in _STORE.items() if v['expire'] < now]:
        _STORE.pop(k, None)


def send_verification_code(email: str) -> dict:
    """生成并向指定邮箱发送 6 位数字验证码，返回结果 dict。

    返回：{'success': bool, 'message': str}
    """
    _cleanup()

    # 防刷：同一邮箱 60 秒内只允许发一次
    existing = _STORE.get(email)
    if existing and existing['expire'] - TTL + RESEND_INTERVAL > time.time():
        wait = int(RESEND_INTERVAL - (time.time() - (existing['expire'] - TTL)))
        return {'success': False, 'message': f'发送过于频繁，请 {max(1, wait)} 秒后重试'}

    code = f'{random.randint(0, 999999):06d}'

    try:
        _send_mail(email, code)
    except Exception as e:
        print(f'[邮件] 发送验证码到 {email} 失败: {e}')
        return {'success': False, 'message': '邮件发送失败，请稍后重试'}

    _STORE[email] = {'code': code, 'expire': time.time() + TTL}
    return {'success': True, 'message': '验证码已发送，请查收邮箱'}


def verify_code(email: str, code: str) -> bool:
    """校验邮箱验证码，成功即消费（删除），失败返回 False。"""
    _cleanup()

    if not email or not code:
        return False

    item = _STORE.pop(email, None)
    if item is None:
        return False

    return item['code'] == code.strip()


def _send_mail(to_email: str, code: str):
    """通过 QQ 邮箱 SMTP（SSL）发送验证码邮件"""
    subject = f'【{settings.SMTP_FROM_NAME}】邮箱验证码'
    body = (
        f'您好：\n\n'
        f'您本次操作的邮箱验证码为：\n\n'
        f'    {code}\n\n'
        f'验证码 {TTL // 60} 分钟内有效，请勿泄露给他人。'
        f'如非本人操作，请忽略本邮件。\n'
    )

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = formataddr((str(Header(settings.SMTP_FROM_NAME, 'utf-8')), settings.SMTP_USER))
    msg['To'] = to_email

    server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
    try:
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_USER, [to_email], msg.as_string())
    finally:
        server.quit()
