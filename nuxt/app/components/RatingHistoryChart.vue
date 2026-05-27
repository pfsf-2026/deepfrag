<script setup>
import { Chart, registerables } from 'chart.js'
if (!Chart.registry?.controllers?.get('line')) {
  Chart.register(...registerables)
}

const props = defineProps({
  points: { type: Array, default: () => [] },     // [{match_date, conservative, mu, sigma, delta, outcome}]
  height: { type: Number, default: 220 }
})

const canvas = ref(null)
let chart = null

// Aggregate to ~150 sample points for chart readability — beyond that the
// line becomes a blur. Picks evenly-spaced indexes; keeps endpoints.
function downsample(pts, target = 150) {
  if (pts.length <= target) return pts
  const step = (pts.length - 1) / (target - 1)
  const out = []
  for (let i = 0; i < target; i++) out.push(pts[Math.round(i * step)])
  return out
}

function build() {
  if (!canvas.value || !props.points.length) return
  chart?.destroy()
  const data = downsample(props.points)
  // Plot μ (point estimate) not conservative (μ − 3σ). σ starts at 500 with
  // OpenSkill defaults, so conservative dips to ~-600 before stabilizing —
  // mathematically correct but visually reads as "you were a -600 player."
  // μ moves naturally from the 1500 default → reflects skill changes only.
  const mu = data.map(p => p.mu)
  const labels = data.map(p => p.match_date)
  chart = new Chart(canvas.value, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Rating (μ)',
        data: mu,
        borderColor: '#14e6c0',
        backgroundColor: 'rgba(20, 230, 192, 0.12)',
        borderWidth: 1.8,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.25,
        fill: true,
        spanGaps: true
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => new Date(items[0].label).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }),
            label: (item) => {
              const p = data[item.dataIndex]
              return `cons ${p.conservative}  ·  μ ${p.mu}  ·  σ ${p.sigma}  ·  ${p.outcome}${p.delta > 0 ? ' (+' + p.delta.toFixed(1) + ')' : p.delta < 0 ? ' (' + p.delta.toFixed(1) + ')' : ''}`
            }
          }
        }
      },
      scales: {
        x: { display: false },
        y: {
          ticks: { color: '#64748b', font: { size: 10, family: 'JetBrains Mono' } },
          grid: { color: 'rgba(100, 116, 139, 0.08)' }
        }
      }
    }
  })
}

onMounted(build)
watch(() => props.points, build)
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div class="rh-wrap" :style="{ height: height + 'px' }">
    <canvas ref="canvas" />
  </div>
</template>

<style scoped>
.rh-wrap { position: relative; width: 100%; }
.rh-wrap canvas { position: absolute !important; left: 0; top: 0; width: 100% !important; height: 100% !important; }
</style>
