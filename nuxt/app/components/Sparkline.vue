<script setup>
// Use registerables instead of cherry-picking — avoids missing-component bugs
// in production builds where tree-shaking can drop things.
import { Chart, registerables } from 'chart.js'
if (!Chart.registry?.controllers?.get('line')) {
  Chart.register(...registerables)
}

const props = defineProps({
  data: { type: Array, default: () => [] },
  color: { type: String, default: '#14e6c0' },
  height: { type: Number, default: 36 }
})

const canvas = ref(null)
let chart = null

function build() {
  if (!canvas.value) return
  chart?.destroy()
  if (!props.data.length || props.data.every(v => v == null)) return
  chart = new Chart(canvas.value, {
    type: 'line',
    data: {
      labels: props.data.map((_, i) => i),
      datasets: [{
        data: props.data,
        borderColor: props.color,
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        fill: true,
        backgroundColor: props.color + '22',
        spanGaps: true
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } }
    }
  })
}

onMounted(build)
watch(() => props.data, build)
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div class="spark-wrap" :style="{ height: height + 'px' }">
    <canvas ref="canvas" />
  </div>
</template>

<style scoped>
.spark-wrap { position: relative; width: 100%; }
.spark-wrap canvas {
  position: absolute !important; left: 0; top: 0;
  width: 100% !important; height: 100% !important;
}
</style>
