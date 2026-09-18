// 告警类型 / 严重程度 的展示映射（跨视图复用）

const ALERT_TYPE = {
  cpu_high: 'CPU过高',
  latency_high: '网络延迟过高',
  memory_high: '内存过高',
  cpu_spike: 'CPU突增异常',
  ml_anomaly: 'ML模型异常',
  offline: '设备离线',
}

const SEVERITY = {
  critical: { label: '严重', color: 'var(--danger)' },
  high: { label: '高', color: 'var(--orange)' },
  medium: { label: '中', color: 'var(--warning)' },
  low: { label: '低', color: 'var(--text-3)' },
}

// 告警处置状态（闭环状态机）
const ALERT_STATUS = {
  firing: { label: '待处理', color: 'var(--danger)' },
  confirmed: { label: '已确认', color: 'var(--warning)' },
  processing: { label: '处理中', color: 'var(--primary)' },
  resolved: { label: '已解决', color: 'var(--success)' },
  closed: { label: '已关闭', color: 'var(--success)' },
  false_alarm: { label: '误报', color: 'var(--text-3)' },
}

export function alertTypeLabel(type) {
  return ALERT_TYPE[type] || type
}

export function severityLabel(sev) {
  return SEVERITY[sev]?.label || sev
}

export function severityColor(sev) {
  return SEVERITY[sev]?.color || 'var(--text-3)'
}

export function alertStatusLabel(status) {
  return ALERT_STATUS[status]?.label || status
}

export function alertStatusColor(status) {
  return ALERT_STATUS[status]?.color || 'var(--text-3)'
}

export { SEVERITY, ALERT_STATUS }
