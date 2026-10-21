import { createApp } from 'vue'

import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap-icons/font/bootstrap-icons.css'
import 'bootstrap'
import './assets/main.css'

import App from './App.vue'
import { attachRouter } from './api/client'
import router from './router'
import pinia from './stores'

const app = createApp(App).use(pinia).use(router)
attachRouter(router)
app.mount('#app')
