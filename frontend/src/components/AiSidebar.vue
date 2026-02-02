<template>
  <aside
    class="fixed inset-y-0 right-0 z-50 w-full max-w-sm border-l border-soft bg-white shadow-2xl lg:w-[30rem] flex flex-col transition-all duration-300 transform overflow-hidden">
    <!-- Header -->
    <div
      class="flex items-center justify-between border-b border-soft px-4 py-3 bg-slate-50/50 backdrop-blur-sm shrink-0">
      <div class="flex items-center gap-2">
        <SparklesIcon class="h-5 w-5 text-brand-600" />
        <h2 class="text-sm font-semibold text-primary">AI 助手</h2>
      </div>
      <div class="flex items-center gap-1">
        <!-- New Chat Button -->
        <button type="button" @click="createNewSession" title="新建对话"
          class="flex h-8 w-8 items-center justify-center rounded-lg text-secondary transition hover:bg-surface hover:text-brand-600">
          <PlusIcon class="h-5 w-5" />
        </button>
        <!-- History Button -->
        <button type="button" @click="toggleHistory" title="会话历史"
          :class="[showHistory ? 'text-brand-600 bg-surface' : 'text-secondary']"
          class="flex h-8 w-8 items-center justify-center rounded-lg transition hover:bg-surface hover:text-brand-600">
          <ClockIcon class="h-5 w-5" />
        </button>
        <!-- Close Button -->
        <button type="button"
          class="flex h-8 w-8 items-center justify-center rounded-lg text-secondary transition hover:bg-surface hover:text-primary ml-1"
          @click="$emit('close')">
          <XMarkIcon class="h-5 w-5" />
        </button>
      </div>
    </div>

    <!-- Deep Chat Component -->
    <div class="flex-1 relative min-h-0 bg-white">
      <deep-chat :key="currentSessionId" ref="chatRef" class="deep-chat-container" :introMessage="introMessage"
        :connect.prop="requestConfig" :textInput.prop="textInputConfig" :messageStyles.prop="messageStyles"
        :submitButtonStyles.prop="submitButtonStyles" :inputAreaStyle.prop="inputAreaStyle"
        :auxiliaryStyle.prop="auxiliaryStyle" :error.prop="errorConfig" :history.prop="chatHistory"
        @message="onChatUpdate" style="height: 100%; width: 100%; border: none; display: block;"></deep-chat>

      <!-- History Overlay -->
      <transition enter-active-class="transition ease-out duration-200" enter-from-class="opacity-0 translate-y-1"
        enter-to-class="opacity-100 translate-y-0" leave-active-class="transition ease-in duration-150"
        leave-from-class="opacity-100 translate-y-0" leave-to-class="opacity-0 translate-y-1">
        <div v-if="showHistory" class="absolute inset-0 z-20 bg-white/95 backdrop-blur-sm p-4 overflow-y-auto overscroll-contain">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-sm font-bold text-slate-900">会话历史</h3>
            <button @click="showHistory = false" class="text-slate-400 hover:text-slate-600">
              <XMarkIcon class="h-5 w-5" />
            </button>
          </div>
          <div v-if="sessions.length === 0" class="text-center py-10">
            <p class="text-xs text-slate-400">暂无历史会话</p>
          </div>
          <div class="space-y-2">
            <div v-for="session in sortedSessions" :key="session.id" @click="switchSession(session.id)"
              :class="[session.id === currentSessionId ? 'border-brand-500 bg-brand-50' : 'border-slate-200 hover:border-brand-300 hover:bg-slate-50']"
              class="group relative p-3 rounded-xl border transition-all cursor-pointer">
              <div class="pr-8">
                <p class="text-sm font-medium text-slate-800 truncate">{{ session.title || '新对话' }}</p>
                <p class="text-[10px] text-slate-400 mt-1">{{ formatDate(session.updatedAt) }}</p>
              </div>
              <button @click.stop="deleteSession(session.id)"
                class="absolute top-3 right-3 p-1 text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                <TrashIcon class="h-4 w-4" />
              </button>
            </div>
          </div>
          <!-- History Disclaimer Footer -->
          <div class="mt-6 pt-4 border-t border-slate-100">
            <p class="text-[10px] text-slate-400 text-center leading-relaxed">
              您的对话信息仅保存在本地浏览器中，不会上传云端或用于分析。清除浏览器缓存将清空所有记录。目前系统默认保留最近 {{ maxSessions }} 条会话。
              <span @click="showSettings = true"
                class="underline cursor-pointer hover:text-brand-600 block mt-1">修改保存设置...</span>
            </p>
          </div>
        </div>
      </transition>

      <!-- Settings Overlay -->
      <transition enter-active-class="transition ease-out duration-200" enter-from-class="opacity-0 scale-95"
        enter-to-class="opacity-100 scale-100" leave-active-class="transition ease-in duration-150"
        leave-from-class="opacity-100 scale-100" leave-to-class="opacity-0 scale-95">
        <div v-if="showSettings"
          class="absolute inset-x-4 top-1/4 z-30 bg-white rounded-2xl shadow-2xl border border-slate-200 p-6">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-sm font-bold text-slate-900">会话存储设置</h3>
            <button @click="showSettings = false" class="text-slate-400 hover:text-slate-600">
              <XMarkIcon class="h-4 w-4" />
            </button>
          </div>
          <div class="space-y-4">
            <div>
              <label class="block text-xs font-medium text-slate-500 mb-2">最多保留会话数</label>
              <div class="flex items-center gap-3">
                <input type="number" v-model.number="tempMaxSessions" min="1" max="100"
                  class="block w-full rounded-lg border-slate-200 text-sm focus:border-brand-500 focus:ring-brand-500" />
                <span class="text-xs text-slate-400">条</span>
              </div>
              <p class="mt-2 text-[10px] text-slate-400">建议范围：5 - 50 条。保存更多会话可能会占用更多本地存储空间。</p>
            </div>
            <button @click="handleSaveSettings"
              class="w-full py-2 px-4 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium rounded-xl transition-colors">
              保存设置
            </button>
          </div>
        </div>
      </transition>
    </div>

    <!-- Main Footer Container -->
    <div class="px-4 py-2 bg-white border-t border-slate-100 shrink-0">
      <p class="text-[10px] text-slate-400 text-center leading-relaxed italic">
        AI 生成的消息可能包含错误信息，请人工核对
      </p>
    </div>
  </aside>
