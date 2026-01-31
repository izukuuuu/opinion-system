<template>
  <aside
    class="fixed inset-y-0 right-0 z-50 w-full max-w-sm border-l border-soft bg-white shadow-2xl lg:w-96 flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between border-b border-soft px-4 py-3 bg-slate-50/50 backdrop-blur-sm">
      <div class="flex items-center gap-2">
        <SparklesIcon class="h-5 w-5 text-brand-600" />
        <h2 class="text-sm font-semibold text-primary">AI 助手</h2>
      </div>
      <div class="flex items-center gap-1">
        <button v-if="messages.length > 0" type="button"
          class="p-1.5 text-secondary hover:text-red-500 transition-colors rounded-md hover:bg-red-50"
          @click="clearChat" title="Clear Chat">
          <TrashIcon class="h-4 w-4" />
        </button>
        <button type="button"
          class="flex h-8 w-8 items-center justify-center rounded-lg text-secondary transition hover:bg-surface hover:text-primary"
          @click="$emit('close')">
          <XMarkIcon class="h-5 w-5" />
        </button>
      </div>
    </div>

    <!-- Chat Area -->
    <div class="flex-1 overflow-y-auto px-4 py-4 space-y-4 scroll-smooth" ref="chatContainer">
      <!-- Welcome State -->
      <div v-if="messages.length === 0"
        class="flex flex-col items-center justify-center gap-4 py-12 text-center h-full">
        <div class="rounded-full bg-brand-50 p-4 ring-1 ring-brand-100">
          <SparklesIcon class="h-8 w-8 text-brand-500" />
        </div>
        <div class="space-y-1">
          <h3 class="font-medium text-primary">AI 助手准备就绪</h3>
          <p class="text-sm text-secondary px-8">我可以协助您分析舆情数据、撰写报告或回答相关问题。</p>
        </div>
      </div>

      <!-- Messages -->
      <template v-else>
        <div v-for="(msg, index) in messages" :key="index" class="flex flex-col gap-1"
          :class="msg.role === 'user' ? 'items-end' : 'items-start'">
          <div class="flex items-end gap-2 max-w-[85%]">
            <div v-if="msg.role === 'assistant'"
              class="flex-shrink-0 w-6 h-6 rounded-full bg-brand-100 flex items-center justify-center text-brand-600 text-xs font-bold ring-1 ring-brand-200">
              AI
            </div>

            <div class="rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm break-words" :class="[
              msg.role === 'user'
                ? 'bg-brand-600 text-white rounded-br-none'
                : 'bg-white border border-gray-100 text-primary rounded-bl-none'
            ]">
              <div v-if="msg.role === 'assistant'" class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
              <!-- Simple render for now, or just text -->
              <span v-else>{{ msg.content }}</span>
            </div>
          </div>
        </div>

        <div v-if="isLoading" class="flex items-start gap-2">
          <div
            class="flex-shrink-0 w-6 h-6 rounded-full bg-brand-100 flex items-center justify-center text-brand-600 text-xs font-bold ring-1 ring-brand-200 animate-pulse">
            AI
          </div>
          <div class="bg-white border border-gray-100 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm">
            <div class="flex gap-1">
              <span class="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"></span>
              <span class="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce delay-75"></span>
              <span class="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce delay-150"></span>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Input Area -->
    <div class="border-t border-soft px-4 py-4 bg-white">
      <div
        class="relative flex items-end gap-2 rounded-xl border border-soft bg-white p-2 shadow-sm focus-within:ring-2 focus-within:ring-brand-500/20 focus-within:border-brand-500 transition-all">
        <textarea v-model="inputContent" rows="1" placeholder="输入您的问题..."
          class="w-full resize-none border-0 bg-transparent py-2 pl-2 text-sm text-primary placeholder:text-muted focus:ring-0 max-h-32"
          @keydown.enter.prevent="handleEnter" :disabled="isLoading"></textarea>
        <button type="button"
          class="flex-shrink-0 p-2 rounded-lg bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          @click="handleSubmit" :disabled="isLoading || !inputContent.trim()">
          <PaperAirplaneIcon class="h-4 w-4" />
        </button>
      </div>
      <p class="text-[10px] text-center text-muted mt-2">AI 生成内容可能包含错误，请核实重要信息。</p>
    </div>
  </aside>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { SparklesIcon, XMarkIcon, PaperAirplaneIcon, TrashIcon } from '@heroicons/vue/24/outline'
import { useAiChat } from '../composables/useAiChat'
import { marked } from 'marked'

const renderMarkdown = (text) => {
  try {
    return marked.parse(text)
  } catch (e) {
    console.error('Markdown parsing error:', e)
    return text
  }
}

const props = defineProps({
  isOpen: Boolean
})

const emit = defineEmits(['close'])

const { messages, isLoading, sendMessage, clearChat } = useAiChat()
const inputContent = ref('')
const chatContainer = ref(null)

const scrollToBottom = async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

watch(messages, () => {
  scrollToBottom()
}, { deep: true })

const handleSubmit = async () => {
  if (!inputContent.value.trim() || isLoading.value) return

  const content = inputContent.value
  inputContent.value = ''
  await sendMessage(content)
}

const handleEnter = (e) => {
  if (e.shiftKey) return
  handleSubmit()
}
</script>

<style scoped>
/* Custom scrollbar for webkit */
::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
</style>
