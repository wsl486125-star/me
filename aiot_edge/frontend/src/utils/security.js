/*
 * 校园安防 —— 告警级别 / 事件类型 / 处置状态 的展示映射（跨视图复用）
 * 与 utils/alerts.js 保持同一组织方式，四级分级语义全局统一：
 *   1 紧急(红) / 2 严重(橙) / 3 一般(黄) / 4 提示(蓝)
 */

// ━━━ 告警级别 ━━━
const LEVEL = {
  1: { label: '紧急', short: '一级', color: 'var(--danger)',  bg: 'rgba(239, 68, 68, 0.14)' },
  2: { label: '严重', short: '二级', color: 'var(--orange)',  bg: 'rgba(249, 115, 22, 0.14)' },
  3: { label: '一般', short: '三级', color: 'var(--warning)', bg: 'rgba(234, 179, 8, 0.14)' },
  4: { label: '提示', short: '四级', color: 'var(--primary)', bg: 'rgba(56, 189, 248, 0.14)' },
}

// ━━━ 事件类型 ━━━
const EVENT_TYPE = {
  loitering: '徘徊逗留',
  gathering: '人员聚集',
  fall_detected: '跌倒检测',
  face_denied: '人脸认证失败',
  face_blacklist: '黑名单布控',
  door_forced: '强行闯入',
  line_crossing: '周界越线',
  perimeter_intrusion: '周界入侵确认',
  smoke_detected: '烟雾检测',
  fire_confirmed: '火情确认',
  gas_leak: '气体泄漏',
  temp_abnormal: '温度异常',
  crowd_warning: '人流拥挤预警',
  crowd_danger: '人流密度危险',
  device_offline: '设备离线',
}

// ━━━ 处置状态（状态机） ━━━
const EVENT_STATUS = {
  pending:     { label: '待确认', color: 'var(--warning)', type: 'warning' },
  confirmed:   { label: '已确认', color: 'var(--orange)',  type: 'warning' },
  processing:  { label: '处置中', color: 'var(--primary)', type: 'primary' },
  closed:      { label: '已闭环', color: 'var(--success)', type: 'success' },
  false_alarm: { label: '误报',   color: 'var(--text-3)',  type: 'info' },
}

// ━━━ 证据源（多源融合展示） ━━━
const SOURCE_LABEL = {
  video: '视频',
  vibration: '振动光纤',
  smoke_sensor: '烟感',
  gas_sensor: '气体',
  face: '人脸',
  infrared: '红外',
  temperature: '温度',
}

// ━━━ 本地联动动作 ━━━
const ACTION_LABEL = {
  sound_light_on: '声光警示',
  door_deny: '门禁拒绝',
  door_lock: '门禁锁定',
  broadcast_evacuate: '疏散广播',
  ventilation_on: '排风联动',
  flow_rate_limit: '限流提示',
  video_snapshot: '抓拍存证',
  alarm_to_guard: '通知安保',
  fire_notify: '消防联动',
}

// ━━━ 推送通道 ━━━
const CHANNEL_LABEL = {
  websocket: '大屏弹窗',
  email: '邮件',
  sms_webhook: '短信网关',
  web_message: '站内消息',
  screen_top: '大屏置顶',
  log: '仅记录',
}

export function levelInfo(level) {
  return LEVEL[level] || LEVEL[3]
}

export function levelLabel(level) {
  const info = levelInfo(level)
  return `${info.short}·${info.label}`
}

export function levelColor(level) {
  return levelInfo(level).color
}

export function eventTypeLabel(type) {
  return EVENT_TYPE[type] || type
}

export function eventStatusInfo(status) {
  return EVENT_STATUS[status] || { label: status, color: 'var(--text-3)', type: 'info' }
}

export function sourceLabel(src) {
  return SOURCE_LABEL[src] || src
}

export function actionLabel(action) {
  return ACTION_LABEL[action] || action
}

export function channelLabel(ch) {
  return CHANNEL_LABEL[ch] || ch
}

/** 该事件当前可流转到的目标状态（与后端 EVENT_STATUS_FLOW 一致） */
export function allowedTransitions(status) {
  const flow = {
    pending: ['confirmed', 'false_alarm'],
    confirmed: ['processing', 'closed', 'false_alarm'],
    processing: ['closed', 'false_alarm'],
    closed: [],
    false_alarm: [],
  }
  return flow[status] || []
}

export { LEVEL, EVENT_TYPE, EVENT_STATUS, SOURCE_LABEL, ACTION_LABEL, CHANNEL_LABEL }
