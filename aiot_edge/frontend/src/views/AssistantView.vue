<template>
  <div class="assistant">
    <el-card class="chat-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">
            <el-icon><ChatDotRound /></el-icon>
            AI 智能助手
          </span>
          <span class="card-subtitle">基于 DeepSeek · 实时感知系统状态</span>
        </div>
      </template>

      <!-- 消息列表 -->
      <div ref="listRef" class="chat-list">
        <!-- 空状态 + 推荐提问 -->
        <div v-if="!messages.length" class="chat-empty">
          <el-icon class="empty-icon"><MagicStick /></el-icon>
          <p class="empty-title">你好，我是 AIoT Edge 的运维助手</p>
          <p class="empty-tip">我可以读取当前设备状态与告警，试试下面的问题：</p>
          <div class="suggestions">
            <el-button
              v-for="q in suggestions"
              :key="q"
              size="small"
              round
              plain
              @click="ask(q)"
            >{{ q }}</el-button>
          </div>
        </div>

        <!-- 消息气泡 -->
        <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
          <div class="avatar">
            <el-icon :size="16">
              <component :is="m.role === 'user' ? 'User' : 'ChatDotRound'" />
            </el-icon>
          </div>
          <div class="bubble">
            <div class="msg-content">{{ m.content }}</div>
            <span
              v-if="m.role === 'assistant' && loading && i === messages.length - 1 && !m.content"
              class="typing"
            >
              <span class="dot"></span><span class="dot"></span><span class="dot"></span>
            </span>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="chat-input">
        <el-input
          v-model="input"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          placeholder="问我系统状态，例如：现在有几台设备在线？"
          @keydown.enter.exact.prevent="send"
        />
        <el-button type="primary" :loading="loading" @click="send">发送</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const AI_CHAT_URL = 'http://localhost:8000/api/ai/chat'

const messages = ref([])
const input = ref('')
const loading = ref(false)
const listRef = ref(null)

const suggestions = [
  '现在有几台设备在线？',
  '最近有哪些告警？',
  '哪台设备负载最高？',
  '系统整体运行情况怎么样？',
]

function ask(q) {
  input.value = q
  send()
}

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return
  input.value = ''

  // 1. 追加用户消息，并快照完整历史（不含待生成的助手回复）
  messages.value.push({ role: 'user', content: text })
  const history = messages.value.map((m) => ({ role: m.role, content: m.content }))

  // 2. 追加空的助手回复，供流式填充
  const assistantMsg = { role: 'assistant', content: '' }
  messages.value.push(assistantMsg)
  loading.value = true
  scrollToBottom()

  try {
    await streamReply(history, assistantMsg)
  } catch (e) {
    assistantMsg.content = '⚠️ 请求失败：' + (e?.message || e)
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

async function streamReply(history, assistantMsg) {
  const token = localStorage.getItem('token')
  const resp = await fetch(AI_CHAT_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ messages: history }),
  })

  if (!resp.ok) {
    const errText = await resp.text().catch(() => '')
    throw new Error(`HTTP ${resp.status} ${errText}`)
  }
  if (!resp.body) throw new Error('当前浏览器不支持流式响应')

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // 按 \n\n 切分完整 SSE 事件
    let idx
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      handleEvent(rawEvent, assistantMsg)
      scrollToBottom()
    }
  }
  if (buffer.trim()) handleEvent(buffer, assistantMsg)
}

function handleEvent(rawEvent, assistantMsg) {
  for (const line of rawEvent.split('\n')) {
    if (!line.startsWith('data:')) continue
    const data = line.slice(5).trim()
    if (data === '[DONE]') continue
    try {
      const obj = JSON.parse(data)
      if (obj.error) {
        assistantMsg.content = '⚠️ ' + obj.error
      } else if (obj.content) {
        assistantMsg.content += obj.content
      }
    } catch {
      // 忽略无法解析的分片
    }
  }
}

function clearChat() {
  messages.value = []
}

function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}
</script>

<style scoped>
.assistant {
  height: calc(100vh - 64px - var(--sp-24) * 2);
  display: flex;
}

.chat-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-card);
  overflow: hidden;
}

.chat-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: baseline;
  gap: var(--sp-16);
}

.card-title {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-8);
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1);
}

.card-subtitle {
  font-size: 12px;
  color: var(--text-3);
}

/* ━━━ 消息列表 ━━━ */
.chat-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-24);
  display: flex;
  flex-direction: column;
  gap: var(--sp-16);
}

/* 空状态 */
.chat-empty {
  margin: auto;
  text-align: center;
  max-width: 480px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-16);
}

.empty-icon {
  font-size: 48px;
  color: var(--primary);
}

.empty-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-1);
  margin: 0;
}

.empty-tip {
  font-size: 13px;
  color: var(--text-2);
  margin: 0;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-8);
  justify-content: center;
  margin-top: var(--sp-8);
}

/* 消息气泡 */
.msg {
  display: flex;
  gap: var(--sp-16);
  align-items: flex-start;
}

.msg.user {
  flex-direction: row-reverse;
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(56, 189, 248, 0.14);
  color: var(--primary);
}

.msg.user .avatar {
  background: rgba(34, 197, 94, 0.14);
  color: var(--success);
}

.bubble {
  max-width: 72%;
  padding: var(--sp-16);
  border-radius: var(--radius-dialog);
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-1);
  font-size: 14px;
  line-height: 1.6;
}

.msg.user .bubble {
  background: rgba(56, 189, 248, 0.12);
  border-color: rgba(56, 189, 248, 0.25);
}

.msg-content {
  white-space: pre-wrap;
  word-break: break-word;
}

/* 输入中动画 */
.typing {
  display: inline-flex;
  gap: 4px;
  margin-top: var(--sp-8);
}

.typing .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-3);
  animation: blink 1.2s infinite ease-in-out;
}

.typing .dot:nth-child(2) { animation-delay: 0.2s; }
.typing .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes blink {
  0%, 80%, 100% { opacity: 0.2; }
  40% { opacity: 1; }
}

/* ━━━ 输入区 ━━━ */
.chat-input {
  display: flex;
  gap: var(--sp-16);
  padding: var(--sp-16) var(--sp-24);
  border-top: 1px solid var(--border);
  background: var(--bg-card);
}

.chat-input .el-button {
  align-self: flex-end;
  height: 40px;
}
</style>
