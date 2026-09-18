"""
AIoT Edge — AI 助手路由
基于 DeepSeek 的智能运维助手（SSE 流式）
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import get_current_user
from schemas import AiChatRequest
from services.ai_service import stream_chat

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post('/chat')
def chat(payload: AiChatRequest, db: Session = Depends(get_db)):
    """AI 助手对话（SSE 流式返回）

    前端通过 fetch + ReadableStream 读取 text/event-stream 响应。
    每个事件为 `data: {"content": "..."}\\n\\n`，结束为 `data: [DONE]\\n\\n`。
    """
    messages = [m.model_dump() for m in payload.messages]
    return StreamingResponse(
        stream_chat(messages, db),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )
