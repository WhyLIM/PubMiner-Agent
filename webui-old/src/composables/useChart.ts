import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, watch, type Ref } from "vue";

/** ECharts 生命周期封装：挂载初始化、数据变化重绘、窗口缩放自适应、卸载释放。 */
export function useChart(
  el: Ref<HTMLElement | undefined>,
  option: () => echarts.EChartsOption,
) {
  const chartRef = el;
  let instance: echarts.ECharts | null = null;

  const render = () => {
    if (!chartRef.value) return;
    if (!instance) {
      instance = echarts.init(chartRef.value);
    }
    instance.setOption(option(), true);
  };

  const onResize = () => instance?.resize();

  onMounted(() => {
    render();
    window.addEventListener("resize", onResize);
  });
  onBeforeUnmount(() => {
    window.removeEventListener("resize", onResize);
    instance?.dispose();
    instance = null;
  });
  watch(option, render, { deep: true });

  return { chartRef, rerender: render };
}
