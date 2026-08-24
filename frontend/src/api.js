const BASE = ''

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  })
  if (!res.ok) {
    let msg = res.statusText
    try { msg = (await res.json()).detail || msg } catch (e) { /* ignore */ }
    throw new Error(msg)
  }
  return res.json()
}

export const api = {
  prices: (day, interval = 60) =>
    request(`/api/prices?interval_min=${interval}` + (day ? `&day=${day}` : '')),
  forecast: (horizon = '24h', interval = 60) =>
    request('/api/forecast', { method: 'POST', body: { horizon, interval_min: interval } }),
  latestForecast: (horizon = '24h', interval = 60) =>
    request(`/api/forecast/latest?horizon=${horizon}&interval_min=${interval}`),
  dispatch: (interval = 60, forecastId = null) =>
    request('/api/dispatch', { method: 'POST', body: { interval_min: interval, forecast_id: forecastId } }),
  latestDispatch: () => request('/api/dispatch/latest'),
  dispatchForDate: (day, interval = 60) =>
    request(`/api/dispatch/for-date?day=${day}&interval_min=${interval}`),
  backtest: (start, end, interval = 60) =>
    request('/api/backtest', { method: 'POST', body: { start_date: start, end_date: end, interval_min: interval } }),
  latestBacktest: () => request('/api/backtest/latest'),
  params: () => request('/api/params'),
  saveParams: (patch) => request('/api/params', { method: 'PUT', body: patch }),
  syncAll: () => request('/api/sync', { method: 'POST' }),
  tou: () => request('/api/tou'),
}
