// Spread total route miles across days in proportion to driving minutes (from plan legs).
// Date keys use en-CA (YYYY-MM-DD) so they sort lexicographically and match backend dates.

export function computeDrivingMilesByDate(legs, distanceMiles, timezone) {
  const minutesByDate = {}
  if (!Array.isArray(legs) || distanceMiles == null || Number(distanceMiles) <= 0) {
    return {}
  }
  const tz = (timezone || 'America/Chicago').trim() || 'America/Chicago'

  for (const leg of legs) {
    if (leg?.type !== 'driving') continue
    let ms = +new Date(leg.start)
    const endMs = +new Date(leg.end)
    if (!Number.isFinite(ms) || !Number.isFinite(endMs) || !(ms < endMs)) continue

    while (ms + 60000 <= endMs) {
      const key = new Date(ms).toLocaleDateString('en-CA', { timeZone: tz })
      minutesByDate[key] = (minutesByDate[key] || 0) + 1
      ms += 60000
    }
    if (ms < endMs) {
      const key = new Date(ms).toLocaleDateString('en-CA', { timeZone: tz })
      minutesByDate[key] = (minutesByDate[key] || 0) + (endMs - ms) / 60000
    }
  }

  const totalMin = Object.values(minutesByDate).reduce((a, b) => a + b, 0)
  if (totalMin <= 0) return {}

  const mph = Number(distanceMiles) / (totalMin / 60)
  const milesByDate = {}
  for (const [d, min] of Object.entries(minutesByDate)) {
    milesByDate[d] = Math.round((min / 60) * mph * 10) / 10
  }
  return milesByDate
}
