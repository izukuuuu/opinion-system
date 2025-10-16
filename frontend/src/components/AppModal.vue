<template>
  <transition
    enter-active-class="transition ease-out duration-200"
    enter-from-class="opacity-0"
    enter-to-class="opacity-100"
    leave-active-class="transition ease-in duration-150"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
  >
    <div v-if="modelValue" class="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 px-4 py-6 backdrop-blur" @click.self="handleBackdrop">
      <div class="w-full rounded-3xl bg-surface p-6 shadow-2xl" :class="width">
        <header class="flex items-start justify-between gap-4 border-b border-soft pb-4">
          <div class="space-y-1.5">
            <p v-if="eyebrow" class="text-xs font-semibold uppercase tracking-[0.35em] text-muted">
              {{ eyebrow }}
            </p>
            <h2 class="text-2xl font-semibold text-primary">
              {{ title }}
            </h2>
          </div>
          <button
            v-if="showClose"
            type="button"
            class="flex h-10 w-10 items-center justify-center rounded-full border border-soft text-secondary transition hover:border-brand-soft hover:bg-accent-faint hover:text-primary focus-ring-accent"
            @click="handleCancel"
            aria-label="关闭"
          >
            ✕
          </button>
        </header>

        <section class="mt-4 space-y-4 text-sm text-secondary">
          <slot name="description">
            <p v-if="description">{{ description }}</p>
          </slot>
          <slot />
        </section>

        <footer class="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end sm:gap-4">
          <button
            type="button"
            class="inline-flex items-center justify-center rounded-full border border-soft px-5 py-2 text-sm font-medium text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-ring-accent disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="confirmLoading"
            @click="handleCancel"
          >
            {{ cancelText }}
          </button>
          <button
            type="button"
            class="inline-flex items-center justify-center rounded-full px-5 py-2 text-sm font-semibold text-white shadow transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            :class="[confirmButtonClass, confirmLoading ? 'cursor-wait opacity-90' : '']"
            :disabled="confirmDisabled || confirmLoading"
            @click="handleConfirm"
          >
            <span v-if="confirmLoading">{{ confirmLoadingText }}</span>
            <span v-else>{{ confirmText }}</span>
          </button>
        </footer>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    required: true
  },
  description: {
    type: String,
    default: ''
  },
  eyebrow: {
    type: String,
    default: ''
  },
  cancelText: {
    type: String,
    default: '取消'
  },
  confirmText: {
    type: String,
    default: '确认'
  },
  confirmLoadingText: {
    type: String,
    default: '处理中…'
  },
  confirmLoading: {
    type: Boolean,
    default: false
  },
  confirmDisabled: {
    type: Boolean,
    default: false
  },
  confirmTone: {
    type: String,
    default: 'primary'
  },
  width: {
    type: String,
    default: 'max-w-lg'
  },
  showClose: {
    type: Boolean,
    default: true
  },
  closeOnBackdrop: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['update:modelValue', 'cancel', 'confirm'])

const confirmButtonClass = computed(() => {
  if (props.confirmTone === 'danger') {
    return 'bg-danger-600 hover:bg-danger-500 focus-visible:outline-danger-600 disabled:cursor-not-allowed disabled:bg-danger-300'
  }
  if (props.confirmTone === 'success') {
    return 'bg-success-600 hover:bg-success-500 focus-visible:outline-success-600 disabled:cursor-not-allowed disabled:bg-success-300'
  }
  return 'bg-brand-600 hover:bg-brand-500 focus-visible:outline-brand-600 disabled:cursor-not-allowed disabled:bg-brand-300'
})

const handleCancel = () => {
  emit('cancel')
  emit('update:modelValue', false)
}

const handleConfirm = () => {
  emit('confirm')
}

const handleBackdrop = () => {
  if (!props.closeOnBackdrop) return
  handleCancel()
}

const handleKeydown = (event) => {
  if (!props.modelValue) return
  if (event.key === 'Escape') {
    event.preventDefault()
    handleCancel()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>
