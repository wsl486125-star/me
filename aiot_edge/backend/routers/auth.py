"""
AIoT Edge — 用户认证路由
注册 / 登录（JWT签发） / 获取当前用户
"""
from __future__ import annotations
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)
from core.config import settings
from core.mail import send_verification_code, verify_code
from schemas import UserCreate, UserLogin, SendCodeRequest, TokenOut
from models import User

router = APIRouter()


def _validate_username(username: str) -> str | None:
    """校验用户名：3-20位字母数字下划线，返回错误信息或None"""
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
        return '用户名需为3-20位字母、数字或下划线'
    return None


def _validate_password(password: str) -> str | None:
    """校验密码：6-30位，含字母和数字，返回错误信息或None"""
    if len(password) < 6 or len(password) > 30:
        return '密码长度需为6-30位'
    if not re.search(r'[a-zA-Z]', password):
        return '密码需包含字母'
    if not re.search(r'\d', password):
        return '密码需包含数字'
    return None


@router.post('/send-code')
def send_code(payload: SendCodeRequest):
    """发送邮箱验证码（注册 / 登录前调用）

    验证码 6 位数字，5 分钟内有效，同一邮箱 60 秒内仅可发送一次。
    """
    email = (payload.email or '').strip()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='请输入邮箱地址',
        )

    result = send_verification_code(email)
    if not result['success']:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=result['message'],
        )
    return {'message': result['message']}


@router.post('/register', status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """用户注册

    校验规则：
      - username：3-20位字母数字下划线，不可重复
      - email：不可重复
      - password：6-30位，必须同时包含字母和数字
      - code：邮箱验证码（发到注册邮箱）
    """
    # 校验用户名格式
    err = _validate_username(payload.username)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    # 校验密码格式
    err = _validate_password(payload.password)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    # 校验邮箱验证码
    if not verify_code(payload.email, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='验证码错误或已过期',
        )

    # 用户名唯一性
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='用户名已存在',
        )

    # 邮箱唯一性
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='邮箱已被注册',
        )

    # 创建用户
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        'message': '注册成功',
        'user': user.to_dict(),
    }


@router.post('/login')
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """用户登录（密码登录 / 验证码登录 二选一）

    - 密码登录：用户名/邮箱 + 密码
    - 验证码登录：邮箱 + 验证码（发到该账号绑定邮箱）
    """
    account = (payload.username or '').strip()

    # 含 @ 视为邮箱，否则按用户名查
    if '@' in account:
        user = db.query(User).filter(User.email == account).first()
    else:
        user = db.query(User).filter(User.username == account).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='账号不存在',
        )

    # ━━━ 方式一：密码登录 ━━━
    if payload.login_type == 'password':
        if not payload.password or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='用户名/邮箱或密码错误',
            )

    # ━━━ 方式二：验证码登录（必须用邮箱） ━━━
    elif payload.login_type == 'code':
        if '@' not in account:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='验证码登录请使用邮箱账号',
            )
        if not verify_code(user.email, payload.code or ''):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='验证码错误或已过期',
            )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='未知的登录方式',
        )

    # 生成 JWT
    access_token = create_access_token(data={'sub': user.username})

    return {
        'access_token': access_token,
        'token_type': 'bearer',
        'expires_in': settings.JWT_EXPIRE_HOURS * 3600,
        'user': user.to_dict(),
    }


@router.get('/me')
def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return current_user.to_dict()