</template>

<script setup>
import 'deep-chat'
import { computed, ref, onMounted, watch } from 'vue'
import { SparklesIcon, XMarkIcon, PlusIcon, ClockIcon, TrashIcon } from '@heroicons/vue/24/outline'
import { useApiBase } from '../composables/useApiBase'
import { useAiChat } from '../composables/useAiChat'

const props = defineProps({
  isOpen: Boolean
})

const emit = defineEmits(['close'])

const { chatHandler } = useAiChat()
const inputContent = ref('')
const chatRef = ref(null)
const showHistory = ref(false)
const showSettings = ref(false)

// Session Management Logic
const STORAGE_KEY = 'opinion_system_ai_sessions'
const SETTINGS_KEY = 'opinion_system_ai_max_sessions'
const DEFAULT_MAX_SESSIONS = 20

const maxSessions = ref(parseInt(localStorage.getItem(SETTINGS_KEY)) || DEFAULT_MAX_SESSIONS)
const tempMaxSessions = ref(maxSessions.value)

const sessions = ref([])
const currentSessionId = ref('')
const chatHistory = ref([])

const saveSessions = () => {
  try {
    if (sessions.value.length === 0) return // Safety: don't wipe data if called with empty state
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions.value))
    console.log('[AiSidebar] Sessions saved to localStorage. Count:', sessions.value.length)
  } catch (e) {
    console.error('[AiSidebar] Failed to save sessions:', e)
  }
}

const createNewSession = () => {
  const newId = Date.now().toString()
  const newSession = {
    id: newId,
    title: '',
    messages: [],
    updatedAt: new Date().toISOString()
  }

  sessions.value.unshift(newSession)
  if (sessions.value.length > maxSessions.value) {
    sessions.value = sessions.value.slice(0, maxSessions.value)
  }

  currentSessionId.value = newId
  chatHistory.value = [] // Reset for new session
  saveSessions()
  showHistory.value = false
}

