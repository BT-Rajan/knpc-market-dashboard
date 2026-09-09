import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { PricePoint } from '../types'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function formatLabel(dateStr: string, labelFormat: 'date' | 'month') {
  if (labelFormat === 'month') {
    return MONTHS[parseInt(dateStr.slice(5, 7), 10) - 1] ?? dateStr.slice(5, 7)
  }
  return dateStr.slice(5)
}

export default function PriceChart({
  title,
  series,
  unit,
  labelFormat = 'date',
}: {
  title: string
  series: PricePoint[]
  unit: string
  labelFormat?: 'date' | 'month'
}) {
  const data = series.map((p) => ({ date: formatLabel(p.price_date, labelFormat), price: p.price }))
  // Thin the x-axis so a long series (a full year of weeks, a month of days) doesn't
  // render an unreadable tick for every single point.
  const tickInterval = data.length > 8 ? Math.ceil(data.length / 8) - 1 : 0

  return (
    <div className="panel" style={{ padding: '18px 18px 8px', flex: 1, minWidth: 280 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>{title}</div>
      {data.length === 0 ? (
        <div style={{ color: 'var(--text-dim)', fontSize: 13, padding: '30px 0', textAlign: 'center' }}>
          No price history yet
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
            <CartesianGrid stroke="var(--border-soft)" vertical={false} />
            <XAxis
              dataKey="date"
              interval={tickInterval}
              tick={{ fill: 'var(--text-dim)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
              axisLine={{ stroke: 'var(--border)' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: 'var(--text-dim)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
              axisLine={false}
              tickLine={false}
              domain={['auto', 'auto']}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--panel-raised)',
                border: '1px solid var(--border)',
                borderRadius: 3,
                fontSize: 12,
              }}
              labelStyle={{ color: 'var(--text-muted)' }}
              formatter={(value: number) => [`${value.toFixed(2)} ${unit}`, 'price']}
            />
            <Line type="monotone" dataKey="price" stroke="var(--brass)" strokeWidth={1.75} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
