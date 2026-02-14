type Point = {
  timestamp: number
  value: number
}

type Props = {
  title: string
  points: Point[]
}

function toPath(points: Point[], width: number, height: number): string {
  if (points.length === 0) {
    return ''
  }

  const minTs = points[0]?.timestamp ?? 0
  const maxTs = points[points.length - 1]?.timestamp ?? 0
  const tsRange = Math.max(maxTs - minTs, 1)

  let minValue = points[0]?.value ?? 0
  let maxValue = points[0]?.value ?? 0
  points.forEach((point) => {
    minValue = Math.min(minValue, point.value)
    maxValue = Math.max(maxValue, point.value)
  })
  const valueRange = Math.max(maxValue - minValue, 1)

  return points
    .map((point, index) => {
      const x = ((point.timestamp - minTs) / tsRange) * width
      const y = height - ((point.value - minValue) / valueRange) * height
      const prefix = index === 0 ? 'M' : 'L'
      return `${prefix}${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
}

export default function LineChart({ title, points }: Props) {
  const width = 480
  const height = 160
  const path = toPath(points, width, height)

  return (
    <section className="chart-card">
      <h3>{title}</h3>
      {points.length < 2 ? (
        <p>Not enough samples yet.</p>
      ) : (
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
          <path d={path} className="chart-line" />
        </svg>
      )}
    </section>
  )
}
