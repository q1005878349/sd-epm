<template>
  <div class="backtest-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">回测与节省</h2>
        <div class="page-sub">预测策略 vs 固定谷时策略 · 逐日滚动回测（每日仅用当日之前的数据训练）</div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-group">
          <span class="panel-icon">📊</span>
          <h3>回测控制</h3>
        </div>
        <div class="toolbar">
          <el-date-picker v-model="range" type="daterange" value-format="YYYY-MM-DD"
            range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" size="small" />
          <el-radio-group v-model="interval" size="small">
            <el-radio-button :value="60">按小时</el-radio-button>
            <el-radio-button :value="15">15 分钟</el-radio-button>
          </el-radio-group>
          <el-button type="primary" :loading="running" @click="run" size="small" round>运行回测</el-button>
          <span class="backtest-note">回测每日重训模型，区间较长时请耐心等待</span>
        </div>
      </div>

      <div v-if="bt" class="cards">
        <div class="card">
          <div class="card-icon-wrap green"><span class="card-icon">📅</span></div>
          <div class="label">日均节省</div>
          <div class="value green">{{ money(bt.summary.avg_daily_saving) }}<small> 元/天</small></div>
        </div>
        <div class="card">
          <div class="card-icon-wrap green"><span class="card-icon">📆</span></div>
          <div class="label">周均节省</div>
          <div class="value green">{{ money(bt.summary.avg_weekly_saving) }}<small> 元/周</small></div>
        </div>
        <div class="card">
          <div class="card-icon-wrap green"><span class="card-icon">🗓️</span></div>
          <div class="label">月均节省</div>
          <div class="value green">{{ money(bt.summary.avg_monthly_saving) }}<small> 元/月</small></div>
        </div>
        <div class="card">
          <div class="card-icon-wrap amber"><span class="card-icon">📈</span></div>
          <div class="label">年化节省（估算）</div>
          <div class="value amber">{{ money(bt.summary.projected_yearly_saving) }}<small> 元/年</small></div>
          <div class="extra">相比固定谷时提升 {{ bt.summary.saving_pct }}%</div>
        </div>
        <div class="card">
          <div class="card-icon-wrap blue"><span class="card-icon">💰</span></div>
          <div class="label">区间累计（{{ bt.days }} 天）</div>
          <div class="value blue">{{ money(bt.summary.total_saving) }}<small> 元</small></div>
          <div class="extra">模型 {{ money(bt.summary.total_model_revenue) }} / 基线 {{ money(bt.summary.total_baseline_revenue) }}</div>
        </div>
      </div>
      <div class="backtest-note" v-if="bt">{{ bt.note }}</div>
      <div ref="chart" class="chart tall" v-show="bt"></div>
    </div>

    <div class="panel" v-if="bt">
      <div class="panel-header">
        <div class="panel-title-group">
          <span class="panel-icon">📋</span>
          <h3>月度 / 周度节省汇总</h3>
        </div>
      </div>
      <div style="display:flex;gap:24px;flex-wrap:wrap">
        <el-table :data="bt.monthly" size="small" style="flex:1;min-width:260px">
          <el-table-column prop="month" label="月份" />
          <el-table-column label="节省（元）">
            <template #default="{ row }"><span class="saving-cell">{{ money(row.saving) }}</span></template>
          </el-table-column>
        </el-table>
        <el-table :data="bt.weekly" size="small" style="flex:1;min-width:260px" height="260">
          <el-table-column prop="week" label="周" />
          <el-table-column label="节省（元）">
            <template #default="{ row }"><span class="saving-cell">{{ money(row.saving) }}</span></template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div class="panel" v-if="bt">
      <div class="panel-header">
        <div class="panel-title-group">
          <span class="panel-icon">🔍</span>
          <h3>单日调度回放（预测策略 · 含谷峰符合性）</h3>
        </div>
        <div class="toolbar">
          <el-select v-model="selectedDay" placeholder="选择日期" style="width:180px" @change="renderDay" size="small">
            <el-option v-for="d in bt.daily" :key="d.date" :label="d.date" :value="d.date" />
          </el-select>
        </div>
      </div>
      <div ref="dayChart" class="chart tall" v-show="selectedDay"></div>
      <el-table v-if="selectedDayData" :data="selectedDayData.schedule_model.filter(s => s.action !== 'idle')"
        height="280" size="small" style="margin-top:12px">
        <el-table-column prop="ts" label="时段" width="170" />
        <el-table-column label="动作" width="80">
          <template #default="{ row }">
            <span :class="['action-tag', row.action]">
              {{ row.action === 'charge' ? '⚡ 充电' : '🔌 放电' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="功率 kW" width="100">
          <template #default="{ row }">{{ row.charge_kw || row.discharge_kw }}</template>
        </el-table-column>
        <el-table-column label="分时类型" width="90">
          <template #default="{ row }"><span class="badge" :class="row.tou">{{ row.tou_label }}</span></template>
        </el-table-column>
        <el-table-column label="符合性">
          <template #default="{ row }">
            <span class="badge" :class="row.tou_match">
              {{ { good: '✓ 符合', neutral: '— 平段', bad: '✗ 偏离' }[row.tou_match] }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { touMarkAreas, baseGrid, axisStyle } from '../chartUtils'

const range = ref(null)
const interval = ref(60)
const running = ref(false)
const bt = ref(null)
const chart = ref(null)
const dayChart = ref(null)
const selectedDay = ref(null)
const money = v => v === null || v === undefined ? '-' : Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 2 })

const selectedDayData = computed(() =>
  bt.value?.daily.find(d => d.date === selectedDay.value) || null)

async function run() {
  if (!range.value || !range.value[0]) { ElMessage.warning('请选择回测区间'); return }
  running.value = true
  try {
    bt.value = await api.backtest(range.value[0], range.value[1], interval.value)
    selectedDay.value = bt.value.daily[0]?.date
    await nextTick()
    render()
    renderDay()
    ElMessage.success('回测完成')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
  }
}

function render() {
  const daily = bt.value.daily
  const inst = echarts.getInstanceByDom(chart.value) || echarts.init(chart.value)
  inst.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(22,27,34,0.96)',
      borderColor: 'rgba(52,211,153,0.2)',
      textStyle: { color: '#e6edf3', fontSize: 12 },
    },
    legend: { bottom: 0, textStyle: { color: '#8b98a5', fontSize: 11 }, icon: 'roundRect', itemWidth: 12, itemHeight: 8 },
    grid: { ...baseGrid, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: daily.map(d => d.date.slice(5)), ...axisStyle },
    yAxis: { type: 'value', name: '元', nameTextStyle: { color: '#8b98a5', fontSize: 11 }, ...axisStyle },
    series: [
      { name: '预测策略收益', type: 'bar', data: daily.map(d => d.model_revenue),
        barWidth: '50%', itemStyle: { color: '#34d399', borderRadius: [3, 3, 0, 0] } },
      { name: '固定谷时收益', type: 'bar', data: daily.map(d => d.baseline_revenue),
        barWidth: '50%', itemStyle: { color: '#8b98a5', borderRadius: [3, 3, 0, 0] } },
      { name: '日节省', type: 'line', data: daily.map(d => d.saving),
        smooth: true, symbol: 'circle', symbolSize: 4,
        lineStyle: { color: '#f59e0b', width: 2.5 }, itemStyle: { color: '#f59e0b' } },
    ],
  }, true)
}

