import { useCallback, useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ApiError, api, getToken, saveToken } from './api'

const timeFormat = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })
const dayFormat = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' })

function LoginForm({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { access_token } = await api.login(email, password)
      onLogin(access_token)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card login" onSubmit={submit}>
      <h2>Log in to claim food</h2>
      <label>
        Email
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
      </label>
      <label>
        Password
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
      </label>
      {error && <p className="error">{error}</p>}
      <button disabled={busy}>{busy ? 'Logging in…' : 'Log in'}</button>
    </form>
  )
}

function RescueChart({ days }) {
  const data = days.map((d) => ({ ...d, label: dayFormat.format(new Date(`${d.date}T12:00:00`)) }))
  const totalRescued = days.reduce((sum, d) => sum + d.meals_rescued, 0)
  const totalPosted = days.reduce((sum, d) => sum + d.portions_posted, 0)
  return (
    <section className="card">
      <div className="row">
        <h2>Last 30 days</h2>
        <div className="totals">
          <span><strong>{totalPosted}</strong> portions posted</span>
          <span><strong>{totalRescued}</strong> meals rescued</span>
        </div>
      </div>
      <div className="chart">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="label" tick={{ fill: 'var(--muted)', fontSize: 12 }} interval="preserveStartEnd" minTickGap={24} />
            <YAxis allowDecimals={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} />
            <Tooltip contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', color: 'var(--text)' }} />
            <Legend />
            <Bar dataKey="portions_posted" name="Portions posted" fill="var(--series-2)" radius={[3, 3, 0, 0]} />
            <Bar dataKey="meals_rescued" name="Meals rescued" fill="var(--accent)" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}

export default function App() {
  const [token, setToken] = useState(getToken)
  const [me, setMe] = useState(null)
  const [listings, setListings] = useState([])
  const [claims, setClaims] = useState([])
  const [days, setDays] = useState([])
  const [message, setMessage] = useState('')
  const [loadError, setLoadError] = useState('')

  const logout = useCallback(() => {
    saveToken(null)
    setToken(null)
    setMe(null)
    setClaims([])
  }, [])

  const refresh = useCallback(async () => {
    try {
      const [l, d] = await Promise.all([api.listings(), api.dailyStats(30)])
      setListings(l)
      setDays(d)
      setLoadError('')
    } catch (err) {
      setLoadError(`Couldn't reach the API: ${err.message}`)
    }
    if (token) {
      try {
        const [m, c] = await Promise.all([api.me(token), api.myClaims(token)])
        setMe(m)
        setClaims(c)
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) logout()
      }
    }
  }, [token, logout])

  useEffect(() => {
    refresh()
  }, [refresh])

  function login(newToken) {
    saveToken(newToken)
    setToken(newToken)
  }

  async function claim(listingId) {
    try {
      const c = await api.claim(token, listingId)
      setMessage(`Claimed! Your pickup code is ${c.pickup_code}. Pick up by ${timeFormat.format(new Date(c.expires_at))}.`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) logout()
      setMessage(err.message)
    }
    refresh()
  }

  const claimedIds = new Set(claims.map((c) => c.listing_id))

  return (
    <>
      <header>
        <span className="brand">Leftover <span className="muted">dashboard</span></span>
        {me && (
          <span className="who">
            {me.name} <button className="link" onClick={logout}>Log out</button>
          </span>
        )}
      </header>
      <main>
        {message && <div className="flash">{message}</div>}
        {loadError && <div className="flash error">{loadError}</div>}

        <RescueChart days={days} />

        <section className="card">
          <h2>Available now</h2>
          {listings.length === 0 ? (
            <p className="muted">Nothing up right now. Check back after campus events.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Food</th><th>Where</th><th>Until</th><th className="num">Left</th><th></th></tr>
                </thead>
                <tbody>
                  {listings.map((l) => (
                    <tr key={l.id}>
                      <td>{l.title}</td>
                      <td>{l.location}</td>
                      <td>{timeFormat.format(new Date(l.available_until))}</td>
                      <td className="num">{l.remaining} / {l.portions}</td>
                      <td className="action">
                        {!token ? null : claimedIds.has(l.id) ? (
                          <span className="muted">Claimed</span>
                        ) : l.remaining > 0 ? (
                          <button className="small" onClick={() => claim(l.id)}>Claim</button>
                        ) : (
                          <span className="muted">All gone</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {token ? (
          <section className="card">
            <h2>Your claims</h2>
            {claims.length === 0 ? (
              <p className="muted">You haven't claimed anything yet.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Food</th><th>Where</th><th>Code</th><th>Status</th></tr>
                  </thead>
                  <tbody>
                    {claims.map((c) => (
                      <tr key={c.id}>
                        <td>{c.listing_title}</td>
                        <td>{c.location}</td>
                        <td className="code">{c.pickup_code}</td>
                        <td>{c.status === 'held' ? `Pick up by ${timeFormat.format(new Date(c.expires_at))}` : 'Picked up'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ) : (
          <LoginForm onLogin={login} />
        )}
      </main>
    </>
  )
}
