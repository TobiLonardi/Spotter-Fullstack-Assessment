import { useMemo, useState } from 'react'
import './App.css'
import { computeDrivingMilesByDate } from './eldDrivingMiles.js'
import EldSheets from './EldSheets.jsx'
import TripMap from './TripMap.jsx'

function apiUrl(path) {
  const base = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
  return base ? `${base}${path}` : path
}

function formatWhen(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    })
  } catch {
    return iso
  }
}

function legStatusLabel(status) {
  switch (status) {
    case 'D':
      return 'Driving'
    case 'ON':
      return 'On duty (not driving)'
    case 'OFF':
      return 'Off duty'
    case 'SB':
      return 'Sleeper berth'
    default:
      return status || ''
  }
}

function legTagClassName(leg) {
  const parts = ['leg-tag', `leg-${leg.type}`]
  if (leg.status === 'SB') parts.push('leg-sb')
  else if (leg.status === 'OFF') parts.push('leg-off-duty')
  return parts.join(' ')
}

function HosModelDetails({ hosModel }) {
  if (!hosModel || typeof hosModel !== 'object') return null
  const { summary, implemented_rules, grid_display_conventions } = hosModel
  return (
    <details className="hos-model-details">
      <summary>HOS model (FMCSA-style scope)</summary>
      {summary ? <p className="hos-model-summary">{summary}</p> : null}
      {Array.isArray(implemented_rules) && implemented_rules.length > 0 ? (
        <>
          <h3 className="hos-model-sub">Included in simulation</h3>
          <ul>
            {implemented_rules.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </>
      ) : null}
      {Array.isArray(grid_display_conventions) && grid_display_conventions.length > 0 ? (
        <>
          <h3 className="hos-model-sub">Daily grid display</h3>
          <ul>
            {grid_display_conventions.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </>
      ) : null}
    </details>
  )
}

export default function App() {
  const [currentLocation, setCurrentLocation] = useState('')
  const [pickupLocation, setPickupLocation] = useState('')
  const [dropoffLocation, setDropoffLocation] = useState('')
  const [cycleUsed, setCycleUsed] = useState('0')
  const [timezone, setTimezone] = useState('America/Chicago')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [plan, setPlan] = useState(null)

  const drivingMilesByDate = useMemo(
    () =>
      computeDrivingMilesByDate(
        plan?.legs,
        plan?.route?.distance_miles,
        timezone,
      ),
    [plan?.legs, plan?.route?.distance_miles, timezone],
  )

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setPlan(null)
    setLoading(true)
    const body = {
      current_location: currentLocation.trim(),
      pickup_location: pickupLocation.trim(),
      dropoff_location: dropoffLocation.trim(),
      current_cycle_used_hours: parseFloat(cycleUsed) || 0,
      timezone,
    }
    try {
      const res = await fetch(apiUrl('/api/trip/plan/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        const msg =
          typeof data.detail === 'string'
            ? data.detail
            : JSON.stringify(data.detail || data)
        throw new Error(msg || `HTTP ${res.status}`)
      }
      setPlan(data)
    } catch (err) {
      setError(err.message || String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="app">
      <header className="hero">
        <h1>Spotter — Trip Planner</h1>
        <p className="subtitle">
          Route, stops, and ELD-style daily grids.
        </p>
      </header>

      <form className="trip-form card" onSubmit={submit}>
        <h2>Trip inputs</h2>
        <label>
          Current location
          <input
            value={currentLocation}
            onChange={(e) => setCurrentLocation(e.target.value)}
            placeholder="Address or city, state"
            required
          />
        </label>
        <label>
          Pickup location
          <input
            value={pickupLocation}
            onChange={(e) => setPickupLocation(e.target.value)}
            placeholder="Address or city, state"
            required
          />
        </label>
        <label>
          Dropoff location
          <input
            value={dropoffLocation}
            onChange={(e) => setDropoffLocation(e.target.value)}
            placeholder="Address or city, state"
            required
          />
        </label>
        <label>
          Current cycle used (hours, 70h / 8 days)
          <input
            type="number"
            min={0}
            max={70}
            step={0.25}
            value={cycleUsed}
            onChange={(e) => setCycleUsed(e.target.value)}
            required
          />
        </label>
        <label>
          Timezone (for daily logs)
          <input
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            placeholder="America/Chicago"
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? 'Planning…' : 'Plan trip'}
        </button>
      </form>

      {error && (
        <p className="err card" role="alert">
          {error}
        </p>
      )}

      {plan && (
        <>
          {plan.disclaimer && <p className="disclaimer card">{plan.disclaimer}</p>}

          <HosModelDetails hosModel={plan.hos_model} />

          <section className="card route-summary">
            <h2>Route</h2>
            <p>
              <strong>{plan.route?.distance_miles}</strong> miles ·{' '}
              <strong>{plan.route?.duration_minutes}</strong> min driving (API estimate,
              before mandatory breaks)
            </p>
            <TripMap
              lineLatLng={plan.route?.coordinates_latlng || []}
              stops={plan.stops || []}
            />
          </section>

          <section className="card legs">
            <h2>Route instructions &amp; breaks</h2>
            <p className="legs-hint">
              Includes pickup/dropoff (1 h each), fuel (~30 min per 1,000 mi), and HOS
              rests (11/14, 30 min after 8 h driving, 10 h reset, simplified 70 h / 8 d
              with 34 h restart).
            </p>
            <ol className="legs-list">
              {(plan.legs || []).map((leg, i) => (
                <li key={i}>
                  <span className={legTagClassName(leg)}>{legStatusLabel(leg.status)}</span>{' '}
                  <strong>{leg.label}</strong>
                  <div className="leg-meta">
                    {formatWhen(leg.start)} → {formatWhen(leg.end)} ·{' '}
                    {leg.duration_minutes} min
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <section className="card eld-wrap">
            <h2>Daily log sheets</h2>
            <p className="eld-wrap-hint">
              Estimated driving miles per day split by time on duty driving (D); proportional to{' '}
              <strong>{plan.route?.distance_miles}</strong> mi total route.
            </p>
            <EldSheets
              eldDays={plan.eld_days || []}
              drivingMilesByDate={drivingMilesByDate}
            />
          </section>
        </>
      )}
    </main>
  )
}
