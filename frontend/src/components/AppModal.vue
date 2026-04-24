<template>
  <Teleport to="body">
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
        class="modal-backdrop fixed inset-0 z-[9999] flex items-center justify-center px-4 py-6"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        @click.self="handleBackdrop"
      >
        <div
          class="w-full overflow-hidden rounded-3xl bg-surface shadow-2xl"
          :class="[width, scrollable ? 'flex flex-col' : 'p-6']"
          :style="scrollable ? 'max-height: 82vh' : ''"
        >
          <header
            class="flex items-start justify-between gap-4 border-b border-soft"
            :class="scrollable ? 'flex-none px-6 pt-6 pb-4' : 'pb-4'"
          >
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
              <XMarkIcon class="h-5 w-5" />
            </button>
          </header>

          <section
            :data-app-select-boundary="scrollable ? '' : null"
            class="text-sm text-secondary"
            :class="scrollable ? 'min-h-0 flex-1 overflow-y-auto px-6 py-4 space-y-4' : 'mt-4 space-y-4'"
          >
            <slot name="description">
              <p v-if="description">{{ description }}</p>
            </slot>
            <slot />
          </section>

          <footer
            v-if="showFooter"
            class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end sm:gap-4"
            :class="scrollable ? 'flex-none border-t border-soft px-6 py-4' : 'mt-6'"
          >
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
              class="btn-base px-5 py-2"
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
  </Teleport>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { XMarkIcon } from '@heroicons/vue/24/outline'

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
  },
  showFooter: {
    type: Boolean,
    default: true
  },
  scrollable: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'cancel', 'confirm'])
const isClient = typeof window !== 'undefined'
let previousBodyOverflow = ''

const confirmButtonClass = computed(() => {
  if (props.confirmTone === 'danger') {
    return 'btn-tone-danger'
  }
  if (props.confirmTone === 'success') {
    return 'btn-tone-success'
  }
  return 'btn-tone-primary'
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

const syncBodyScrollLock = (open) => {
  if (!isClient) return
  if (open) {
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return
  }
  document.body.style.overflow = previousBodyOverflow
}

watch(
  () => props.modelValue,
  (open) => {
    syncBodyScrollLock(open)
  },
  { immediate: true }
)

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  syncBodyScrollLock(false)
})
</script>
