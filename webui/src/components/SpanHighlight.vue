<script setup lang="ts">
/** 原文 span 高亮渲染：canonical text + 定位区间 mark。 */
defineProps<{
  canonicalText: string;
  startChar: number;
  endChar: number;
}>();
</script>

<template>
  <p class="canonical-text">
    {{ canonicalText.slice(0, startChar)
    }}<mark class="evidence-highlight">{{ canonicalText.slice(startChar, endChar) }}</mark
    >{{ canonicalText.slice(endChar) }}
  </p>
</template>