async function renderDay() {
  const d = selectedDayData.value
  if (!d) return
  await nextTick()
  const s = d.schedule_model
  const touAreas = touMarkAreas(s)
  const inst = echarts.getInstanceByDom(dayChart.value) || echarts.init(dayChart.value)
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
      { type: 'value', name: 'kW', nameTextStyle: { color: '#8b98a5', fontSize: 11 }, ...axisStyle },
      { type: 'value', name: 'SOC kWh', nameTextStyle: { color: '#8b98a5', fontSize: 11 }, ...axisStyle },
    ],
    series: [
      { name: '充电', type: 'bar', stack: 'p', data: s.map(p => p.charge_kw),
        barWidth: '60%', itemStyle: { color: '#34d399', borderRadius: [2, 2, 0, 0] } },
      { name: '放电', type: 'bar', stack: 'p', data: s.map(p => -p.discharge_kw),
        barWidth: '60%', itemStyle: { color: '#f87171', borderRadius: [0, 0, 2, 2] } },
      { name: 'SOC', type: 'line', yAxisIndex: 1, data: s.map(p => p.soc_kwh),
        showSymbol: false, smooth: true,
        lineStyle: { color: '#f59e0b', width: 2.5 }, itemStyle: { color: '#f59e0b' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: 'rgba(245,158,11,0.10)' }, { offset: 1, color: 'rgba(245,158,11,0.0)' }] } },
        markArea: { silent: true, data: touAreas } },
    ],
  }, true)
}

onMounted(async () => {
  try {
    bt.value = await api.latestBacktest()
    selectedDay.value = bt.value.daily[0]?.date
    await nextTick()
    render()
    renderDay()
  } catch (e) { /* 尚无回测 */ }
})
</script>
