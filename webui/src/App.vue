<script setup lang="ts">
import { useRoute } from "vue-router";
import { Odometer, ChatDotRound, Checked, Moon, Sunny } from "@element-plus/icons-vue";
import { isDark, toggleTheme } from "@/composables/useTheme";

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
        <span>每条结论都钉在原文上</span>
        <el-button
          :icon="isDark ? Sunny : Moon"
          circle
          size="small"
          text
          bg
          aria-label="切换明暗主题"
          @click="toggleTheme"
        />
      </div>
    </aside>
    <main class="pm-main">
      <router-view />
    </main>
  </div>
</template>
