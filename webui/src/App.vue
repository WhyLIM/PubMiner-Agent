<script setup lang="ts">
import { useRoute } from "vue-router";
import { Odometer, ChatDotRound, Checked } from "@element-plus/icons-vue";

const route = useRoute();
const menu = [
  { path: "/", label: "总览", icon: Odometer, exact: true },
  { path: "/agent", label: "Agent 工作台", icon: ChatDotRound, exact: false },
  { path: "/review", label: "证据审核", icon: Checked, exact: true },
];
</script>

<template>
  <div class="pm-layout">
    <aside class="pm-sidebar">
      <div class="pm-logo">
        <span class="pi">Π</span>
        <span>
          PubMiner
          <small>Evidence Agent</small>
        </span>
      </div>
      <nav class="pm-menu">
        <router-link
          v-for="item in menu"
          :key="item.path"
          :to="item.path"
          :class="{ 'active-on': !item.exact && route.path.startsWith(item.path) }"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          {{ item.label }}
        </router-link>
      </nav>
      <div class="pm-sidebar-footer">
        可信生物医学证据 Agent<br />
        每条结论 · 钉在原文上
      </div>
    </aside>
    <main class="pm-main">
      <router-view />
    </main>
  </div>
</template>
