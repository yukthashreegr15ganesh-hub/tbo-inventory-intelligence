import React, { useEffect, useState, useRef } from 'react'
import { api, inr, pct, num, shortWeek } from './api'
import { Card, Kpi, KpiRow, Pill, Loading, COLORS, tip, pnlTone } from './ui'

export default function DataIntegration() {
  const [provenance, setProvenance] = useState(null)
  const [history, setHistory] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null)
  const [dataType, setDataType] = useState('bookings')
  const [triggerReason, setTriggerReason] = useState('Demand forecast update (+10% holiday surge)')
  const [replanning, setReplanning] = useState(false)
  const [lastReplanResult, setLastReplanResult] = useState(null)
  const fileInputRef = useRef(null)

  const reloadData = () => {
    api.dataStatus().then(setProvenance).catch(console.error)
    api.replanHistory().then(setHistory).catch(console.error)
  }

  useEffect(() => { reloadData() }, [])

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadMsg(null)
    const formData = new FormData()
    formData.append('file', file)
    formData.append('data_type', dataType)

    try {
      const res = await api.uploadData(formData)
      setUploadMsg({ tone: 'good', text: `Success: ${res.validation_message} (${res.duplicates_removed} duplicates removed).` })
      reloadData()
    } catch (err) {
      setUploadMsg({ tone: 'bad', text: `Upload Error: ${err.message}` })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const triggerReplan = async () => {
    setReplanning(true)
    try {
      const res = await api.replan({
        trigger_reason: triggerReason,
        budget: 75e7,
        risk_aversion: 0.30,
        max_dest_share: 0.30,
        auto_approve: false,
      })
      setLastReplanResult(res.replan_audit)
      reloadData()
    } catch (err) {
      console.error('Replan trigger failed:', err)
    } finally {
      setReplanning(false)
    }
  }

  const handleApproval = async (replanId, action) => {
    try {
      await api.replanApprove({ replan_id: replanId, action, approver: 'Procurement_Manager' })
      reloadData()
      if (lastReplanResult?.replan_id === replanId) {
        setLastReplanResult({ ...lastReplanResult, status: action === 'APPROVE' ? 'APPROVED' : 'REJECTED' })
      }
    } catch (err) {
      console.error('Approval failed:', err)
    }
  }

  if (!provenance) return <Loading text="Checking data streams and audit logs…" />

  return (
    <div className="stack">
      {/* Provenance & Freshness Banner */}
      <Card title="Data Provenance & Pipeline Health"
        sub="Transparent tracking of data origins, pipeline freshness, and record volume. Never displays fabricated real-time TBO connectivity.">
        <KpiRow className="four">
          <Kpi label="Data Source" value={provenance.source_mode === 'synthetic_benchmark' ? 'Synthetic Benchmark' : 'User Upload'}
            hint={provenance.dataset_name} tone="good" />
          <Kpi label="Pipeline Freshness" value={provenance.last_updated?.split(' ')[0]}
            hint={`Last sync: ${provenance.last_updated}`} />
          <Kpi label="Historical Records" num={provenance.total_records.daily_bookings} fmt={num}
            hint="Daily item-level demand observations" />
          <Kpi label="Supplier Quotes" num={provenance.total_records.supplier_quotes} fmt={num}
            hint="Lead-time quotes across 10 destinations" />
        </KpiRow>
        <p className="note">{provenance.description}</p>
      </Card>

      <div className="row2">
        {/* CSV & Excel Ingestion Panel */}
        <Card title="Data Ingestion Layer (CSV / Excel)"
          sub="Upload external supplier quotes, booking updates, or inventory masters with instant schema validation and deduplication.">
          <div className="ctl">
            <label className="ctl-t" htmlFor="data-type-select">Target Dataset Schema</label>
            <select id="data-type-select" value={dataType} onChange={(e) => setDataType(e.target.value)}>
              <option value="bookings">Bookings & Search Logs (daily.csv)</option>
              <option value="quotes">Supplier Pre-Buy Rate Quotes (rate_quotes.csv)</option>
              <option value="items">Inventory Master Records (items.csv)</option>
            </select>
          </div>

          <div style={{ marginTop: '12px' }}>
            <input type="file" ref={fileInputRef} accept=".csv, .xlsx, .xls" onChange={handleFileUpload} disabled={uploading} style={{ display: 'none' }} id="file-uploader" />
            <label htmlFor="file-uploader" className="ghost" style={{ display: 'inline-block', cursor: 'pointer', textAlign: 'center', width: '100%', padding: '16px', borderStyle: 'dashed' }}>
              {uploading ? 'Validating and ingesting…' : '📁 Click to upload CSV or Excel (.xlsx) file'}
            </label>
          </div>

          {uploadMsg && (
            <div style={{ marginTop: '12px' }} className={uploadMsg.tone === 'good' ? 'txt-good' : 'txt-bad'}>
              {uploadMsg.text}
            </div>
          )}
        </Card>

        {/* Automated Replanning Trigger Panel */}
        <Card title="Automated Inventory Replanning Engine"
          sub="Recalculate recommended buy plans when demand shifts, supplier prices fluctuate, or cancellation trends deviate.">
          <div className="ctl">
            <label className="ctl-t" htmlFor="replan-trigger-select">Operational Trigger Event</label>
            <select id="replan-trigger-select" value={triggerReason} onChange={(e) => setTriggerReason(e.target.value)}>
              <option value="Demand forecast update (+10% holiday surge)">Demand Forecast Shift (+10% holiday surge)</option>
              <option value="Supplier rate revision (Late procurement pricing alert)">Supplier Rate Revision (Spot price increase)</option>
              <option value="Cancellation pattern deviation (Higher leisure churn)">Cancellation Surge Alert (Over 25% churn)</option>
              <option value="Budget reallocation review">Executive Budget Adjustment</option>
            </select>
          </div>

          <button className="run" onClick={triggerReplan} disabled={replanning} style={{ marginTop: '10px' }}>
            {replanning ? 'Recalculating optimization deltas…' : '⚡ Execute Dynamic Re-Plan'}
          </button>
        </Card>
      </div>

      {/* Replan Delta & Approval Queue */}
      {lastReplanResult && (
        <Card title={`Replanning Run: ${lastReplanResult.replan_id}`}
          sub={`Trigger: ${lastReplanResult.trigger_reason} · Status: ${lastReplanResult.status}`}
          right={
            lastReplanResult.status === 'PENDING_APPROVAL' && (
              <div style={{ display: 'flex', gap: '8px' }}>
                <button className="run sm" onClick={() => handleApproval(lastReplanResult.replan_id, 'APPROVE')}>Approve Replan</button>
                <button className="ghost sm" onClick={() => handleApproval(lastReplanResult.replan_id, 'REJECT')}>Reject</button>
              </div>
            )
          }>
          <KpiRow className="three">
            <Kpi label="Positions Affected" num={lastReplanResult.delta.total_positions_affected} fmt={num}
              hint={`Net direction: ${lastReplanResult.delta.net_direction}`} />
            <Kpi label="Net Capital Delta" num={lastReplanResult.delta.total_investment_delta} fmt={(v) => `${v >= 0 ? '+' : ''}${inr(v)}`}
              tone={pnlTone(lastReplanResult.delta.total_investment_delta)} />
            <Kpi label="Net Profit Impact" num={lastReplanResult.delta.total_profit_delta} fmt={(v) => `${v >= 0 ? '+' : ''}${inr(v)}`}
              tone={pnlTone(lastReplanResult.delta.total_profit_delta)} />
          </KpiRow>

          <h4 className="mini-h">Position Changes (Top Reallocations)</h4>
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Inventory</th>
                  <th>Week</th>
                  <th className="r">Old Units</th>
                  <th className="r">New Units</th>
                  <th className="r">Unit Delta</th>
                  <th className="r">Capital Impact</th>
                  <th className="r">Exp. Profit Delta</th>
                </tr>
              </thead>
              <tbody>
                {lastReplanResult.delta.changes.slice(0, 10).map((c) => (
                  <tr key={c.cand_id} className="nohover">
                    <td><span className={`pill ${c.tag_tone}`}>{c.action.replace('_', ' ')}</span></td>
                    <td><b>{c.name}</b> <small>({c.destination})</small></td>
                    <td>{shortWeek(c.week)}</td>
                    <td className="r">{num(c.old_units)}</td>
                    <td className="r"><b>{num(c.new_units)}</b></td>
                    <td className={`r ${c.units_delta >= 0 ? 'good' : 'bad'}`}>{c.units_delta >= 0 ? '+' : ''}{num(c.units_delta)}</td>
                    <td className="r">{inr(c.investment_delta)}</td>
                    <td className={`r ${pnlTone(c.expected_profit_delta)}`}>{inr(c.expected_profit_delta)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Audit History Log */}
      <Card title="Replanning & Approval Audit Log"
        sub="Persistent governance audit log tracking every automated and manual replanning action, capital variance, and sign-offs.">
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th>Replan ID</th>
                <th>Timestamp</th>
                <th>Trigger Event</th>
                <th>Status</th>
                <th className="r">Budget</th>
                <th className="r">Positions Changed</th>
                <th className="r">Capital Delta</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr className="nohover"><td colSpan={8} style={{ textAlign: 'center', padding: '24px', color: 'var(--muted)' }}>No replanning runs logged yet. Execute a re-plan above.</td></tr>
              ) : (
                history.map((h) => (
                  <tr key={h.replan_id} className="nohover">
                    <td><b>{h.replan_id}</b></td>
                    <td><small>{h.timestamp}</small></td>
                    <td>{h.trigger_reason}</td>
                    <td>
                      <span className={`pill ${h.status === 'APPROVED' || h.status === 'APPROVED_AUTOMATIC' ? 'green' : h.status === 'REJECTED' ? 'red' : 'amber'}`}>
                        {h.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="r">{inr(h.budget, 0)}</td>
                    <td className="r">{h.delta?.total_positions_affected || 0}</td>
                    <td className="r">{inr(h.delta?.total_investment_delta || 0)}</td>
                    <td style={{ fontSize: '12px', color: 'var(--muted)' }}>{h.notes}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
