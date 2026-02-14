export function secondsSince(isoTimestamp: string): number {
  const milliseconds = Date.now() - Date.parse(isoTimestamp)
  if (Number.isNaN(milliseconds) || milliseconds < 0) {
    return 0
  }
  return Math.floor(milliseconds / 1000)
}

export function formatNumber(value: number, digits = 1): string {
  return value.toFixed(digits)
}

export function toPercent(value: number | null, total: number | null): number | null {
  if (value === null || total === null || total <= 0) {
    return null
  }
  return (value / total) * 100
}
