import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { ScrapeSettingOut, ScrapeStatusOut, ItemLastUpdateOut } from '../../types'

function formatTimestamp(iso: string | null): string {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleString()
}

function StatusTable({ status, loading }: { status: ScrapeStatusOut | null; loading: boolean }) {
  const grouped: Record<string, ItemLastUpdateOut[]> = {}
  for (const item of status?.items ?? []) {
    grouped[item.category] = grouped[item.category] ?? []
    grouped[item.category].push(item)
  }

  return (
    <div className="panel" style={{ padding: 20 }}>
      <div className="eyebrow" style={{ marginBottom: 12 }}>
        Update status {loading && '(loading...)'}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th style={{ padding: 8, textAlign: 'left' }}>Category</th>
              <th style={{ padding: 8, textAlign: 'left' }}>Item</th>
              <th style={{ padding: 8, textAlign: 'right' }}>Last updated</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(grouped).map(([category, items]) =>
              items.map((item, i) => (
                <tr key={item.code} style={{ borderBottom: '1px solid var(--border-dim)' }}>
                  <td style={{ padding: 8, color: 'var(--text-dim)' }}>{i === 0 ? category : ''}</td>
                  <td style={{ padding: 8 }}>{item.name}</td>
                  <td style={{ padding: 8, textAlign: 'right' }} className="mono">
                    {formatTimestamp(item.last_update)}
                  </td>
                </tr>
              ))
            )}
            <tr style={{ borderTop: '2px solid var(--border)' }}>
              <td style={{ padding: 8, color: 'var(--text-dim)' }}>News</td>
              <td style={{ padding: 8 }}>Market News feed</td>
              <td style={{ padding: 8, textAlign: 'right' }} className="mono">
                {formatTimestamp(status?.news_last_update ?? null)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function ScrapeSettings() {
  const [frequency, setFrequency] = useState(30)
  const [saved, setSaved] = useState(true)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [status, setStatus] = useState<ScrapeStatusOut | null>(null)
  const [statusLoading, setStatusLoading] = useState(true)

  const loadStatus = () => {
    setStatusLoading(true)
    api
      .get<ScrapeStatusOut>('/api/admin/scrape/status')
      .then(setStatus)
      .finally(() => setStatusLoading(false))
  }

  useEffect(() => {
    api.get<ScrapeSettingOut>('/api/admin/scrape/settings').then((s) => setFrequency(s.frequency_minutes))
    loadStatus()
  }, [])

  async function save() {
    await api.put('/api/admin/scrape/settings', { frequency_minutes: frequency })
    setSaved(true)
  }

  async function runAll() {
    setRunning(true)
    setResult(null)
    try {
      const res = await api.post<{ results: Record<string, boolean> }>('/api/admin/scrape/run')
      const ok = Object.values(res.results).filter(Boolean).length
      const total = Object.values(res.results).length
      setResult(`${ok}/${total} items scraped successfully. See Logs for details.`)
      loadStatus()
    } finally {
      setRunning(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 640 }}>
      <div className="panel" style={{ padding: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>Scrape frequency</div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
          <div className="field" style={{ flex: 1 }}>
            <label>Minutes between runs</label>
            <input
              type="number"
              min={1}
              value={frequency}
              onChange={(e) => {
                setFrequency(Number(e.target.value))
                setSaved(false)
              }}
            />
          </div>
          <button className="btn btn-brass" onClick={save} disabled={saved}>
            {saved ? 'Saved' : 'Save'}
          </button>
        </div>
      </div>

      <div className="panel" style={{ padding: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>Manual run</div>
        <button className="btn btn-brass" onClick={runAll} disabled={running}>
          {running ? 'Running…' : 'Scrape all items now'}
        </button>
        {result && <div style={{ marginTop: 12, fontSize: 13, color: 'var(--text-muted)' }}>{result}</div>}
      </div>

      <StatusTable status={status} loading={statusLoading} />
    </div>
  )
}
