import { createRouter, createWebHistory } from "vue-router";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "dashboard", component: () => import("@/views/DashboardView.vue") },
    { path: "/agent", name: "agent", component: () => import("@/views/AgentView.vue") },
    { path: "/review", name: "review", component: () => import("@/views/ReviewView.vue") },
  ],
});
