import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

import './assets/main.css'
import { initializeTheme } from './settings/theme/themeManager'

const app = createApp(App)

app.use(router)

initializeTheme()

app.mount('#app')
