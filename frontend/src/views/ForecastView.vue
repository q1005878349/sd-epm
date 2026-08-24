<template>
  <div class="forecast-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">电价预测与调度</h2>
        <div class="page-sub">现货电价走势 · 工商业充/放着色对比 · 未来预测 · LP 优化调度</div>
      </div>
      <div class="page-header-meta">
        <span v-if="dayData" class="meta-badge green">
          <span class="meta-dot"></span>实时数据
        </span>
      </div>
    </div>

    <div class="grid2">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title-group">
            <span class="panel-icon">⚡</span>
            <h3>现货电价（真实）</h3>
          </div>
          <div class="toolbar">
            <el-date-picker v-model="day" type="date" value-format="YYYY-MM-DD"
              placeholder="选择日期" @change="loadDay" size="small" style="width:140px" />
            <el-radio-group v-model="interval" @change="loadDay" size="small">
              <el-radio-button :value="60">按小时</el-radio-button>
              <el-radio-button :value="15">15 分钟</el-radio-button>
            </el-radio-group>
          </div>
        </div>
        <div ref="spotChart" class="chart"></div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div class="panel-title-group">
            <span class="panel-icon">🏪</span>
            <h3>工商业电价对比</h3>
          </div>
          <span class="legend-dots">
            <i class="dot" style="background:#60a5fa"></i>实际
            <i class="dot" style="background:#f59e0b"></i>预测
            <i class="dot charge"></i>充电
            <i class="dot discharge"></i>放电
          </span>
        </div>
        <div ref="retailChart" class="chart"></div>
        <div class="revenue-bar" v-if="dayData && dayData.summary_actual">
          <div class="revenue-item">
            <span class="revenue-label">按实际价收益</span>
            <span class="revenue-value blue">{{ dayData.summary_actual.revenue_yuan }} 元</span>
          </div>
          <template v-if="dayData.summary_predicted && dayData.summary_predicted.revenue_yuan !== undefined">
            <span class="revenue-divider">|</span>
            <div class="revenue-item">
              <span class="revenue-label">按预测价收益</span>
              <span class="revenue-value amber">{{ dayData.summary_predicted.revenue_yuan }} 元</span>
            </div>
          </template>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div class="panel-title-group">
            <span class="panel-icon">🔮</span>
            <h3>预测电价（未来 {{ horizon === '24h' ? '24 小时' : '1 小时' }}）</h3>
          </div>
          <div class="toolbar">
            <el-radio-group v-model="horizon" size="small">
              <el-radio-button value="24h">24 小时</el-radio-button>
              <el-radio-button value="1h">1 小时</el-radio-button>
            </el-radio-group>
            <el-button type="primary" :loading="running" @click="runForecast" size="small" round>
              运行预测
            </el-button>
            <span v-if="fc" class="mae-badge">MAE {{ fc.mae?.toFixed(1) ?? '-' }} 元/MWh</span>
          </div>
        </div>
        <div ref="forecastChart" class="chart"></div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div class="panel-title-group">
            <span class="panel-icon">🔋</span>
            <h3>充放电调度计划</h3>
          </div>
          <span v-if="plan" class="plan-summary">
            <span class="plan-stat revenue">日收益 {{ plan.summary.revenue_yuan }} 元</span>
            <span class="plan-stat cycles">循环 {{ plan.summary.cycles }} 次</span>
          </span>
        </div>
        <div ref="dispatchChart" class="chart"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { touMarkAreas, baseGrid, axisStyle } from '../chartUtils'

const day = ref(null)
const interval = ref(60)
const horizon = ref('24h')
const running = ref(false)
const dayData = ref(null)   // { prices, schedule, summary } 所选日期的真实数据 + LP 调度
const fc = ref(null)        // 预测结果
const plan = ref(null)      // 最新调度计划

const spotChart = ref(null)
const retailChart = ref(null)
const forecastChart = ref(null)
const dispatchChart = ref(null)

