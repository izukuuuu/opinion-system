import { ref, unref } from 'vue'
import { useApiBase } from './useApiBase'

export function useAiChat() {
    const messages = ref([])
    const isLoading = ref(false)
    const error = ref(null)
    const { apiBase } = useApiBase()

    const sendMessage = async (content) => {
        if (!content.trim()) return

        const userMessage = { role: 'user', content }
        messages.value.push(userMessage)
        isLoading.value = true
        error.value = null

        try {
            // Create a temporary assistant message for streaming
            const assistantMessage = { role: 'assistant', content: '' }
            messages.value.push(assistantMessage)
            const assistantMessageIndex = messages.value.length - 1

            // Use apiBase to construct the URL. apiBase already includes '/api'
            // remove trailing slash if present to avoid double slashes, though generally harmless
            const baseUrl = unref(apiBase).replace(/\/$/, '')
            const url = `${baseUrl}/ai/chat`

            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    messages: messages.value.slice(0, -1), // Send history excluding the empty assistant placeholder
                }),
            })

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`)
            }

            const reader = response.body.getReader()
            const decoder = new TextDecoder()

            while (true) {
                const { done, value } = await reader.read()
                if (done) break

                const text = decoder.decode(value, { stream: true })
                messages.value[assistantMessageIndex].content += text
            }

        } catch (e) {
            console.error('Chat error:', e)
            error.value = e.message
            messages.value.push({ role: 'system', content: `Error: ${e.message}` })
        } finally {
            isLoading.value = false
        }
    }

    const clearChat = () => {
        messages.value = []
        error.value = null
    }

    return {
        messages,
        isLoading,
        error,
        sendMessage,
        clearChat
    }
}
