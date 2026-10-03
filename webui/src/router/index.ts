import { createRouter, createWebHistory } from 'vue-router';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'literature',
      component: () => import('@/components/LiteratureView.vue'),
    },
    {
      path: '/graph',
      name: 'graph',
      component: () => import('@/components/KnowledgeGraphView.vue'),
    },
    {
      path: '/analytics',
      name: 'analytics',
      component: () => import('@/components/AnalyticsView.vue'),
    },
    {
      path: '/workflow',
      name: 'workflow',
      component: () => import('@/components/AgentWorkflowView.vue'),
    },
    {
      path: '/synthesis',
      name: 'synthesis',
      component: () => import('@/components/SynthesisReviewView.vue'),
    },
  ],
});
