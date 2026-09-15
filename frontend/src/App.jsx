import { useCallback, useEffect, useState } from 'react'
import { Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, loadConfig, saveConfig, toRequest } from './api.js'
import Overview from './components/Overview.jsx'
import RunView from './components/RunView.jsx'
import Sidebar from './components/Sidebar.jsx'

const useTheme = () => {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('or-theme') || 'dark' } catch { return 'dark' }
  })
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try { localStorage.setItem('or-theme', theme) } catch { /* private mode */ }
  }, [theme])
  return [theme, () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))]
}

export default function App() {
  const [theme, toggleTheme] = useTheme()
  const [data, setData] = useState(null)
  const [config, setConfig] = useState(loadConfig)
  const [busy, setBusy] = useState(false)
  const [activeRunId, setActiveRunId] = useState(null)
  const [stopping, setStopping] = useState(false)
  const [error, setError] = useState(null)
  const [confirmClear, setConfirmClear] = useState(false)
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('or-sidebar') === 'collapsed' } catch { return false }
  })
  const [confirmDelete, setConfirmDelete] = useState(null)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    try { localStorage.setItem('or-sidebar', collapsed ? 'collapsed' : 'open') }
    catch { /* private mode */ }
  }, [collapsed])

  useEffect(() => { saveConfig(config) }, [config])

  const refresh = useCallback(async () => {
    try { setData(await api('/api/state')); setError(null) } catch (e) { setError(e.message) }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // While a run is in flight the sidebar list needs to keep updating too, so
  // the new run appears and its counts move.
  useEffect(() => {
    if (!busy) return undefined
    const timer = setInterval(refresh, 3000)
    return () => clearInterval(timer)
  }, [busy, refresh])

  const start = async (path, dryRun) => {
    setBusy(true); setStopping(false); setError(null)
    try {
      const res = await api(path, {
        method: 'POST',
        body: JSON.stringify(toRequest(config, dryRun)),
      })
      if (res.run_id) {
        setActiveRunId(res.run_id)
        navigate(`/run/${res.run_id}`)
      } else {
        // /api/eligibility has no run of its own.
        setTimeout(() => { refresh(); setBusy(false) }, 4000)
      }
    } catch (e) {
      setError(e.message); setBusy(false)
    }
  }

  // Cancels the budget server-side; the run then refuses paid tools but still
  // saves whatever it has already extracted.
  const stopRun = async () => {
    if (!activeRunId) return
    setStopping(true)
    try { await api(`/api/runs/${activeRunId}/stop`, { method: 'POST' }) }
    catch (e) { setError(e.message); setStopping(false) }
  }

  const onRunFinished = useCallback(() => {
    setBusy(false); setStopping(false); setActiveRunId(null); refresh()
  }, [refresh])

  const deleteRun = async (run) => {
    setConfirmDelete(null)
    try {
      await api(`/api/runs/${run.run_id}`, { method: 'DELETE' })
      // Only navigate away if the deleted run is the one on screen.
      if (location.pathname === `/run/${run.run_id}`) navigate('/')
      await refresh()
    } catch (e) { setError(e.message) }
  }

  const clearDatabase = async () => {
    setConfirmClear(false); setBusy(true)
    try {
      await api('/api/database/clear', { method: 'POST' })
      navigate('/')
      await refresh()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <div className={`shell${collapsed ? ' collapsed' : ''}`}>
      <Sidebar
        config={config} setConfig={setConfig} busy={busy} onStart={start}
        runs={data?.runs || []} theme={theme} toggleTheme={toggleTheme}
        onClear={() => setConfirmClear(true)}
        collapsed={collapsed} onToggleCollapse={() => setCollapsed((v) => !v)}
        onDeleteRun={setConfirmDelete}
      />

      <main className="main">
        {error && <div className="card err">{error}</div>}
        <Routes>
          <Route path="/" element={<Overview data={data} />} />
          <Route
            path="/run/:runId"
            element={
              <RunView onRunFinished={onRunFinished} onStop={stopRun} stopping={stopping} />
            }
          />
          <Route path="*" element={<Overview data={data} />} />
        </Routes>
      </main>

      {confirmDelete && (
        <div className="modal-back" onClick={() => setConfirmDelete(null)}>
          <div className="modal" onClick={(ev) => ev.stopPropagation()}>
            <h3>Delete this run?</h3>
            <p className="small muted">
              Removes the run record and its full journey — the steps, reasoning and
              fetched page content. Opportunities it stored are <strong>kept</strong>,
              because a record is upserted on its own identity and may have been
              confirmed by later runs.
            </p>
            <div className="row" style={{ marginTop: 16 }}>
              <button className="danger" type="button"
                      onClick={() => deleteRun(confirmDelete)}>
                Delete the run record
              </button>
              <button className="ghost" type="button" onClick={() => setConfirmDelete(null)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmClear && (
        <div className="modal-back" onClick={() => setConfirmClear(false)}>
          <div className="modal" onClick={(ev) => ev.stopPropagation()}>
            <h3>Clear the database?</h3>
            <p className="small muted">
              Deletes every stored opportunity, the programme registry, all run history
              and extraction failures. The business profile and golden set are files and
              are not touched. This cannot be undone.
            </p>
            <div className="row" style={{ marginTop: 16 }}>
              <button className="danger" type="button" onClick={clearDatabase}>
                Yes, delete everything
              </button>
              <button className="ghost" type="button" onClick={() => setConfirmClear(false)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
