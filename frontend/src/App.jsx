import { useEffect, useState } from 'react'
import './App.css'

function healthUrl() {
  const base = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
  return base ? `${base}/api/health/` : '/api/health/'
}

function App() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(healthUrl())
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <main className="app">
      <h1>Spotter</h1>
      <p className="subtitle">Django + React</p>
      <section className="card">
        <h2>Backend API</h2>
        {loading && <p>Checking API…</p>}
        {error && (
          <p className="err">
            Could not reach the API. Start Django:{' '}
            <code>python manage.py runserver</code> in <code>backend/</code>
            {' — '}
            {error}
          </p>
        )}
        {data && <pre className="json">{JSON.stringify(data, null, 2)}</pre>}
      </section>
    </main>
  )
}

export default App