const COLOR = { charge: '#34d399', discharge: '#f87171', idle: '#60a5fa' }

async function loadDay() {
  try {
    let d = day.value
    if (!d) {
      const latest = await api.prices(null, interval.value)
      d = latest.date
      day.value = d
    }
    const dp = await api.dispatchForDate(d, interval.value)
    dayData.value = dp
    await nextTick()
    renderSpot(dp.prices)
    renderRetail(dp)
  } catch (e) {
    ElMessage.warning(e.message || '该日期暂无数据')
  }
}

function renderSpot(points) {
  const inst = echarts.getInstanceByDom(spotChart.value) || echarts.init(spotChart.value)
  inst.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(22,27,34,0.96)',
      borderColor: 'rgba(52,211,153,0.2)',
      textStyle: { color: '#e6edf3', fontSize: 12 },
    },
    grid: { ...baseGrid, top: 20, bottom: 32 },
    xAxis: { type: 'category', data: points.map(p => p.ts.slice(5, 16)), ...axisStyle },
    yAxis: { type: 'value', name: '元/MWh', nameTextStyle: { color: '#8b98a5', fontSize: 11 }, ...axisStyle },
    series: [{
      name: '现货电价', type: 'line', data: points.map(p => p.spot),
      showSymbol: false, lineStyle: { color: '#60a5fa', width: 2.5 },
      itemStyle: { color: '#60a5fa' },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: 'rgba(96,165,250,0.15)' }, { offset: 1, color: 'rgba(96,165,250,0.0)' }] } },
      markArea: { silent: true, data: touMarkAreas(points) },
    }],
  }, true)
}

function renderRetail(dp) {
  const allLabels = dp.prices.map(p => p.ts.slice(5, 16))
  const tsToLabel = {}
  dp.prices.forEach((p, i) => { tsToLabel[p.ts] = allLabels[i] })

  if (dp.forecast && dp.forecast.length) {
    dp.forecast.forEach((p, i) => {
      if (!(p.ts in tsToLabel)) {
        tsToLabel[p.ts] = p.ts.slice(5, 16)
      }
    })
  }

  const fcLabels = (dp.forecast && dp.forecast.length)
    ? dp.forecast.map(p => p.ts.slice(5, 16))
    : []
  const xLabels = fcLabels.length > allLabels.length ? fcLabels : allLabels

  const series = []
  series.push(...buildPriceLines(
    dp.prices.map(p => ({ ts: p.ts, retail: p.retail })),
    actionMapOf(dp.schedule_actual),
    xLabels, tsToLabel,
    { name: '实际工商电价', base: '#60a5fa', dashed: false, bandA: 0.28 }))

  if (dp.forecast && dp.forecast.length) {
    series.push(...buildPriceLines(
      dp.forecast.map(p => ({ ts: p.ts, retail: p.price_retail })),
      actionMapOf(dp.schedule_predicted),
      xLabels, tsToLabel,
      { name: '预测工商电价', base: '#f59e0b', dashed: true, bandA: 0.14 }))
  }

  const inst = echarts.getInstanceByDom(retailChart.value) || echarts.init(retailChart.value)
  inst.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(22,27,34,0.96)',
      borderColor: 'rgba(52,211,153,0.2)',
      textStyle: { color: '#e6edf3', fontSize: 12 },
      formatter: function(params) {
        if (!params || !params.length) return ''
        let html = `<div style="font-weight:600;margin-bottom:4px">${params[0].axisValue}</div>`
        for (const p of params) {
          const val = typeof p.value === 'object' ? p.value[1] : p.value
          html += `<div style="display:flex;align-items:center;gap:6px;margin:2px 0">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color}"></span>
            <span style="flex:1">${p.seriesName}</span>
            <span style="font-weight:600">${val?.toFixed(4) ?? '-'} 元/kWh</span>
          </div>`
        }
        return html
      },
    },
    legend: { show: true, bottom: 0, textStyle: { color: '#8b98a5', fontSize: 11 }, icon: 'roundRect', itemWidth: 12, itemHeight: 8 },
    grid: { ...baseGrid, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: xLabels, ...axisStyle },
    yAxis: { type: 'value', name: '元/kWh', nameTextStyle: { color: '#8b98a5', fontSize: 11 }, ...axisStyle },
    series,
  }, true)
}

