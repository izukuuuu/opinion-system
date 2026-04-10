import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

import './assets/main.css'
import { initializeTheme } from './settings/theme/themeManager'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

initializeTheme()

app.mount('#app')
