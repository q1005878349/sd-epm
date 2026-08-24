// 分时电价配色与图表公共工具
export const TOU_COLORS = {
  deep_valley: 'rgba(96,165,250,0.14)',
  valley: 'rgba(52,211,153,0.12)',
  flat: 'rgba(139,152,165,0.06)',
  peak: 'rgba(245,158,11,0.10)',
  sharp: 'rgba(248,113,113,0.14)',
}
export const TOU_LABEL_COLORS = {
  deep_valley: '#60a5fa', valley: '#34d399', flat: '#8b98a5',
  peak: '#f59e0b', sharp: '#f87171',
}

// 根据价格点的 tou 字段生成背景色带（markArea）。
// 注意：xAxis 值必须与图表分类轴标签一致（各视图统一用 ts.slice(5,16)），
// 否则 ECharts 找不到对应分类会抛 "Cannot read properties of null (reading 'getAttribute')"。
const _label = ts => ts.slice(5, 16)

export function touMarkAreas(points) {
  if (!points || !points.length) return []
  const areas = []
  let start = _label(points[0].ts), cur = points[0].tou
  for (let i = 1; i <= points.length; i++) {
    const p = points[i]
    if (!p || p.tou !== cur) {
      areas.push([{ xAxis: start, itemStyle: { color: TOU_COLORS[cur] } },
                  { xAxis: p ? _label(p.ts) : _label(points[i - 1].ts) }])
      if (p) { start = _label(p.ts); cur = p.tou }
    }
  }
  return areas
}

export const baseGrid = { left: 60, right: 60, top: 40, bottom: 40 }
export const axisStyle = {
  axisLine: { lineStyle: { color: '#2b333d' } },
  axisLabel: { color: '#8b98a5' },
  splitLine: { lineStyle: { color: 'rgba(43,51,61,0.5)' } },
}
