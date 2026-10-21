import { defineStore } from 'pinia'

let nextId = 1

export const useToastStore = defineStore('toast', {
  state: () => ({ items: [] }),
  actions: {
    show(message, variant = 'success', timeout = 4000) {
      const id = nextId++
      this.items.push({ id, message, variant })
      if (timeout) setTimeout(() => this.dismiss(id), timeout)
    },
    success(message) {
      this.show(message, 'success')
    },
    error(message) {
      this.show(message, 'danger', 6000)
    },
    dismiss(id) {
      this.items = this.items.filter((t) => t.id !== id)
    },
  },
})
