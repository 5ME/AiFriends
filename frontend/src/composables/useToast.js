import { reactive, readonly } from 'vue'

const state = reactive({
  toasts: []
})

let _id = 0

export function useToast() {
  function add(type, message, duration = 3000) {
    if (!message) return
    const id = ++_id
    state.toasts.push({ id, type, message })
    if (type !== 'error' && duration > 0) {
      setTimeout(() => remove(id), duration)
    }
    if (state.toasts.length > 5) {
      state.toasts.shift()
    }
  }

  function remove(id) {
    const idx = state.toasts.findIndex(t => t.id === id)
    if (idx !== -1) state.toasts.splice(idx, 1)
  }

  return {
    toasts: readonly(state.toasts),
    success: (msg) => add('success', msg),
    error:   (msg) => add('error', msg, 0),
    warning: (msg) => add('warning', msg),
    info:    (msg) => add('info', msg),
    remove,
  }
}
