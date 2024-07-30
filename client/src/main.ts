import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import axios from 'axios'

const apiUrl = import.meta.env.VITE_API_URL || 'https://api.websitetotext.com'
axios.defaults.baseURL = apiUrl
axios.defaults.withCredentials = true

console.log("Axios base URL set to:", axios.defaults.baseURL)

createApp(App).mount('#app')