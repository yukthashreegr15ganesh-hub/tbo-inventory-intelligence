import React, { useEffect, useMemo, useState } from 'react'
import { api, inr, pct, num, shortWeek } from './api'
import { Card, Kpi, KpiRow, Pill, Loading, COLORS, tip, pnlTone } from './ui'

export default function Suppliers() {
  const [data, setData] = useState(null)
  const [filter, setFilter] = useState('')
  const [sel, setSel] = useState(null)

  useEffect(() => {
    api.suppliers(30)
      .then(setData)
      .catch((e) => console.error('Failed to load supplier intelligence:', e))
  }, [])

  const benchmarks = useMemo(() => {
    if (!data?.supplier_benchmarks) return []
    const f = filter.toLowerCase()
    return data.supplier_benchmarks.filter(
      (b) => !f || `${b.item_name} ${b.destination} ${b.recommended_supplier.supplier_name}`.toLowerCase().includes(f)
    )
  }, [data, filter])

  if (!data) return <Loading text="Evaluating supplier intelligence and contracts…" />

  return (
    <div className="stack">
      {/* Supplier Profile Archetypes */}
      <div className="problem">
        {data.supplier_profiles.map((p) => (
          <Card key={p.id} title={p.name}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span className="pill green">{p.rating} Rating</span>
              <span className="pill blue">{p.reliability} SLA Fulfillment</span>
            </div>
            <p className="muted" style={{ fontSize: '12.5px', marginBottom: '8px' }}>{p.strengths}</p>
            <div style={{ fontSize: '12px', color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: '3px' }}>
              <span>Pricing: <b>{p.pricing_advantage}</b></span>
              <span>Salvage / Refund: <b>{p.salvage}</b></span>
              <span>Min Lead Time: <b>{p.min_lead_days} days</b></span>
            </div>
          </Card>
        ))}
      </div>

      {/* Main Benchmarks Table */}
      <Card title="Supplier Comparison & Recommendation Module"
        sub="Multi-criteria procurement evaluation: unit price, allotment depth, fulfillment reliability, lead-time feasibility, and refund salvage."
        right={
          <div className="tbl-tools">
            <input placeholder="Filter hotel / route / supplier…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </div>
        }>
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th>Inventory</th>
                <th>Travel Week</th>
                <th>Recommended Supplier</th>
                <th className="r">Procurement Cost</th>
                <th className="r">Cost Diff</th>
                <th className="r">Reliability</th>
                <th className="r">Allotment</th>
                <th className="r">Salvage</th>
                <th>Selection Rationale</th>
              </tr>
            </thead>
            <tbody>
              {benchmarks.map((b) => {
                const rec = b.recommended_supplier
                return (
                  <tr key={b.cand_id} onClick={() => setSel(b)}>
                    <td>
                      <div className="nm">
                        <span className={`ic ${b.item_type}`}>{b.item_type === 'Hotel' ? 'H' : 'F'}</span>
                        <div>
                          <b>{b.item_name}</b>
                          <small>{b.destination}</small>
                        </div>
                      </div>
                    </td>
                    <td>{shortWeek(b.week)}</td>
                    <td>
                      <div>
                        <b>{rec.supplier_name.split(' (')[0]}</b>
                        <span className="pill green" style={{ marginLeft: '4px' }}>{rec.rating}</span>
                      </div>
                    </td>
                    <td className="r"><b>{inr(rec.unit_cost)}</b></td>
                    <td className={`r ${rec.cost_diff_vs_base <= 0 ? 'good' : 'bad'}`}>
                      {rec.cost_diff_pct <= 0 ? '' : '+'}{rec.cost_diff_pct}%
                    </td>
                    <td className="r"><b>{pct(rec.reliability_score, 0)}</b></td>
                    <td className="r">{num(rec.allotment_capacity)}</td>
                    <td className="r">{pct(rec.salvage_rate, 0)}</td>
                    <td style={{ maxWidth: '340px', whiteSpace: 'normal', fontSize: '12px' }}>
                      <span className="muted">{b.selection_rationale}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Detail Drawer for Selected Item's All Suppliers */}
      {sel && (
        <div className="drawer-bg" onClick={() => setSel(null)}>
          <aside className="drawer" onClick={(e) => e.stopPropagation()}>
            <button className="x" onClick={() => setSel(null)}>×</button>
            <div className="eyebrow">{sel.item_type} · {sel.destination} · week of {sel.week}</div>
            <h2>{sel.item_name}</h2>
            <p className="note" style={{ marginBottom: '16px' }}>{sel.selection_rationale}</p>
            
            <h4>All Sourced Supplier Quotes</h4>
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Supplier</th>
                    <th className="r">Cost</th>
                    <th className="r">Margin</th>
                    <th className="r">Reliability</th>
                    <th className="r">Capacity</th>
                    <th className="r">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {sel.all_suppliers.map((s) => (
                    <tr key={s.supplier_id} className={s.supplier_id === sel.recommended_supplier.supplier_id ? 'selected-row' : ''}>
                      <td>
                        <b>{s.supplier_name}</b>
                        <div><small>{s.tier} · {s.rating}</small></div>
                      </td>
                      <td className="r">{inr(s.unit_cost)}</td>
                      <td className="r good">{pct(s.gross_margin_pct)}</td>
                      <td className="r">{pct(s.reliability_score, 0)}</td>
                      <td className="r">{s.allotment_capacity}</td>
                      <td className="r"><b>{s.composite_score}</b></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}
