import { engine } from './engine'

// Static website build (npm run build:site) runs everything in the browser; otherwise talk to FastAPI.
export const STATIC = import.meta.env.VITE_STATIC === '1'
export const DEFAULT_SETTINGS = {
  budget: 75e7,
  risk_aversion: 0.3,
  max_dest_share: 0.3,
  item_types: ['Hotel', 'Flight'],
  destinations: null,
}

const j = async (r) => {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

const staticApi = {
  summary: () => engine.summary(),
  items: () => engine.items(),
  opportunities: (limit = 15) => engine.opportunities(limit),
  forecast: (id) => engine.forecast(id),
  post: (path, body) =>
    ({
      optimize: engine.optimize,
      frontier: engine.frontier,
      'budget-curve': engine.budgetCurve,
      explain: engine.explain,
    })[path](body),
  suppliers: () => Promise.resolve({ supplier_benchmarks: [], supplier_profiles: [] }),
  simulateWhatIf: () => Promise.resolve({ stats: {}, strategies: [] }),
  replan: () => Promise.resolve({ replan_audit: {}, current_plan: {} }),
  replanHistory: () => Promise.resolve([]),
  replanApprove: () => Promise.resolve({ success: true }),
  pricingRecommendations: () => Promise.resolve({ pricing_curve: [] }),
  cancellationRisk: () => Promise.resolve({ cancellation_probability: 0.15 }),
  dataStatus: () => Promise.resolve({ source_mode: 'synthetic_benchmark' }),
  evaluationMetrics: () => Promise.resolve({ daily: {}, weekly: {}, monthly: {} }),
  uploadData: () => Promise.resolve({ success: true }),
}

const serverApi = {
  summary: () => fetch('/api/summary').then(j),
  items: () => fetch('/api/items').then(j),
  opportunities: (limit = 15) => fetch(`/api/opportunities?limit=${limit}`).then(j),
  forecast: (id) => fetch(`/api/forecast/${id}`).then(j),
  post: (path, body) =>
    fetch(`/api/${path}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }).then(j),
  suppliers: (limit = 30) => fetch(`/api/suppliers?limit=${limit}`).then(j),
  simulateWhatIf: (body) =>
    fetch('/api/simulate-what-if', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }).then(j),
  replan: (body) =>
    fetch('/api/replan', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }).then(j),
  replanHistory: () => fetch('/api/replan/history').then(j),
  replanApprove: (body) =>
    fetch('/api/replan/approve', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }).then(j),
  pricingRecommendations: (body) =>
    fetch('/api/pricing-recommendations', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }).then(j),
  cancellationRisk: (body) =>
    fetch('/api/cancellation-risk', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }).then(j),
  dataStatus: () => fetch('/api/data/status').then(j),
  evaluationMetrics: () => fetch('/api/evaluation-metrics').then(j),
  uploadData: (formData) =>
    fetch('/api/data/upload', {
      method: 'POST',
      body: formData,
    }).then(j),
}

export const api = STATIC ? staticApi : serverApi

export const inr = (x, d = 2) => {
  if (x === null || x === undefined || isNaN(x)) return '–'
  const a = Math.abs(x),
    s = x < 0 ? '-' : ''
  if (a >= 1e7) return `${s}₹${(a / 1e7).toFixed(d)} Cr`
  if (a >= 1e5) return `${s}₹${(a / 1e5).toFixed(1)} L`
  return `${s}₹${Math.round(a).toLocaleString('en-IN')}`
}
export const pct = (x, d = 1) => (x === null || x === undefined || isNaN(x) ? '–' : `${(x * 100).toFixed(d)}%`)
export const num = (x) => (x === null || x === undefined || isNaN(x) ? '–' : Math.round(x).toLocaleString('en-IN'))
export const shortWeek = (w) => (w ? new Date(w + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '–')
