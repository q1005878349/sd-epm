<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-logo">⚡</div>
        <div class="brand-text">
          <span class="brand-name">山东电价预测</span>
          <span class="brand-sub">储能套利系统</span>
        </div>
      </div>
      <nav class="nav">
        <router-link v-for="r in routes" :key="r.path" :to="r.path" class="nav-item"
          :class="{ active: $route.path === r.path }">
          <span class="nav-icon">{{ r.meta.icon }}</span>
          <span class="nav-label">{{ r.meta.title }}</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <div class="status-indicator">
          <span class="status-dot"></span>
          <span class="status-text">系统运行中</span>
        </div>
      </div>
    </aside>
    <main class="main">
      <router-view v-slot="{ Component }">
        <transition name="page-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
const routes = [
  { path: '/forecast', meta: { title: '电价预测', icon: '📈' } },
  { path: '/backtest', meta: { title: '回测与节省', icon: '💰' } },
  { path: '/settings', meta: { title: '参数与数据', icon: '⚙️' } },
]
</script>
