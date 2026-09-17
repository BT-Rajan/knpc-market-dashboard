import { NewsOut } from '../types'

function sentimentColors(sentiment: string | null) {
  if (sentiment === 'up') {
    return { bg: 'rgba(106, 156, 125, 0.12)', border: 'var(--positive)' }
  }
  if (sentiment === 'down') {
    return { bg: 'rgba(194, 105, 79, 0.12)', border: 'var(--negative)' }
  }
  return { bg: 'transparent', border: 'transparent' }
}

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
          {news.map((n, i) => {
            const { bg, border } = sentimentColors(n.sentiment)
            return (
              <div
                key={i}
                style={{
                  backgroundColor: bg,
                  borderLeft: `3px solid ${border}`,
                  padding: '10px 12px',
                  marginBottom: i < news.length - 1 ? 6 : 0,
                  borderRadius: 3,
                }}
              >
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
            )
          })}
        </div>
      )}
    </div>
  )
}
