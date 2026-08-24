import { createRouter, createWebHistory } from 'vue-router'
import ForecastView from './views/ForecastView.vue'
import BacktestView from './views/BacktestView.vue'
import SettingsView from './views/SettingsView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/forecast' },
    { path: '/forecast', name: 'forecast', component: ForecastView, meta: { title: '预测' } },
    { path: '/backtest', name: 'backtest', component: BacktestView, meta: { title: '回测与节省' } },
    { path: '/settings', name: 'settings', component: SettingsView, meta: { title: '参数与数据' } },
  ]
})
