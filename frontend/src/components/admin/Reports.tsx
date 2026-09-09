import { useEffect, useState } from 'react'
import { api, getToken } from '../../api/client'

interface Stat {
  name: string
  open: number
  close: number
  high: number
  low: number
  avg: number
  change: number
  change_pct: number
  readings: number
}

interface ReportFile {
  filename: string
  size: number
  created: string
}

type Mode = 'data_only' | 'ai_enhanced'

const MODES: { value: Mode; label: string; hint: string }[] = [
  { value: 'data_only', label: 'Data only', hint: 'Tables and charts computed straight from tracked prices. No AI calls.' },
  { value: 'ai_enhanced', label: 'AI-enhanced', hint: 'Adds narrative, drivers, and outlook synthesized from this system’s collected news feed.' },
]

const QUARTERS = ['Q1', 'Q2', 'Q3', 'Q4'] as const
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const inputStyle = { width: '100%', padding: '8px', border: '1px solid var(--border)', borderRadius: 4 }

function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label className="form-label">Report style</label>
      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        {MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            onClick={() => onChange(m.value)}
            className={mode === m.value ? 'btn btn-brass' : 'btn'}
            style={{ flex: 1, padding: '8px 10px', fontSize: 13 }}
          >
            {m.label}
          </button>
        ))}
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--text-dim)', marginTop: 6 }}>
        {MODES.find((m) => m.value === mode)?.hint}
      </div>
    </div>
  )
}

