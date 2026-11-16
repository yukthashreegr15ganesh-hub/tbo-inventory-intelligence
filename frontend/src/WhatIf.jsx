import React, { useEffect, useState, useRef } from 'react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell, Legend } from 'recharts'
import { api, inr, pct, num } from './api'
import { Card, Kpi, KpiRow, Pill, Loading, COLORS, tip, pnlTone, pnlFill, Pnl } from './ui'

const crore = (v) => `₹${(v / 1e7).toFixed(1)}Cr`

export default function WhatIf({ summary }) {
  const [params, setParams] = useState({
    budget: 75e7,
    demand_shock_pct: 0.0,
    supplier_cost_shock_pct: 0.0,
    cancellation_shock_pct: 0.0,
    risk_aversion: 0.30,
    max_dest_share: 0.30,
  })

  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const reqId = useRef(0)

  const runSim = () => {
    const id = ++reqId.current
    setBusy(true)
    api.simulateWhatIf(params)
      .then((data) => { if (id === reqId.current) setRes(data) })
      .catch((e) => console.error('What-If simulation error:', e))
      .finally(() => { if (id === reqId.current) setBusy(false) })
  }

  useEffect(() => {
    const t = setTimeout(runSim, res ? 300 : 0)
    return () => clearTimeout(t)
  }, [params])

  const s = res?.stats
  const sens = res?.sensitivity

  const stratChartData = res?.strategies?.map((st) => ({
    name: st.name.split(' (')[0],
    expected: st.expected_profit,
    worst: st.worst_10_profit,
    invested: st.invested,
    roi: st.roi,
  })) || []

  return (
    <div className="stack">
      <Card title="Interactive What-If Scenario Stress Testing"
        sub="Simulate macroeconomic and supplier cost shocks. Immediately observe the mathematical reallocation, profit volatility, and risk coverage across three strategies.">
        
        <div className="row2" style={{ marginBottom: '16px' }}>
          {/* Controls Column 1 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div className="ctl">
              <span className="ctl-t">Available Budget: <b>₹{Math.round(params.budget / 1e7)} Cr</b></span>
              <input type="range" min="10" max="150" step="5" value={Math.round(params.budget / 1e7)}
                onChange={(e) => setParams({ ...params, budget: +e.target.value * 1e7 })} />
              <div className="ends"><small>₹10 Cr</small><small>₹150 Cr</small></div>
            </div>

            <div className="ctl">
              <span className="ctl-t">Demand Shock: <b>{params.demand_shock_pct >= 0 ? '+' : ''}{params.demand_shock_pct}%</b>
                <Pill tone={params.demand_shock_pct >= 0 ? 'green' : 'red'}>
                  {params.demand_shock_pct > 0 ? 'Demand Surge' : params.demand_shock_pct < 0 ? 'Demand Slump' : 'Baseline'}
                </Pill>
              </span>
              <input type="range" min="-40" max="40" step="5" value={params.demand_shock_pct}
                onChange={(e) => setParams({ ...params, demand_shock_pct: +e.target.value })} />
              <div className="ends"><small>-40% (Recession)</small><small>Baseline</small><small>+40% (Boom)</small></div>
            </div>
          </div>

          {/* Controls Column 2 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div className="ctl">
              <span className="ctl-t">Supplier Cost Shock: <b>{params.supplier_cost_shock_pct >= 0 ? '+' : ''}{params.supplier_cost_shock_pct}%</b>
                <Pill tone={params.supplier_cost_shock_pct <= 0 ? 'green' : 'amber'}>
                  {params.supplier_cost_shock_pct > 0 ? 'Supplier Inflation' : params.supplier_cost_shock_pct < 0 ? 'Procurement Discount' : 'Base Quotes'}
                </Pill>
              </span>
              <input type="range" min="-25" max="35" step="5" value={params.supplier_cost_shock_pct}
                onChange={(e) => setParams({ ...params, supplier_cost_shock_pct: +e.target.value })} />
              <div className="ends"><small>-25% (Favorable)</small><small>Baseline</small><small>+35% (Inflation)</small></div>
            </div>

            <div className="ctl">
              <span className="ctl-t">Cancellation Rate Shift: <b>{params.cancellation_shock_pct >= 0 ? '+' : ''}{params.cancellation_shock_pct}%</b>
                <Pill tone={params.cancellation_shock_pct <= 0 ? 'green' : 'red'}>
                  {params.cancellation_shock_pct > 0 ? 'Spike in Cancellations' : params.cancellation_shock_pct < 0 ? 'Sticky Bookings' : 'Normal'}
                </Pill>
              </span>
              <input type="range" min="-30" max="40" step="5" value={params.cancellation_shock_pct}
                onChange={(e) => setParams({ ...params, cancellation_shock_pct: +e.target.value })} />
              <div className="ends"><small>-30%</small><small>Baseline</small><small>+40% Surge</small></div>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button className="ghost sm" onClick={() => setParams({
            budget: 75e7, demand_shock_pct: 0.0, supplier_cost_shock_pct: 0.0, cancellation_shock_pct: 0.0, risk_aversion: 0.30, max_dest_share: 0.30
          })}>Reset to Nominal</button>
        </div>
      </Card>

      {!res ? <Loading text="Simulating scenario across 1,000 futures…" /> : <>
        <KpiRow className="four">
          <Kpi label="Capital Deployed" num={s.invested} fmt={(v) => inr(v)}
            hint={`${pct(s.budget_used, 0)} budget deployed (${inr(s.unused_budget || 0)} unallocated)`} />
          <Kpi label="Scenario Expected Profit" num={s.expected_profit} fmt={(v) => inr(v)}
            hint={`Expected ROI: ${pct(s.roi)}`} tone={pnlTone(s.expected_profit)} />
          <Kpi label="Worst-10% (CVaR10)" num={s.cvar10} fmt={(v) => inr(v)}
            hint={`Loss Probability: ${pct(s.prob_loss)}`} tone={pnlTone(s.cvar10)} />
          <Kpi label="Profit Variance vs Nominal" num={sens.profit_impact_vs_nominal} fmt={(v) => `${v >= 0 ? '+' : ''}${inr(v)}`}
            hint={`${sens.profit_impact_pct >= 0 ? '+' : ''}${sens.profit_impact_pct}% profit delta`}
            tone={pnlTone(sens.profit_impact_vs_nominal)} />
        </KpiRow>

        <div className="row2">
          {/* Strategy Benchmarks Table */}
          <Card title="Strategy Comparison Under This Scenario"
            sub="How Conservative, Balanced, and Aggressive procurement policies perform under these exact shock parameters.">
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Strategy</th>
                    <th className="r">Invested</th>
                    <th className="r">Exp. Profit</th>
                    <th className="r">Worst 10%</th>
                    <th className="r">ROI</th>
                    <th className="r">Loss Prob</th>
                  </tr>
                </thead>
                <tbody>
                  {res.strategies.map((st) => (
                    <tr key={st.name} className="nohover">
                      <td><b>{st.name}</b></td>
                      <td className="r">{inr(st.invested)}</td>
                      <td className={`r ${pnlTone(st.expected_profit)}`}>{inr(st.expected_profit)}</td>
                      <td className={`r ${pnlTone(st.worst_10_profit)}`}>{inr(st.worst_10_profit)}</td>
                      <td className={`r ${pnlTone(st.roi)}`}>{pct(st.roi)}</td>
                      <td className={`r ${st.prob_loss > 0.05 ? 'bad' : ''}`}>{pct(st.prob_loss)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="note" style={{ marginTop: '12px' }}>
              {res.scenario_summary}
            </p>
          </Card>

          {/* Strategy Bar Chart */}
          <Card title="Strategy Profit vs Downside Stress"
            sub="Solid bar = Expected profit · Muted bar = Worst-10% stress scenario average">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={stratChartData} margin={{ left: 10, right: 10, top: 10 }}>
                <CartesianGrid vertical={false} stroke={COLORS.grid} />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: COLORS.muted }} stroke={COLORS.grid} />
                <YAxis tickFormatter={crore} tick={{ fontSize: 11, fill: COLORS.muted }} stroke={COLORS.grid} />
                <Tooltip {...tip()} formatter={(v) => inr(v)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="expected" name="Expected Profit" fill={COLORS.teal} radius={[4, 4, 0, 0]}>
                  {stratChartData.map((d) => <Cell key={d.name} fill={pnlFill(d.expected)} />)}
                </Bar>
                <Bar dataKey="worst" name="Worst-10% Profit" fill={COLORS.teal} fillOpacity={0.45} radius={[4, 4, 0, 0]}>
                  {stratChartData.map((d) => <Cell key={d.name} fill={pnlFill(d.worst)} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>
      </>}
    </div>
  )
}
