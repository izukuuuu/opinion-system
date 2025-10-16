<template>
  <transition
    enter-active-class="transition ease-out duration-200"
    enter-from-class="opacity-0"
    enter-to-class="opacity-100"
    leave-active-class="transition ease-in duration-150"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
  >
    <div
      v-if="modelValue"
      class="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 px-4 py-6 backdrop-blur"
      @click.self="handleBackdrop"
    >
      <div
        class="w-full rounded-3xl bg-white p-6 shadow-2xl"
        :class="width"
      >
        <header class="flex items-start justify-between gap-4 border-b border-slate-200 pb-4">
          <div class="space-y-1.5">
            <p v-if="eyebrow" class="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">
              {{ eyebrow }}
            </p>
            <h2 class="text-2xl font-semibold text-slate-900">
              {{ title }}
            </h2>
          </div>
          <button
            v-if="showClose"
            type="button"
            class="flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 text-slate-500 transition hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            @click="handleCancel"
            aria-label="关闭"
          >
            ✕
          </button>
        </header>

        <section class="mt-4 space-y-4 text-sm text-slate-600">
          <slot name="description">
            <p v-if="description">{{ description }}</p>
          </slot>
          <slot />
        </section>

        <footer class="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end sm:gap-4">
          <button
            type="button"
            class="inline-flex items-center justify-center rounded-full border border-slate-200 px-5 py-2 text-sm font-medium text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
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
    return 'bg-rose-600 hover:bg-rose-500 focus-visible:outline-rose-600 disabled:cursor-not-allowed disabled:bg-rose-300'
  }
  if (props.confirmTone === 'success') {
    return 'bg-emerald-600 hover:bg-emerald-500 focus-visible:outline-emerald-600 disabled:cursor-not-allowed disabled:bg-emerald-300'
  }
  return 'bg-indigo-600 hover:bg-indigo-500 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:bg-indigo-300'
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
