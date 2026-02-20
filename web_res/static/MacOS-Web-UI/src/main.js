import { createApp } from 'vue'
import { createStore } from 'vuex'

import MacOS from './MacOS'
let macOS = createApp(MacOS)


import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
macOS.use(ElementPlus, {
    locale: zhCn,
})

import "@/asset/css/app.css"
import "@/asset/css/animation.css"

import config from './config'
macOS.config.globalProperties.config = config

import tool from './helper/tool'
macOS.config.globalProperties.tool = tool

import AppStore from './store/App'
const store = createStore(AppStore)
macOS.use(store)

window.macOS = macOS
macOS.mount('#app')