import { describe, expect, it } from 'vitest'
import { secondsSince, toPercent } from './utils'

describe('secondsSince', () => {
  it('returns non-negative seconds', () => {
    const nowIso = new Date().toISOString()
    expect(secondsSince(nowIso)).toBeGreaterThanOrEqual(0)
  })
})

describe('toPercent', () => {
  it('converts value over total to percent', () => {
    expect(toPercent(2, 8)).toBe(25)
  })

  it('returns null when total missing', () => {
    expect(toPercent(2, null)).toBeNull()
  })
})