function actionMapOf(schedule) {
  const m = {}
  for (const row of (schedule || [])) m[row.ts] = row.action
  return m
}

function runsOf(points, map, act) {
  const runs = []
  let cur = []
  for (const p of points) {
    if ((map[p.ts] || 'idle') === act) cur.push(p)
    else if (cur.length) { runs.push(cur); cur = [] }
  }
  if (cur.length) runs.push(cur)
  return runs
}

function buildPriceLines(points, map, labels, tsToLabel, cfg) {
  const bandColor = {
    charge: `rgba(52,211,153,${cfg.bandA})`,
    discharge: `rgba(248,113,113,${cfg.bandA})`,
  }
  const bandData = []
  for (const act of ['charge', 'discharge']) {
    let start = null, end = null
    for (const p of points) {
      const a = map[p.ts] || 'idle'
      if (a === act) { if (start === null) start = p.ts; end = p.ts }
      else if (start !== null) { bandData.push(makeBand(start, end, bandColor[act])); start = null; end = null }
    }
    if (start !== null) bandData.push(makeBand(start, end, bandColor[act]))
  }

  function makeBand(startTs, endTs, color) {
    const s = tsToLabel[startTs], e = tsToLabel[endTs]
    if (s === undefined || e === undefined) return null
    if (s !== e) return [{ xAxis: s, itemStyle: { color } }, { xAxis: e }]
    const i = labels.indexOf(s)
    if (i >= 0 && i + 1 < labels.length) {
      return [{ xAxis: s, itemStyle: { color } }, { xAxis: labels[i + 1] }]
    }
    return [{ xAxis: s, itemStyle: { color } }, { xAxis: s }]
  }

  const validBandData = bandData.filter(Boolean)

  const series = [{
    name: cfg.name, type: 'line',
    data: points.map(p => {
      const label = tsToLabel[p.ts]
      return label !== undefined ? [label, p.retail] : null
    }).filter(Boolean),
    showSymbol: false,
    lineStyle: { width: 2.5, color: cfg.base, type: cfg.dashed ? 'dashed' : 'solid' },
    itemStyle: { color: cfg.base },
    markArea: validBandData.length ? { silent: true, data: validBandData } : undefined,
  }]

  for (const act of ['charge', 'discharge']) {
    for (const run of runsOf(points, map, act)) {
      const pts = run.map(p => {
        const label = tsToLabel[p.ts]
        return label !== undefined ? [label, p.retail] : null
      }).filter(Boolean)
      if (pts.length === 0) continue
      series.push({
        name: `${cfg.name}·${act === 'charge' ? '充电' : '放电'}`, type: 'line',
        data: pts, showSymbol: pts.length === 1,
        symbol: 'circle', symbolSize: 6,
        lineStyle: { width: 3.5, color: COLOR[act], type: cfg.dashed ? 'dashed' : 'solid' },
        itemStyle: { color: COLOR[act] },
      })
    }
  }
  return series
}