const loadSessions = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (!saved) {
      console.log('[AiSidebar] No saved sessions found, creating first one.')
      createNewSession()
      return
    }
    const parsed = JSON.parse(saved)
    if (!Array.isArray(parsed) || parsed.length === 0) {
      console.log('[AiSidebar] Parsed sessions empty, creating first one.')
      createNewSession()
      return
    }

    sessions.value = parsed
    
    // Check if the most recent session is empty
    const latestSession = parsed[0]
    if (latestSession && Array.isArray(latestSession.messages) && latestSession.messages.length > 0) {
      createNewSession()
    } else {
      currentSessionId.value = latestSession.id
      chatHistory.value = [...latestSession.messages]
    }
    console.log('[AiSidebar] Successfully loaded sessions:', parsed.length)
  } catch (e) {
    console.error('[AiSidebar] Failed to load sessions:', e)
    createNewSession()
  }
}

// Deep watch sessions for any changes (messages, titles, etc)
watch(sessions, () => {
  saveSessions()
}, { deep: true })

// Initial load
loadSessions()

const handleSaveSettings = () => {
  if (tempMaxSessions.value < 1) tempMaxSessions.value = 1
  if (tempMaxSessions.value > 100) tempMaxSessions.value = 100

  maxSessions.value = tempMaxSessions.value
  localStorage.setItem(SETTINGS_KEY, maxSessions.value.toString())

  // Apply limit immediately if sessions exceed new limit
  if (sessions.value.length > maxSessions.value) {
    sessions.value = sessions.value.slice(0, maxSessions.value)
    saveSessions()
  }

  showSettings.value = false
}

const switchSession = (id) => {
  if (currentSessionId.value === id) {
    showHistory.value = false
    return
  }

  const target = sessions.value.find(s => s.id === id)
  if (target) {
    currentSessionId.value = id
    // Update chatHistory REF which is bound to deep-chat
    // This triggers the key change OR prop change once
    chatHistory.value = [...target.messages]
    console.log('[AiSidebar] Switched to session:', id, 'messages:', chatHistory.value.length)
  }
  showHistory.value = false
}

const deleteSession = (id) => {
  sessions.value = sessions.value.filter(s => s.id !== id)
  if (currentSessionId.value === id) {
    if (sessions.value.length > 0) {
      currentSessionId.value = sessions.value[0].id
    } else {
      createNewSession()
    }
  }
  saveSessions()
}

const currentMessages = computed(() => {
  // This is now used mainly for debugging or if any other UI needs it
  const session = sessions.value.find(s => s.id === currentSessionId.value)
  return session ? session.messages : []
})

const sortedSessions = computed(() => {
  return [...sessions.value].sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))
})

const toggleHistory = () => {
  showHistory.value = !showHistory.value
}

const onChatUpdate = async () => {
  if (!chatRef.value) return

  // Use getMessages() to fetch the internal state of deep-chat
  const allMessages = await chatRef.value.getMessages()
  const sessionId = currentSessionId.value
  const sessionIndex = sessions.value.findIndex(s => s.id === sessionId)

  if (sessionIndex !== -1 && Array.isArray(allMessages) && allMessages.length > 0) {
    const session = sessions.value[sessionIndex]

    // Standardize role names for persistence
    session.messages = allMessages.map(m => ({
      role: m.role || 'ai',
      text: m.text || m.html || ''
    }))

    session.updatedAt = new Date().toISOString()

    // Generate title from the first valid user message if it's currently generic
    if (!session.title || session.title === '新对话' || session.title.trim() === '') {
      const firstUserMsg = allMessages.find(m => m.role === 'user' && (m.text || m.html))
      if (firstUserMsg) {
        let title = (firstUserMsg.text || firstUserMsg.html).trim()
        if (title.length > 30) title = title.substring(0, 30) + '...'
        session.title = title || '新对话'
        console.log('[AiSidebar] Generated session title:', session.title)
      }
    }
  } else {
    console.warn('[AiSidebar] onChatUpdate: Session not found or no messages!', sessionId)
  }
}

const formatDate = (isoString) => {
  const date = new Date(isoString)
  return date.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  console.log('[AiSidebar] Component mounted.')
})

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
  #container {
    overscroll-behavior: contain;
  }
  #messages {
    overscroll-behavior: contain;
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
