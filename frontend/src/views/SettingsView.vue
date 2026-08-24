<template>
  <div class="settings-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">参数与数据</h2>
        <div class="page-sub">电池 / 电网 / 电价转换 / 预测模型参数，以及数据源同步</div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-group">
          <span class="panel-icon">🔋</span>
          <h3>电池与电网参数</h3>
        </div>
      </div>
      <el-form label-width="180px" style="max-width:560px">
        <el-form-item label="电池容量 (kWh)">
          <el-input-number v-model="p.battery_capacity_kwh" :min="50" :max="10000" :step="50" /></el-form-item>
        <el-form-item label="电池最大充电功率 (kW)">
          <el-input-number v-model="p.max_charge_power_kw" :min="10" :max="5000" :step="10" /></el-form-item>
        <el-form-item label="电池最大放电功率 (kW)">
          <el-input-number v-model="p.max_discharge_power_kw" :min="10" :max="5000" :step="10" /></el-form-item>
        <el-form-item label="电网输电功率上限 (kW)">
          <el-input-number v-model="p.grid_power_limit_kw" :min="10" :max="5000" :step="10" /></el-form-item>
        <el-form-item label="SOC 下限 / 上限">
          <el-input-number v-model="p.soc_min" :min="0" :max="0.5" :step="0.01" style="width:110px" />
          <el-input-number v-model="p.soc_max" :min="0.5" :max="1" :step="0.01" style="width:110px;margin-left:8px" /></el-form-item>
        <el-form-item label="充 / 放电效率">
          <el-input-number v-model="p.charge_efficiency" :min="0.7" :max="1" :step="0.01" style="width:110px" />
          <el-input-number v-model="p.discharge_efficiency" :min="0.7" :max="1" :step="0.01" style="width:110px;margin-left:8px" /></el-form-item>
        <el-form-item label="每日最大循环次数">
          <el-input-number v-model="p.max_daily_cycles" :min="0.5" :max="6" :step="0.5" /></el-form-item>
      </el-form>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-group">
          <span class="panel-icon">💱</span>
          <h3>工商业电价转换</h3>
        </div>
      </div>
      <el-form label-width="220px" style="max-width:620px">
        <el-form-item label="现货价乘数 (multiplier)">
          <el-input-number v-model="p.retail_multiplier" :min="0.5" :max="2" :step="0.05" /></el-form-item>
        <el-form-item label="附加项 (元/kWh，输配电价+基金等)">
          <el-input-number v-model="p.retail_adder_yuan_kwh" :min="0" :max="0.6" :step="0.005" /></el-form-item>
      </el-form>
      <div class="formula-hint">到户电价 = 现货价 ÷ 1000 × 乘数 + 附加项</div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-group">
          <span class="panel-icon">🧠</span>
          <h3>预测模型</h3>
        </div>
      </div>
      <el-form label-width="220px" style="max-width:620px">
        <el-form-item label="训练窗口（天）">
          <el-input-number v-model="p.train_days" :min="14" :max="365" :step="1" /></el-form-item>
        <el-form-item label="计价颗粒度">
          <el-radio-group v-model="p.interval_min">
            <el-radio-button :value="60">按小时（现行）</el-radio-button>
            <el-radio-button :value="15">15 分钟（后续模式）</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <el-button type="primary" :loading="saving" @click="save" round>保存参数</el-button>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-group">
          <span class="panel-icon">⏰</span>
          <h3>分时电价时段（山东工商业，近似可配置）</h3>
        </div>
      </div>
      <div class="tou-tags">
        <span v-for="seg in tou.periods" :key="seg.start" class="badge" :class="seg.type"
          style="margin-right:8px;margin-bottom:4px">{{ seg.start }}:00–{{ seg.end }}:00 {{ seg.label }}</span>
      </div>
      <div class="formula-hint">{{ tou.note }}</div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-group">
          <span class="panel-icon">📡</span>
          <h3>数据源</h3>
        </div>
      </div>
      <el-descriptions :column="1" border size="small" style="max-width:720px">
        <el-descriptions-item label="现货价格">仿真适配器（simulator）· 替换方式见 README「接入真实数据源」</el-descriptions-item>
        <el-descriptions-item label="天气">Open-Meteo 公开 API（济南）· 网络不可用时自动回退仿真</el-descriptions-item>
        <el-descriptions-item label="法定节假日">timor.tech 公开 API · 失败回退内置列表</el-descriptions-item>
      </el-descriptions>
      <el-button style="margin-top:14px" type="warning" :loading="syncing" @click="sync" round>
        重新同步全部数据（价格/天气/节假日）</el-button>
      <span v-if="syncResult" class="sync-result">{{ syncResult }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

const p = ref({})
const tou = ref({ periods: [] })
const saving = ref(false)
const syncing = ref(false)
const syncResult = ref('')

async function save() {
  saving.value = true
  try {
    await api.saveParams(p.value)
    ElMessage.success('参数已保存')
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function sync() {
  syncing.value = true
  try {
    const r = await api.syncAll()
    syncResult.value = `价格(小时) ${r.prices_60min} 条 / 价格(15分钟) ${r.prices_15min} 条 / 天气 ${r.weather} 条 / 节假日 ${r.holidays} 条`
    ElMessage.success('同步完成')
  } catch (e) { ElMessage.error(e.message) } finally { syncing.value = false }
}

onMounted(async () => {
  p.value = await api.params()
  tou.value = await api.tou()
})
</script>
