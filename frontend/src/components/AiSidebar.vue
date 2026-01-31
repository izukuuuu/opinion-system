<template>
  <aside
    class="fixed inset-y-0 right-0 z-50 w-full max-w-sm border-l border-soft bg-white shadow-2xl lg:w-[30rem] flex flex-col transition-all duration-300 transform">
    <!-- Header -->
    <div
      class="flex items-center justify-between border-b border-soft px-4 py-3 bg-slate-50/50 backdrop-blur-sm shrink-0">
      <div class="flex items-center gap-2">
        <SparklesIcon class="h-5 w-5 text-brand-600" />
        <h2 class="text-sm font-semibold text-primary">AI 助手</h2>
      </div>
      <button type="button"
        class="flex h-8 w-8 items-center justify-center rounded-lg text-secondary transition hover:bg-surface hover:text-primary"
        @click="$emit('close')">
        <XMarkIcon class="h-5 w-5" />
      </button>
    </div>

    <!-- Deep Chat Component -->
    <div class="flex-1 relative min-h-0 bg-white">
      <deep-chat ref="chatRef" class="deep-chat-container" :introMessage="introMessage" :connect.prop="requestConfig"
        :textInput.prop="textInputConfig" :messageStyles.prop="messageStyles"
        :submitButtonStyles.prop="submitButtonStyles" :inputAreaStyle.prop="inputAreaStyle"
        :auxiliaryStyle.prop="auxiliaryStyle" :error.prop="errorConfig" :initialMessages.prop="historyMessages"
        @message="onNewMessage" style="height: 100%; width: 100%; border: none; display: block;"></deep-chat>
    </div>
  </aside>
</template>

