/* 主题初始化必须在绘制前执行（index.html 内联脚本亦会设置，避免闪烁） */

/** 主题状态组合式：isDark 响应式 + toggle + 持久化（localStorage，缺省跟随系统）。 */
import { ref } from "vue";

const STORAGE_KEY = "pubminer-theme";

function initialDark(): boolean {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === "dark") return true;
  if (saved === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export const isDark = ref(initialDark());

export function applyTheme() {
  document.documentElement.classList.toggle("dark", isDark.value);
}

export function toggleTheme() {
  isDark.value = !isDark.value;
  localStorage.setItem(STORAGE_KEY, isDark.value ? "dark" : "light");
  applyTheme();
}

applyTheme();
