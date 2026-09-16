import { NewsOut } from '../types'

function SentimentArrow({ sentiment }: { sentiment: string | null }) {
  if (sentiment === 'up') {
    return (
      <span
        className="mono"
        style={{ color: 'var(--positive)', fontSize: 13 }}
        title="Likely to push prices up"
      >
        ▲
      </span>
    )
  }
  if (sentiment === 'down') {
    return (
      <span
        className="mono"
        style={{ color: 'var(--negative)', fontSize: 13 }}
        title="Likely to push prices down"
      >
        ▼
      </span>
    )
  }
  return null
}

export default function NewsList({ news, title = 'News' }: { news: NewsOut[]; title?: string }) {
  return (
    <div className="panel" style={{ padding: 20 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>{title}</div>
      {news.length === 0 ? (
        <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>No headlines collected yet.</div>
      ) : (
        <div>
          {news.map((n, i) => (
            <div key={i}>
              {i > 0 && <hr className="hairline" style={{ margin: '12px 0' }} />}
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <SentimentArrow sentiment={n.sentiment} />
                  <a href={n.url ?? undefined} target="_blank" rel="noreferrer" style={{ fontSize: 14, color: 'var(--text)' }}>
                    {n.headline}
                  </a>
                </span>
                <span className="mono" style={{ fontSize: 11, color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
                  {n.source}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