<script setup>
import 'deep-chat'
import { computed, ref, onMounted } from 'vue'
import { SparklesIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import { useApiBase } from '../composables/useApiBase'
import { useAiChat } from '../composables/useAiChat'

defineProps({
  isOpen: Boolean
})

const emit = defineEmits(['close'])
const { chatHandler } = useAiChat()
const inputContent = ref('')
const chatRef = ref(null)

// Chat History Logic
const HISTORY_KEY = 'opinion_system_chat_history'
const MAX_HISTORY_MESSAGES = 10 // 5 rounds (User + AI)

const loadHistory = () => {
  try {
    const saved = localStorage.getItem(HISTORY_KEY)
    return saved ? JSON.parse(saved) : []
  } catch (e) {
    console.error('Failed to load chat history:', e)
    return []
  }
}

const historyMessages = ref(loadHistory())

const onNewMessage = (event) => {
  // event.detail contains all messages in deep-chat
  // We take all messages and keep the last 10
  const allMessages = event.detail
  if (Array.isArray(allMessages)) {
    const trimmed = allMessages.slice(-MAX_HISTORY_MESSAGES)
    localStorage.setItem(HISTORY_KEY, JSON.stringify(trimmed))
  }
}

// Initial welcome message
const introMessage = {
  text: '您好！我是 Opinion System 的 AI 助手。我可以协助您分析舆情数据、撰写报告或回答相关问题。'
}

// Configuration for the request
const requestConfig = computed(() => {
  return {
    handler: chatHandler,
    stream: true
  }
})

// UI Configuration - using theme colors
const textInputConfig = {
  placeholder: { text: '输入您的问题...' },
  styles: {
    container: {
      position: 'relative', // Anchor for the absolute button
      borderRadius: '1.5rem',
      border: '1px solid #d0d5d9',
      boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
      backgroundColor: '#ffffff',
      margin: '0',
      flex: '1',
      boxSizing: 'border-box',
      minWidth: '0'
    },
    text: {
      color: '#1c252c',
      fontSize: '0.9rem',
      padding: '0.65rem 3rem 0.65rem 1.25rem',
      boxSizing: 'border-box'
    }
  }
}

const messageStyles = {
  default: {
    shared: {
      bubble: {
        maxWidth: '85%',
        padding: '10px 14px',
        fontSize: '0.875rem',
        lineHeight: '1.5'
      }
    },
    user: {
      bubble: {
        backgroundColor: '#879db3', // brand-700
        color: 'white',
        borderRadius: '16px 16px 4px 16px'
      }
    },
    ai: {
      bubble: {
        backgroundColor: '#f5f8fa', // bg-base-soft
        color: '#1c252c',
        borderRadius: '16px 16px 16px 4px'
      }
    }
  }
}

// Heroicons PaperAirplaneIcon (solid) SVG
const sendIconSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" /></svg>'
const stopIconSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path fill-rule="evenodd" d="M4.5 7.5a3 3 0 013-3h9a3 3 0 013 3v9a3 3 0 01-3 3h-9a3 3 0 01-3-3v-9z" clip-rule="evenodd" /></svg>'
const loadingIconSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" class="animate-spin"><path d="M21 12a9 9 0 11-6.219-8.56" /></svg>'

// Button positioned absolute relative to the input container
// Button positioned absolute relative to the input container
const submitButtonStyles = {
  submit: {
    container: {
      default: {
        position: 'absolute',
        right: '0.5rem',
        top: '50%',
        transform: 'translateY(-50%)', // Mathematical center
        width: '2rem',
        height: '2rem',
        borderRadius: '50%',
        backgroundColor: '#879db3',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        zIndex: '1', // Ensure it sits above input text
        margin: '0'
      },
      hover: {
        backgroundColor: '#9ab2cb',
        transform: 'translateY(-50%) scale(1.05)'
      }
    },
    svg: {
      content: sendIconSvg,
      styles: {
        default: {
          width: '1rem',
          height: '1rem',
          filter: 'brightness(0) invert(1)'
        }
      }
    }
  },
  loading: {
    container: {
      default: {
        position: 'absolute',
        right: '0.5rem',
        top: '50%',
        transform: 'translateY(-50%)',
        width: '2rem',
        height: '2rem',
        borderRadius: '50%',
        backgroundColor: '#f5f8fa',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'default',
        zIndex: '1',
        margin: '0'
      }
    },
    svg: {
      content: loadingIconSvg,
      styles: {
        default: {
          width: '1rem',
          height: '1rem',
          color: '#879db3' // brand-700
        }
      }
    }
  },
  stop: {
    container: {
      default: {
        position: 'absolute',
        right: '0.5rem',
        top: '50%',
        transform: 'translateY(-50%)',
        width: '2rem',
        height: '2rem',
        borderRadius: '50%',
        backgroundColor: '#f5f8fa',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        zIndex: '1',
        margin: '0'
      },
      hover: {
        backgroundColor: '#fee2e2', // red-100
        transform: 'translateY(-50%) scale(1.05)'
      }
    },
    svg: {
      content: stopIconSvg,
      styles: {
        default: {
          width: '1rem',
          height: '1rem',
          color: '#ef4444' // red-500
        }
      }
    }
  }
}

// Ensure input container is relative to support absolute button
const inputAreaStyle = {
  padding: '10px 14px',
  backgroundColor: '#ffffff',
  borderTop: '1px solid #d0d5d9',
  display: 'flex',
  alignItems: 'center',
  boxSizing: 'border-box'
}

const auxiliaryStyle = `
  ::-webkit-scrollbar {
    width: 6px;
  }
  ::-webkit-scrollbar-thumb {
    background-color: #cbd5e1;
    border-radius: 3px;
  }
`

const errorConfig = {
  style: {
    borderRadius: '10px',
    backgroundColor: '#fee2e2',
    color: '#b91c1c'
  }
}

</script>

<style scoped>
.deep-chat-container {
  height: 100%;
  width: 100%;
  background-color: white;
  --deep-chat-font-family: 'Segoe UI', 'PingFang SC', sans-serif;
}
</style>