function StatTable({ title, stats, loading }: { title: string; stats: Stat[]; loading: boolean }) {
  return (
    <div className="panel" style={{ padding: 16, marginBottom: 16 }}>
      <div className="eyebrow" style={{ marginBottom: 12 }}>
        {title} {loading && '(loading...)'}
      </div>
      {stats.length > 0 ? (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th style={{ padding: 8, textAlign: 'left' }}>Name</th>
                <th style={{ padding: 8, textAlign: 'right' }}>Open</th>
                <th style={{ padding: 8, textAlign: 'right' }}>Close</th>
                <th style={{ padding: 8, textAlign: 'right' }}>Change %</th>
                <th style={{ padding: 8, textAlign: 'right' }}>Readings</th>
              </tr>
            </thead>
            <tbody>
              {stats.map((s, i) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--border-dim)' }}>
                  <td style={{ padding: 8 }}>{s.name}</td>
                  <td style={{ padding: 8, textAlign: 'right' }}>{s.open.toFixed(2)}</td>
                  <td style={{ padding: 8, textAlign: 'right' }}>{s.close.toFixed(2)}</td>
                  <td style={{ padding: 8, textAlign: 'right', color: s.change_pct >= 0 ? '#22c55e' : '#ef4444' }}>
                    {s.change_pct >= 0 ? '+' : ''}{s.change_pct.toFixed(2)}%
                  </td>
                  <td style={{ padding: 8, textAlign: 'right' }}>{s.readings}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>No data available for this period.</div>
      )}
    </div>
  )
}

function QuarterlySection({ onGenerated }: { onGenerated: () => void }) {
  const [year, setYear] = useState(new Date().getFullYear())
  const [quarter, setQuarter] = useState<typeof QUARTERS[number]>('Q1')
  const [mode, setMode] = useState<Mode>('data_only')
  const [benchmarks, setBenchmarks] = useState<Stat[]>([])
  const [products, setProducts] = useState<Stat[]>([])
  const [outlookNotes, setOutlookNotes] = useState('')
  const [generatedBy, setGeneratedBy] = useState('MOG Analyst')
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .post<{ benchmarks: Stat[]; products: Stat[] }>('/api/reports/preview', { year, quarter })
      .then((data) => {
        if (cancelled) return
        setBenchmarks(data.benchmarks)
        setProducts(data.products)
      })
      .catch((err) => !cancelled && setMessage(`Error loading preview: ${err}`))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [year, quarter])

  const generateReport = async () => {
    try {
      setGenerating(true)
      setMessage('')
      const result = await api.post<{ status: string; filename: string }>('/api/reports/generate', {
        year, quarter, outlook_notes: outlookNotes, generated_by: generatedBy, mode,
      })
      if (result.status === 'success') {
        setMessage(`✓ Report generated: ${result.filename}`)
        setOutlookNotes('')
        onGenerated()
      }
    } catch (err) {
      setMessage(`Error generating report: ${err}`)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div style={{ marginBottom: 40 }}>
      <h2 style={{ fontSize: 18, marginBottom: 20 }}>Quarterly Market Reports</h2>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
        <div>
          <label className="form-label">Year</label>
          <input type="number" value={year} onChange={(e) => setYear(parseInt(e.target.value))} style={inputStyle} />
        </div>
        <div>
          <label className="form-label">Quarter</label>
          <select value={quarter} onChange={(e) => setQuarter(e.target.value as typeof QUARTERS[number])} style={inputStyle}>
            {QUARTERS.map((q) => (
              <option key={q} value={q}>{q}</option>
            ))}
          </select>
        </div>
      </div>

      <StatTable title="Preview — Benchmark Movement" stats={benchmarks} loading={loading} />
      <StatTable title="Preview — Product Movement" stats={products} loading={loading} />

      <div className="panel" style={{ padding: 16, marginBottom: 24 }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>Generate Report</div>

        <ModeToggle mode={mode} onChange={setMode} />

        <div style={{ marginBottom: 16 }}>
          <label className="form-label">Analyst Outlook & Commentary (optional)</label>
          <textarea
            value={outlookNotes}
            onChange={(e) => setOutlookNotes(e.target.value)}
            placeholder="e.g., Demand outlook for next quarter, refinery maintenance schedule impacts, key risks to monitor... Leave blank in AI-enhanced mode to get a draft built from this period's collected news."
            style={{ ...inputStyle, minHeight: 100, fontFamily: 'monospace', fontSize: 13 }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label className="form-label">Prepared By</label>
          <input type="text" value={generatedBy} onChange={(e) => setGeneratedBy(e.target.value)} style={inputStyle} />
        </div>

        <button onClick={generateReport} disabled={generating} className="btn btn-brass" style={{ width: '100%', padding: '10px', fontWeight: 500 }}>
          {generating ? 'Generating...' : 'Generate & Save Report'}
        </button>

        {message && (
          <div style={{
            marginTop: 12, padding: '8px', borderRadius: 4,
            backgroundColor: message.startsWith('✓') ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
            color: message.startsWith('✓') ? '#22c55e' : '#ef4444', fontSize: 13,
          }}>
            {message}
          </div>
        )}
      </div>
    </div>
  )
}

function MonthlySection({ onGenerated }: { onGenerated: () => void }) {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [mode, setMode] = useState<Mode>('data_only')
  const [benchmarks, setBenchmarks] = useState<Stat[]>([])
  const [products, setProducts] = useState<Stat[]>([])
  const [generatedBy, setGeneratedBy] = useState('MOG Analyst')
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .post<{ benchmarks: Stat[]; products: Stat[] }>('/api/reports/monthly/preview', { year, month })
      .then((data) => {
        if (cancelled) return
        setBenchmarks(data.benchmarks)
        setProducts(data.products)
      })
      .catch((err) => !cancelled && setMessage(`Error loading preview: ${err}`))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [year, month])

  const generateReport = async () => {
    try {
      setGenerating(true)
      setMessage('')
      const result = await api.post<{ status: string; filename: string }>('/api/reports/monthly/generate', {
        year, month, generated_by: generatedBy, mode,
      })
      if (result.status === 'success') {
        setMessage(`✓ Report generated: ${result.filename}`)
        onGenerated()
      }
    } catch (err) {
      setMessage(`Error generating report: ${err}`)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div style={{ marginBottom: 40 }}>
      <h2 style={{ fontSize: 18, marginBottom: 20 }}>Monthly Market Reports</h2>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
        <div>
          <label className="form-label">Year</label>
          <input type="number" value={year} onChange={(e) => setYear(parseInt(e.target.value))} style={inputStyle} />
        </div>
        <div>
          <label className="form-label">Month</label>
          <select value={month} onChange={(e) => setMonth(parseInt(e.target.value))} style={inputStyle}>
            {MONTHS.map((name, i) => (
              <option key={name} value={i + 1}>{name}</option>
            ))}
          </select>
        </div>
      </div>

      <StatTable title="Preview — Benchmark Movement" stats={benchmarks} loading={loading} />
      <StatTable title="Preview — Product Movement" stats={products} loading={loading} />

      <div className="panel" style={{ padding: 16, marginBottom: 24 }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>Generate Report</div>

        <ModeToggle mode={mode} onChange={setMode} />
        <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: -8, marginBottom: 16 }}>
          {mode === 'data_only'
            ? 'Produces a simple price recap for the month — tables and charts only.'
            : 'Picks this month’s single most relevant story from the collected news feed and writes a single-topic brief around it (background, key figures, analytics, implications, recommendation).'}
        </div>

        <div style={{ marginBottom: 16 }}>
          <label className="form-label">Prepared By</label>
          <input type="text" value={generatedBy} onChange={(e) => setGeneratedBy(e.target.value)} style={inputStyle} />
        </div>

        <button onClick={generateReport} disabled={generating} className="btn btn-brass" style={{ width: '100%', padding: '10px', fontWeight: 500 }}>
          {generating ? 'Generating...' : 'Generate & Save Report'}
        </button>

        {message && (
          <div style={{
            marginTop: 12, padding: '8px', borderRadius: 4,
            backgroundColor: message.startsWith('✓') ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
            color: message.startsWith('✓') ? '#22c55e' : '#ef4444', fontSize: 13,
          }}>
            {message}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Reports() {
  const [reports, setReports] = useState<ReportFile[]>([])

  const loadReports = async () => {
    try {
      const data = await api.get<{ reports: ReportFile[] }>('/api/reports/list')
      setReports(data.reports)
    } catch (err) {
      console.error('Error loading reports:', err)
    }
  }

  useEffect(() => {
    loadReports()
  }, [])

  const downloadReport = async (filename: string) => {
    try {
      const resp = await fetch(`/api/reports/download/${encodeURIComponent(filename)}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      })
      if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`)
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Error downloading report:', err)
    }
  }

  return (
    <div>
      <QuarterlySection onGenerated={loadReports} />
      <MonthlySection onGenerated={loadReports} />

      <div className="panel" style={{ padding: 16 }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>Published Reports ({reports.length})</div>
        {reports.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {reports.map((report, i) => (
              <div
                key={i}
                style={{
                  padding: '12px', border: '1px solid var(--border-dim)', borderRadius: 4,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}
              >
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 500, fontSize: 14 }}>{report.filename}</div>
                  <div style={{ color: 'var(--text-dim)', fontSize: 12, marginTop: 4 }}>
                    {new Date(report.created).toLocaleString()} • {(report.size / 1024).toFixed(0)} KB
                  </div>
                </div>
                <button onClick={() => downloadReport(report.filename)} className="btn" style={{ padding: '6px 12px', fontSize: 12 }}>
                  Download
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>No reports generated yet.</div>
        )}
      </div>
    </div>
  )
}
