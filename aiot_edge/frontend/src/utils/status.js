/*
 * 设备状态统一映射 —— 保证「正常绿 / 警告黄 / 离线红」全局一致。
 */
export function deviceStatus(status) {
  const map = {
    online: { cls: 'online', text: '在线', color: 'var(--success)' },
    warning: { cls: 'warning', text: '警告', color: 'var(--warning)' },
    offline: { cls: 'offline', text: '离线', color: 'var(--danger)' },
  }
  return map[status] || map.offline
}
