import { useEffect, useState } from 'react'
import { getToken } from '../../api/client'

export default function CsvExport() {
  const [tables, setTables] = useState<string[]>([])
  const [downloading, setDownloading] = useState<string | null>(null)
  const [pricesDownloading, setPricesDownloading] = useState(false)

  useEffect(() => {
    fetch('/api/admin/export/tables', { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.json())
      .then((d) => setTables(d.tables))
  }, [])

  async function downloadFile(path: string, filename: string, onDone: () => void) {
    try {
      const resp = await fetch(path, { headers: { Authorization: `Bearer ${getToken()}` } })
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      onDone()
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 480 }}>
      <div className="panel" style={{ padding: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Price export</div>
        <div style={{ fontSize: 12.5, color: 'var(--text-dim)', marginBottom: 14 }}>
          One sheet per crude benchmark and product, named and labeled by item -- daily prices for crudes, week-ending prices for products.
        </div>
        <button
          className="btn"
          onClick={() => {
            setPricesDownloading(true)
            downloadFile('/api/admin/export/prices.xlsx', 'price_export.xlsx', () => setPricesDownloading(false))
          }}
          disabled={pricesDownloading}
        >
          {pricesDownloading ? 'Downloading…' : 'Download prices (.xlsx)'}
        </button>
      </div>

      <div className="panel" style={{ padding: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>Raw table export</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {tables.map((t) => (
            <div key={t} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="mono" style={{ fontSize: 13 }}>{t}</span>
              <button
                className="btn"
                onClick={() => {
                  setDownloading(t)
                  downloadFile(`/api/admin/export/tables/${t}.csv`, `${t}.csv`, () => setDownloading(null))
                }}
                disabled={downloading === t}
              >
                {downloading === t ? 'Downloading…' : 'Download CSV'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
