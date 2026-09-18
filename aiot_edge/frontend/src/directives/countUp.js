/*
 * v-count-up 数字滚动指令
 * 用法：
 *   <span v-count-up="42" />                          // 整数
 *   <span v-count-up="{ value: 45.2, decimals: 1 }" /> // 指定小数位
 *   <span v-count-up="{ value: 128, duration: 1200 }" />
 * 仅当目标数值真正变化时才重新滚动（按数值比较，不受对象引用影响）。
 */
function format(value, decimals) {
  if (decimals != null) return value.toFixed(decimals)
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(1)
}

function resolveConfig(binding) {
  const v = binding.value
  if (v && typeof v === 'object') {
    return { value: v.value ?? 0, decimals: v.decimals, duration: v.duration ?? 800 }
  }
  return { value: v ?? 0, decimals: undefined, duration: 800 }
}

const prefersReducedMotion = () =>
  typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

function animate(el, target, duration, decimals) {
  const to = parseFloat(target) || 0
  if (prefersReducedMotion()) {
    el.textContent = format(to, decimals)
    el.__countCurrent = to
    return
  }

  const start = performance.now()
  const from = el.__countCurrent ?? 0

  const step = (now) => {
    const progress = Math.min((now - start) / duration, 1)
    const eased = 1 - Math.pow(1 - progress, 3) // ease-out cubic
    const current = from + (to - from) * eased
    el.textContent = format(current, decimals)
    if (progress < 1) {
      requestAnimationFrame(step)
    } else {
      el.__countCurrent = to
      el.textContent = format(to, decimals)
    }
  }
  requestAnimationFrame(step)
}

export default {
  mounted(el, binding) {
    const { value, decimals, duration } = resolveConfig(binding)
    el.__countTarget = parseFloat(value) || 0
    el.__countCurrent = 0
    animate(el, el.__countTarget, duration, decimals)
  },
  updated(el, binding) {
    const { value, decimals, duration } = resolveConfig(binding)
    const target = parseFloat(value) || 0
    if (target !== el.__countTarget) {
      el.__countTarget = target
      animate(el, target, duration, decimals)
    }
  },
}