function renderForecast() {
  const pts = fc.value.points
  const inst = echarts.getInstanceByDom(forecastChart.value) || echarts.init(forecastChart.value)
  inst.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(22,27,34,0.96)',
      borderColor: 'rgba(52,211,153,0.2)',
      textStyle: { color: '#e6edf3', fontSize: 12 },
    },
    legend: { bottom: 0, textStyle: { color: '#8b98a5', fontSize: 11 }, icon: 'roundRect', itemWidth: 12, itemHeight: 8 },
    grid: { ...baseGrid, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: pts.map(p => p.ts.slice(5, 16)), ...axisStyle },
    yAxis: [
      { type: 'value', name: '元/MWh', nameTextStyle: { color: '#8b98a5', fontSize: 11 }, ...axisStyle },
      { type: 'value', name: '元/kWh', nameTextStyle: { color: '#8b98a5', fontSize: 11 }, ...axisStyle },
    ],
    series: [
      { name: '预测现货价', type: 'line', data: pts.map(p => p.price_spot),
        showSymbol: false, smooth: true,
        lineStyle: { color: '#34d399', width: 2.5 }, itemStyle: { color: '#34d399' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: 'rgba(52,211,153,0.12)' }, { offset: 1, color: 'rgba(52,211,153,0.0)' }] } } },
      { name: '预测工商电价', type: 'line', yAxisIndex: 1, data: pts.map(p => p.price_retail),
        showSymbol: false, smooth: true,
        lineStyle: { color: '#60a5fa', type: 'dashed', width: 2.5 }, itemStyle: { color: '#60a5fa' } },
    ],
  }, true)
}

function renderDispatch() {
  const s = plan.value.schedule
  const inst = echarts.getInstanceByDom(dispatchChart.value) || echarts.init(dispatchChart.value)
  const touAreas = touMarkAreas(s)
  inst.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(22,27,34,0.96)',
      borderColor: 'rgba(52,211,153,0.2)',
      textStyle: { color: '#e6edf3', fontSize: 12 },
    },
    legend: { bottom: 0, textStyle: { color: '#8b98a5', fontSize: 11 }, icon: 'roundRect', itemWidth: 12, itemHeight: 8 },
    grid: { ...baseGrid, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: s.map(p => p.ts.slice(5, 16)), ...axisStyle },
    yAxis: [
      { type: 'value', name: 'kW / 元·kWh', nameTextStyle: { color: '#8b98a5', fontSize: 11 }, ...axisStyle },
      { type: 'value', name: 'SOC kWh', nameTextStyle: { color: '#8b98a5', fontSize: 11 }, ...axisStyle },
    ],
    series: [
      { name: '充电', type: 'bar', stack: 'p', data: s.map(p => p.charge_kw),
        barWidth: '60%', itemStyle: { color: '#34d399', borderRadius: [2, 2, 0, 0] } },
      { name: '放电', type: 'bar', stack: 'p', data: s.map(p => -p.discharge_kw),
        barWidth: '60%', itemStyle: { color: '#f87171', borderRadius: [0, 0, 2, 2] } },
      { name: '电价', type: 'line', data: s.map(p => p.price), showSymbol: false,
        smooth: true, lineStyle: { color: '#60a5fa', type: 'dashed', width: 2 },
        itemStyle: { color: '#60a5fa' },
        markArea: { silent: true, data: touAreas } },
      { name: 'SOC', type: 'line', yAxisIndex: 1, data: s.map(p => p.soc_kwh),
        showSymbol: false, smooth: true,
        lineStyle: { color: '#f59e0b', width: 2.5 }, itemStyle: { color: '#f59e0b' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: 'rgba(245,158,11,0.10)' }, { offset: 1, color: 'rgba(245,158,11,0.0)' }] } } },
    ],
  }, true)
}

async function runForecast() {
  running.value = true
  try {
    fc.value = await api.forecast(horizon.value, interval.value)
    await nextTick()
    renderForecast()
    plan.value = await api.dispatch(interval.value)
    await nextTick()
    renderDispatch()
    ElMessage.success('预测与调度计划已生成')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  await loadDay()
  try {
    fc.value = await api.latestForecast('24h', interval.value)
    await nextTick()
    renderForecast()
  } catch (e) { /* 尚无预测 */ }
  try {
    plan.value = await api.latestDispatch()
    await nextTick()
    renderDispatch()
  } catch (e) { /* 尚无调度计划 */ }
  window.addEventListener('resize', () => {
    ;[spotChart, retailChart, forecastChart, dispatchChart].forEach(r =>
      r.value && echarts.getInstanceByDom(r.value)?.resize())
  })
})
</script>
