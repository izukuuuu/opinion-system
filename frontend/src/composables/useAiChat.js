import { ref, unref } from 'vue'
import { useApiBase } from './useApiBase'

export function useAiChat() {
    const { ensureApiBase } = useApiBase()

    /**
     * Handler for Deep Chat component
     * @param {Object} body - Request body from Deep Chat (contains { messages: [] })
     * @param {Object} signals - Deep Chat signals for stream control ({ onResponse, onStop, ... })
     */
    const chatHandler = async (body, signals) => {
        const controller = new AbortController()
        if (typeof signals.onStop === 'function') {
            signals.onStop(() => controller.abort())
        } else if (typeof signals.stopClicked === 'function') {
            signals.stopClicked(() => controller.abort())
        }


        try {
            const baseUrl = await ensureApiBase()
            // Clean up base URL to ensure valid path concatenation
            const cleanBase = baseUrl.replace(/\/+$/, '')
            const url = `${cleanBase}/ai/chat`

            // Deep Chat uses 'text', OpenAI expects 'content'
            const messages = body.messages.map(msg => ({
                role: msg.role,
                content: msg.text || ''
            }))

            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    messages
                }),
                signal: controller.signal
            })

            if (!response.ok) {
                const text = await response.text().catch(() => '')
                throw new Error(`Server Error (${response.status}): ${text || response.statusText}`)
            }

            // Signal that streaming is starting
            if (typeof signals.onOpen === 'function') {
                signals.onOpen()
            }

            const reader = response.body.getReader()
            const decoder = new TextDecoder()

            while (true) {
                const { done, value } = await reader.read()
                if (done) break
                const text = decoder.decode(value, { stream: true })
                signals.onResponse({ text, overwrite: false })
            }

            // Signal that streaming is complete
            if (typeof signals.onClose === 'function') {
                signals.onClose()
            }

        } catch (e) {
            if (e.name === 'AbortError') return
            console.error('AI Chat Error:', e)
            signals.onResponse({ error: e.message || 'Network error occurred' })
        }
    }

    return {
        chatHandler
    }
}
