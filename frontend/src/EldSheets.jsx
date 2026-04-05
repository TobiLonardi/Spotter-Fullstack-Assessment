// Same vertical order as a paper log: off → sleeper → drive → on.
const ROWS = [
  { key: 'OFF', label: 'Off duty' },
  { key: 'SB', label: 'Sleeper berth' },
  { key: 'D', label: 'Driving' },
  { key: 'ON', label: 'On duty (not driving)' },
]

function formatClock(mins) {
  const h = Math.floor(mins / 60) % 24
  const m = mins % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

function SegmentBar({ seg }) {
  const left = (seg.start_minute / (24 * 60)) * 100
  const width = ((seg.end_minute - seg.start_minute) / (24 * 60)) * 100
  return (
    <div
      className="eld-bar"
      style={{ left: `${left}%`, width: `${Math.max(width, 0.2)}%` }}
      title={`${formatClock(seg.start_minute)}–${formatClock(seg.end_minute)} ${seg.label || ''}`}
    />
  )
}

function DayGrid({ day, drivingMiles }) {
  const byStatus = { OFF: [], SB: [], D: [], ON: [] }
  for (const seg of day.segments || []) {
    if (byStatus[seg.status]) byStatus[seg.status].push(seg)
  }

  const hours = Array.from({ length: 24 }, (_, i) => i)

  return (
    <section className="eld-sheet">
      <header className="eld-sheet-head">
        <h3>Daily log — {day.date}</h3>
        <p className="eld-hint">
          {drivingMiles != null ? (
            <>
              <span className="eld-driving-miles">
                Driving (est.): <strong>{drivingMiles} mi</strong>
              </span>
              {' · '}
            </>
          ) : null}
          15-minute grid. Rest ≥7h shown as sleeper berth;
          10-hour daily resets as 7h SB + 3h off duty.
        </p>
      </header>
      <div className="eld-hour-labels">
        {hours.map((h) => (
          <span key={h} className="eld-hour-tick">
            {h}
          </span>
        ))}
      </div>
      {ROWS.map((row) => (
        <div key={row.key} className={`eld-row eld-row-${row.key}`}>
          <div className="eld-row-label">{row.label}</div>
          <div className="eld-track">
            {byStatus[row.key].map((seg, i) => (
              <SegmentBar key={`${row.key}-${i}-${seg.start_minute}`} seg={seg} />
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}

export default function EldSheets({ eldDays, drivingMilesByDate = {} }) {
  if (!eldDays?.length) return null
  return (
    <div className="eld-sheets">
      {eldDays.map((d) => (
        <DayGrid
          key={d.date}
          day={d}
          drivingMiles={
            Object.keys(drivingMilesByDate).length === 0
              ? null
              : (drivingMilesByDate[d.date] ?? 0)
          }
        />
      ))}
    </div>
  )
}
