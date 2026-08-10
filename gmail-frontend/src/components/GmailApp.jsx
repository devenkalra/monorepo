import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import api from '../services/api'
import { getLoginUrl } from '../utils/apiUrl'
import {
  escapeHtml,
  formatMailDate,
  gmailOpenUrl,
  linkifyHtml,
  shortFrom,
  snippetWords,
} from '../utils/format'

const API = '/api/gmail'

export default function GmailApp() {
  const { user, loading, logout, isAuthenticated } = useAuth()
  const [status, setStatus] = useState(null)
  const [statusMsg, setStatusMsg] = useState('')
  const [statusKind, setStatusKind] = useState('')
  const [prompt, setPrompt] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [days, setDays] = useState('')
  const [keyword, setKeyword] = useState('')
  const [queryPreview, setQueryPreview] = useState('')
  const [emails, setEmails] = useState([])
  const [selected, setSelected] = useState(() => new Set())
  const [anchorIndex, setAnchorIndex] = useState(null)
  const [focusId, setFocusId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [bodyLoading, setBodyLoading] = useState(false)
  const [detailExpanded, setDetailExpanded] = useState(false)
  const detailFetchSeq = useRef(0)
  const [prompts, setPrompts] = useState([])
  const [promptSelect, setPromptSelect] = useState('')
  const [labels, setLabels] = useState([])
  const [labelMode, setLabelMode] = useState(null) // 'labels' | 'move'
  const [labelOpen, setLabelOpen] = useState(false)
  const [checkedLabels, setCheckedLabels] = useState(() => new Set())
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveLabel, setSaveLabel] = useState('')
  const [processOpen, setProcessOpen] = useState(false)
  const [processPrompt, setProcessPrompt] = useState('')
  const [progress, setProgress] = useState(null)
  const [prefsOpen, setPrefsOpen] = useState(false)
  const [schedulesOpen, setSchedulesOpen] = useState(false)
  const [schedules, setSchedules] = useState([])
  const [schedLabel, setSchedLabel] = useState('')
  const [schedHours, setSchedHours] = useState('24')
  const [schedForce, setSchedForce] = useState(false)
  const sessionSummarized = useRef(new Set())
  const previewTimer = useRef(null)
  const shiftHeldRef = useRef(false)

  const activeAccount = useMemo(() => {
    if (!status?.accounts?.length) return null
    return (
      status.accounts.find((a) => a.id === status.active_account_id) ||
      status.accounts[0]
    )
  }, [status])

  const flash = (msg, kind = '') => {
    setStatusMsg(msg)
    setStatusKind(kind)
  }

  const loadStatus = useCallback(async () => {
    const data = await api.json(`${API}/status/`)
    setStatus(data)
    return data
  }, [])

  const loadPrompts = useCallback(async () => {
    const data = await api.json(`${API}/prompts/`)
    setPrompts(data.prompts || [])
  }, [])

  const loadSchedules = useCallback(async () => {
    const data = await api.json(`${API}/schedules/`)
    setSchedules(data.schedules || [])
  }, [])

  useEffect(() => {
    if (loading || isAuthenticated) return
    window.location.replace(getLoginUrl('/gmail-app/'))
  }, [loading, isAuthenticated])

  useEffect(() => {
    if (!isAuthenticated) return
    loadStatus()
      .then(() => Promise.all([loadPrompts(), loadSchedules()]))
      .catch((e) => flash(String(e.message || e), 'error'))
    const params = new URLSearchParams(window.location.search)
    const oauth = params.get('oauth')
    if (oauth === 'ok') flash('Gmail account connected.', 'ok')
    if (oauth === 'error') flash(`OAuth error: ${params.get('detail') || 'unknown'}`, 'error')
  }, [isAuthenticated, loadStatus, loadPrompts, loadSchedules])

  const openSchedules = async () => {
    try {
      await loadSchedules()
      setSchedLabel('')
      setSchedHours('24')
      setSchedForce(false)
      setSchedulesOpen(true)
    } catch (e) {
      flash(String(e.message || e), 'error')
    }
  }

  const createSchedule = async () => {
    const label = schedLabel.trim()
    if (!label) {
      flash('Enter a schedule name.', 'error')
      return
    }
    const hours = Number(schedHours)
    if (!Number.isFinite(hours) || hours < 1 || hours > 168) {
      flash('Interval must be 1–168 hours.', 'error')
      return
    }
    const daysRaw = days.trim()
    const daysN = daysRaw === '' ? null : Number(daysRaw)
    try {
      await api.json(`${API}/schedules/`, {
        method: 'POST',
        body: JSON.stringify({
          label,
          prompt: prompt.trim(),
          start_date: startDate || '',
          end_date: endDate || '',
          days: Number.isFinite(daysN) && daysN > 0 ? daysN : null,
          keyword: keyword.trim(),
          interval_hours: hours,
          force: schedForce,
          max_results: 100,
          enabled: true,
          account_id: activeAccount?.id,
        }),
      })
      await loadSchedules()
      flash(`Schedule “${label}” saved.`, 'ok')
      setSchedLabel('')
    } catch (e) {
      flash(String(e.message || e), 'error')
    }
  }

  const patchSchedule = async (id, patch) => {
    try {
      await api.json(`${API}/schedules/${id}/`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      })
      await loadSchedules()
    } catch (e) {
      flash(String(e.message || e), 'error')
    }
  }

  const deleteSchedule = async (id) => {
    try {
      await api.json(`${API}/schedules/${id}/`, { method: 'DELETE' })
      await loadSchedules()
      flash('Schedule deleted.', 'ok')
    } catch (e) {
      flash(String(e.message || e), 'error')
    }
  }

  const runScheduleNow = async (id) => {
    try {
      const data = await api.json(`${API}/schedules/${id}/run/`, { method: 'POST' })
      flash('Schedule run queued.', 'ok')
      if (data.task_id) {
        // Lightweight refresh of schedule status after a short delay
        setTimeout(() => loadSchedules().catch(() => {}), 2000)
      }
    } catch (e) {
      flash(String(e.message || e), 'error')
    }
  }

  useEffect(() => {
    if (!detailExpanded) return undefined
    const onKey = (ev) => {
      if (ev.key === 'Escape') setDetailExpanded(false)
    }
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [detailExpanded])

  useEffect(() => {
    if (!detail) setDetailExpanded(false)
  }, [detail])

  const searchPayload = () => {
    const daysRaw = days.trim()
    const daysN = daysRaw === '' ? null : Number(daysRaw)
    return {
      prompt: prompt.trim(),
      start_date: startDate || null,
      end_date: endDate || null,
      days: Number.isFinite(daysN) && daysN > 0 ? daysN : null,
      keyword: keyword.trim() || null,
      account_id: activeAccount?.id,
    }
  }

  const hasCriteria = (p) =>
    Boolean(p.prompt || p.start_date || p.end_date || p.days || p.keyword)

  const schedulePreview = () => {
    clearTimeout(previewTimer.current)
    previewTimer.current = setTimeout(async () => {
      const payload = searchPayload()
      if (!hasCriteria(payload)) {
        setQueryPreview('')
        return
      }
      try {
        const data = await api.json(`${API}/query/preview/`, {
          method: 'POST',
          body: JSON.stringify(payload),
        })
        setQueryPreview(data.query || '')
      } catch {
        /* ignore */
      }
    }, 300)
  }

  useEffect(() => {
    schedulePreview()
    return () => clearTimeout(previewTimer.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prompt, startDate, endDate, days, keyword])

  const runSearch = async () => {
    const payload = { ...searchPayload(), max_results: 100 }
    if (!hasCriteria(payload)) {
      flash('Enter a prompt and/or qualifiers.', 'error')
      return
    }
    flash('Searching…')
    try {
      const data = await api.json(`${API}/search/`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setEmails(data.emails || [])
      setSelected(new Set())
      setAnchorIndex(null)
      setFocusId(null)
      setDetail(null)
      setQueryPreview(data.query || '')
      flash(`Found ${data.count} message(s).`, 'ok')
    } catch (e) {
      flash(String(e.message || e), 'error')
    }
  }

  const selectedIds = () => {
    const ids = emails.filter((e) => selected.has(e.gmail_id)).map((e) => e.gmail_id)
    if (ids.length) return ids
    if (focusId) return [focusId]
    return []
  }

  const pollTask = async (taskId) => {
    for (;;) {
      const data = await api.json(`${API}/tasks/${taskId}/progress/`)
      setProgress(data)
      if (data.status === 'completed' || data.status === 'failed') return data
      await new Promise((r) => setTimeout(r, 700))
    }
  }

  const connectGmail = async () => {
    try {
      const data = await api.json(`${API}/oauth/start/`)
      window.location.href = data.authorize_url
    } catch (e) {
      flash(String(e.message || e), 'error')
    }
  }

  const switchAccount = async (id) => {
    await api.json(`${API}/accounts/${id}/activate/`, { method: 'POST' })
    await loadStatus()
    flash('Active account switched.', 'ok')
  }

  const disconnectAccount = async (id) => {
    if (!confirm('Disconnect this Gmail account from the assistant?')) return
    await api.json(`${API}/accounts/${id}/`, { method: 'DELETE' })
    await loadStatus()
    flash('Account disconnected.', 'ok')
  }

  const bulk = async (action, extra = {}) => {
    const ids = selectedIds()
    if (!ids.length) return null
    if (action === 'delete' && !confirm(`Trash ${ids.length} message(s)?`)) return null
    const data = await api.json(`${API}/emails/bulk/`, {
      method: 'POST',
      body: JSON.stringify({
        action,
        gmail_ids: ids,
        account_id: activeAccount?.id,
        ...extra,
      }),
    })
    return data
  }

  const removeDone = (data) => {
    const done = new Set(data?.done || [])
    setEmails((prev) => prev.filter((e) => !done.has(e.gmail_id)))
    setSelected((prev) => {
      const next = new Set(prev)
      done.forEach((id) => next.delete(id))
      return next
    })
  }

  const openLabelPicker = async (mode) => {
    setLabelMode(mode)
    flash('Loading labels…')
    try {
      const data = await api.json(
        `${API}/labels/?account_id=${encodeURIComponent(activeAccount?.id || '')}`
      )
      setLabels(data.labels || [])
      setCheckedLabels(new Set())
      setLabelOpen(true)
      flash(mode === 'move' ? 'Choose destination, then Move.' : 'Choose labels, then Apply.')
    } catch (e) {
      flash(String(e.message || e), 'error')
    }
  }

  const applyLabels = async () => {
    const ids = [...checkedLabels]
    if (!ids.length) {
      flash('Select at least one label.', 'error')
      return
    }
    setLabelOpen(false)
    const action = labelMode === 'move' ? 'move' : 'labels'
    try {
      const data = await bulk(action, { label_ids: ids })
      if (!data) return
      if (action === 'move') removeDone(data)
      flash(
        action === 'move'
          ? `Moved ${data.done?.length || 0}.`
          : `Labels updated on ${data.done?.length || 0}.`,
        'ok'
      )
    } catch (e) {
      flash(String(e.message || e), 'error')
    }
  }

  const runSummarize = async () => {
    const ids = selectedIds()
    if (!ids.length) return
    flash('Summarizing…')
    setProgress({ status: 'processing', message: 'Starting…', percentage: 0 })
    try {
      const start = await api.json(`${API}/summarize/`, {
        method: 'POST',
        body: JSON.stringify({
          gmail_ids: ids,
          account_id: activeAccount?.id,
          force: false,
        }),
      })
      const done = await pollTask(start.task_id)
      if (done.status === 'failed') throw new Error(done.message || 'Summarize failed')
      ;(done.done || []).forEach((id) => sessionSummarized.current.add(id))
      flash(
        `Summarized ${done.done?.length || 0}, skipped ${done.skipped?.length || 0}.`,
        'ok'
      )
      await runSearch()
    } catch (e) {
      flash(String(e.message || e), 'error')
    } finally {
      setProgress(null)
    }
  }

  const runProcess = async () => {
    const ids = selectedIds()
    const p = processPrompt.trim()
    if (!p || !ids.length) return
    setProcessOpen(false)
    flash('Processing…')
    setProgress({ status: 'processing', message: 'Starting…', percentage: 0 })
    try {
      const start = await api.json(`${API}/process/`, {
        method: 'POST',
        body: JSON.stringify({
          gmail_ids: ids,
          prompt: p,
          account_id: activeAccount?.id,
        }),
      })
      const done = await pollTask(start.task_id)
      if (done.status === 'failed') throw new Error(done.message || 'Process failed')
      setDetail({
        kind: 'process',
        prompt: p,
        result: done.result || '',
        email_count: done.email_count || ids.length,
      })
      flash('Process complete.', 'ok')
    } catch (e) {
      flash(String(e.message || e), 'error')
    } finally {
      setProgress(null)
    }
  }

  const savePrompt = async () => {
    const label = saveLabel.trim()
    const text = prompt.trim()
    if (!label || !text) return
    await api.json(`${API}/prompts/`, {
      method: 'POST',
      body: JSON.stringify({ label, prompt: text }),
    })
    setSaveOpen(false)
    await loadPrompts()
    flash(`Saved prompt “${label}”.`, 'ok')
  }

  const savePrefs = async (patch) => {
    const data = await api.json(`${API}/preferences/`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    })
    setStatus((s) => (s ? { ...s, preferences: data } : s))
    flash('Preferences saved.', 'ok')
  }

  const noteShift = (ev) => {
    shiftHeldRef.current = !!ev.shiftKey
  }

  const selectRange = (idx, wantSelected) => {
    setSelected((prev) => {
      const next = new Set(prev)
      const start = anchorIndex != null ? anchorIndex : idx
      const a = Math.min(start, idx)
      const b = Math.max(start, idx)
      for (let i = a; i <= b; i++) {
        const mid = emails[i]?.gmail_id
        if (!mid) continue
        if (wantSelected) next.add(mid)
        else next.delete(mid)
      }
      return next
    })
  }

  const loadEmailDetail = async (row) => {
    if (!row?.gmail_id) return
    const seq = ++detailFetchSeq.current
    setDetail({ kind: 'email', email: row })
    setBodyLoading(true)
    try {
      const q = activeAccount?.id
        ? `?account_id=${encodeURIComponent(activeAccount.id)}`
        : ''
      const data = await api.json(`${API}/emails/${encodeURIComponent(row.gmail_id)}/${q}`)
      if (seq !== detailFetchSeq.current) return
      setDetail({
        kind: 'email',
        email: {
          ...row,
          ...(data.email || {}),
        },
      })
    } catch (e) {
      if (seq !== detailFetchSeq.current) return
      flash(String(e.message || e), 'error')
    } finally {
      if (seq === detailFetchSeq.current) setBodyLoading(false)
    }
  }

  const focusEmailRow = (row, idx) => {
    if (!row) return
    setFocusId(row.gmail_id)
    setSelected(new Set([row.gmail_id]))
    setAnchorIndex(idx)
    loadEmailDetail(row)
  }

  const goToNextEmail = (fromId) => {
    const idx = emails.findIndex((e) => e.gmail_id === fromId)
    if (idx < 0) return
    const next = emails[idx + 1]
    if (!next) {
      flash('End of search results.', 'ok')
      return
    }
    focusEmailRow(next, idx + 1)
  }

  const deleteAndNext = async (fromId) => {
    if (!fromId) return
    const idx = emails.findIndex((e) => e.gmail_id === fromId)
    const next = idx >= 0 ? emails[idx + 1] : null
    try {
      const data = await api.json(`${API}/emails/bulk/`, {
        method: 'POST',
        body: JSON.stringify({
          action: 'delete',
          gmail_ids: [fromId],
          account_id: activeAccount?.id,
        }),
      })
      removeDone(data)
      if (next) {
        focusEmailRow(next, idx) // after removal, next sits at old idx
        flash('Deleted. Showing next.', 'ok')
      } else {
        setDetail(null)
        setFocusId(null)
        setDetailExpanded(false)
        flash('Deleted. End of search results.', 'ok')
      }
    } catch (e) {
      flash(String(e.message || e), 'error')
    }
  }

  const toggleRow = (ev, idx, id) => {
    const row = emails.find((x) => x.gmail_id === id)
    if (shiftHeldRef.current && anchorIndex != null) {
      setFocusId(id)
      if (row) loadEmailDetail(row)
      selectRange(idx, true)
      return
    }
    focusEmailRow(row, idx)
  }

  const onCheck = (ev, idx, id) => {
    const turningOn = ev.target.checked
    if (shiftHeldRef.current && anchorIndex != null) {
      selectRange(idx, turningOn)
      return
    }
    setSelected((prev) => {
      const next = new Set(prev)
      if (turningOn) next.add(id)
      else next.delete(id)
      return next
    })
    setAnchorIndex(idx)
  }

  if (loading || !isAuthenticated) {
    return (
      <div className="flex h-full items-center justify-center text-stone-500">
        {loading ? 'Loading…' : 'Redirecting to login…'}
      </div>
    )
  }

  const prefs = status?.preferences || {}
  const nSel = selected.size
  const connected = !!status?.connected

  return (
    <div className="mx-auto flex min-h-full max-w-7xl flex-col gap-3 p-4 md:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-2xl font-semibold tracking-tight text-emerald-900">Gmail Assistant</p>
          <p className="text-sm text-stone-500">
            Search · select · act · summarize only what you choose
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              connected ? 'bg-emerald-600' : 'bg-stone-300'
            }`}
            title={connected ? 'Connected' : 'Not connected'}
          />
          <button type="button" className="text-stone-600 underline" onClick={openSchedules}>
            Schedules
          </button>
          <button type="button" className="text-stone-600 underline" onClick={() => setPrefsOpen(true)}>
            Prefs
          </button>
          <a className="text-stone-600 underline" href="/">
            Home
          </a>
          <button type="button" className="text-stone-600 underline" onClick={logout}>
            Log out ({user?.username || user?.email})
          </button>
        </div>
      </header>

      <section className="flex flex-wrap items-center gap-2 rounded-xl border border-stone-200 bg-white/80 p-3">
        {!connected ? (
          <button
            type="button"
            onClick={connectGmail}
            className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-medium text-white"
          >
            Connect Gmail
          </button>
        ) : (
          <>
            <select
              className="rounded-lg border border-stone-200 bg-[#fffdf8] px-2 py-1.5 text-sm"
              value={activeAccount?.id || ''}
              onChange={(ev) => switchAccount(ev.target.value)}
            >
              {(status.accounts || []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.email}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={connectGmail}
              className="rounded-lg border border-stone-200 px-3 py-1.5 text-sm"
            >
              Add account
            </button>
            {activeAccount && (
              <button
                type="button"
                onClick={() => disconnectAccount(activeAccount.id)}
                className="rounded-lg border border-stone-200 px-3 py-1.5 text-sm"
              >
                Disconnect
              </button>
            )}
          </>
        )}
        <select
          className="rounded-lg border border-stone-200 bg-[#fffdf8] px-2 py-1.5 text-sm"
          value={promptSelect}
          onChange={(ev) => {
            const id = ev.target.value
            setPromptSelect(id)
            const row = prompts.find((p) => p.id === id)
            if (row) {
              setPrompt(row.prompt)
              flash(`Loaded “${row.label}” (not executed).`, 'ok')
            }
          }}
        >
          <option value="">Saved prompts…</option>
          {prompts.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="rounded-lg border border-stone-200 px-3 py-1.5 text-sm"
          onClick={() => {
            if (!prompt.trim()) {
              flash('Type a prompt before saving.', 'error')
              return
            }
            setSaveLabel('')
            setSaveOpen(true)
          }}
        >
          Save prompt
        </button>
      </section>

      <section className="grid grid-cols-1 gap-2 md:grid-cols-[1fr_auto]">
        <textarea
          className="min-h-[3.2rem] rounded-xl border border-stone-200 bg-[#fffdf8] p-3 text-sm"
          rows={2}
          placeholder="e.g. find email from smithsonian, borowitz, infoq in inbox"
          value={prompt}
          onChange={(ev) => setPrompt(ev.target.value)}
          onKeyDown={(ev) => {
            if (ev.key === 'Enter' && (ev.metaKey || ev.ctrlKey)) {
              ev.preventDefault()
              runSearch()
            }
          }}
        />
        <button
          type="button"
          disabled={!connected}
          onClick={runSearch}
          className="rounded-xl bg-emerald-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          Search
        </button>
      </section>

      <section className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <label className="grid gap-1 text-[0.7rem] font-semibold uppercase tracking-wide text-stone-500">
          Start date
          <input type="date" className="rounded-lg border border-stone-200 bg-[#fffdf8] px-2 py-1.5 text-sm font-normal normal-case text-stone-900" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </label>
        <label className="grid gap-1 text-[0.7rem] font-semibold uppercase tracking-wide text-stone-500">
          End date
          <input type="date" className="rounded-lg border border-stone-200 bg-[#fffdf8] px-2 py-1.5 text-sm font-normal normal-case text-stone-900" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </label>
        <label className="grid gap-1 text-[0.7rem] font-semibold uppercase tracking-wide text-stone-500">
          Days
          <input type="number" min={1} max={3650} placeholder="e.g. 7" className="rounded-lg border border-stone-200 bg-[#fffdf8] px-2 py-1.5 text-sm font-normal normal-case text-stone-900" value={days} onChange={(e) => setDays(e.target.value)} />
        </label>
        <label className="grid gap-1 text-[0.7rem] font-semibold uppercase tracking-wide text-stone-500">
          Keyword
          <input type="text" placeholder="subject/body term" className="rounded-lg border border-stone-200 bg-[#fffdf8] px-2 py-1.5 text-sm font-normal normal-case text-stone-900" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
        </label>
      </section>

      {queryPreview && (
        <p className="font-mono text-xs text-stone-500">Gmail query: {queryPreview}</p>
      )}

      <section className="flex flex-wrap items-center gap-2 rounded-xl border border-stone-200 bg-white/80 px-3 py-2 text-sm">
        <label className="inline-flex items-center gap-1">
          <input
            type="checkbox"
            checked={emails.length > 0 && selected.size === emails.length}
            onChange={(ev) => {
              if (ev.target.checked) setSelected(new Set(emails.map((e) => e.gmail_id)))
              else setSelected(new Set())
            }}
          />
          Select all
        </label>
        <span className="text-stone-500">{nSel} selected</span>
        <button type="button" disabled={!nSel || !connected} className="rounded-lg border px-2 py-1 disabled:opacity-40" onClick={async () => { const d = await bulk('archive'); if (d) { removeDone(d); flash(`Archived ${d.done?.length || 0}.`, 'ok') } }}>Archive</button>
        <button type="button" disabled={!nSel || !connected} className="rounded-lg border px-2 py-1 disabled:opacity-40" onClick={async () => { const d = await bulk('delete'); if (d) { removeDone(d); flash(`Deleted ${d.done?.length || 0}.`, 'ok') } }}>Delete</button>
        <button type="button" disabled={!nSel || !connected} className="rounded-lg border px-2 py-1 disabled:opacity-40" onClick={() => openLabelPicker('labels')}>Assign label</button>
        <button type="button" disabled={!nSel || !connected} className="rounded-lg border px-2 py-1 disabled:opacity-40" onClick={() => openLabelPicker('move')}>Move to</button>
        <button type="button" disabled={!nSel || !connected} className="rounded-lg bg-emerald-700 px-2 py-1 text-white disabled:opacity-40" onClick={runSummarize}>Summarize</button>
        <button type="button" disabled={!nSel || !connected} className="rounded-lg bg-emerald-700 px-2 py-1 text-white disabled:opacity-40" onClick={() => { setProcessPrompt(''); setProcessOpen(true) }}>Process</button>
      </section>

      {statusMsg && (
        <p className={`text-sm ${statusKind === 'error' ? 'text-red-700' : statusKind === 'ok' ? 'text-emerald-800' : 'text-stone-600'}`}>
          {statusMsg}
        </p>
      )}

      {progress && (
        <div className="rounded-xl border border-stone-200 bg-white p-3 text-sm">
          <div className="mb-1 flex justify-between font-medium">
            <span>{progress.message || progress.status}</span>
            <span>{progress.percentage ?? 0}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded bg-stone-100">
            <div className="h-full bg-emerald-600 transition-all" style={{ width: `${progress.percentage || 0}%` }} />
          </div>
        </div>
      )}

      <main
        className={
          detailExpanded
            ? 'hidden'
            : 'grid min-h-[420px] grid-cols-1 gap-3 lg:grid-cols-[1.4fr_1fr]'
        }
      >
        <section className="overflow-hidden rounded-xl border border-stone-200 bg-white">
          {!emails.length ? (
            <p className="p-4 text-sm text-stone-500">No messages. Try a search.</p>
          ) : (
            emails.map((e, idx) => {
              const summarized =
                e.has_summary || sessionSummarized.current.has(e.gmail_id)
              return (
                <div
                  key={e.gmail_id}
                  className={`grid grid-cols-[auto_1fr] border-b border-stone-100 ${
                    e.gmail_id === focusId ? 'bg-emerald-50' : ''
                  }`}
                >
                  <label
                    className="flex items-center px-3"
                    onClick={(ev) => ev.stopPropagation()}
                    onMouseDown={noteShift}
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(e.gmail_id)}
                      onMouseDown={noteShift}
                      onChange={(ev) => onCheck(ev, idx, e.gmail_id)}
                      title="Shift+click to select a range"
                    />
                  </label>
                  <div
                    role="button"
                    tabIndex={0}
                    className="grid cursor-pointer grid-cols-[9rem_1fr_auto] gap-x-3 gap-y-0.5 px-2 py-2 text-left text-sm hover:bg-emerald-50/50"
                    onMouseDown={noteShift}
                    onClick={(ev) => toggleRow(ev, idx, e.gmail_id)}
                    onKeyDown={(ev) => {
                      if (ev.key === 'Enter' || ev.key === ' ') {
                        ev.preventDefault()
                        shiftHeldRef.current = !!ev.shiftKey
                        toggleRow(ev, idx, e.gmail_id)
                      }
                    }}
                    title="Click to view email in the detail panel · Shift+click to select a range"
                  >
                    <span className="truncate font-semibold">{shortFrom(e.from_addr)}</span>
                    <span
                      className="truncate font-semibold"
                      dangerouslySetInnerHTML={{
                        __html: escapeHtml(e.subject || '(no subject)'),
                      }}
                    />
                    <span className="text-xs text-stone-500">
                      {formatMailDate(e.date_iso, e.internal_date_ms)}
                    </span>
                    <span
                      className="col-span-2 truncate text-xs text-stone-500"
                      dangerouslySetInnerHTML={{
                        __html: linkifyHtml(snippetWords(e.snippet)),
                      }}
                    />
                    {summarized && (
                      <span className="col-span-2 text-[0.7rem] text-emerald-800">
                        Summarized{e.category ? ` · ${e.category}` : ''}
                      </span>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </section>

        <section className="rounded-xl border border-stone-200 bg-white p-4 text-sm">
          {!detail && (
            <p className="text-stone-500">Select a row to inspect, or Summarize / Process selected.</p>
          )}
          {detail?.kind === 'process' && (
            <div className="space-y-2">
              <h2 className="text-lg font-semibold">Process result</h2>
              <p className="text-stone-500">{detail.prompt}</p>
              <p className="text-xs text-stone-400">{detail.email_count} emails</p>
              <div
                className="whitespace-pre-wrap"
                dangerouslySetInnerHTML={{ __html: linkifyHtml(detail.result) }}
              />
            </div>
          )}
          {detail?.kind === 'email' && (
            <EmailDetail
              email={detail.email}
              zk={!!prefs.zero_knowledge}
              bodyLoading={bodyLoading}
              expanded={false}
              onToggleExpand={() => setDetailExpanded(true)}
              hasNext={
                emails.findIndex((e) => e.gmail_id === detail.email?.gmail_id) <
                emails.length - 1
              }
              onNext={() => goToNextEmail(detail.email?.gmail_id)}
              onDeleteNext={() => deleteAndNext(detail.email?.gmail_id)}
              connected={connected}
            />
          )}
        </section>
      </main>

      {detailExpanded && detail?.kind === 'email' && (
        <div className="fixed inset-0 z-40 flex flex-col bg-[#f6f1e8] p-3 md:p-4">
          <div className="mx-auto flex h-full w-full max-w-[1600px] flex-col rounded-xl border border-stone-200 bg-white p-4 shadow-lg">
            <EmailDetail
              email={detail.email}
              zk={!!prefs.zero_knowledge}
              bodyLoading={bodyLoading}
              expanded
              onToggleExpand={() => setDetailExpanded(false)}
              hasNext={
                emails.findIndex((e) => e.gmail_id === detail.email?.gmail_id) <
                emails.length - 1
              }
              onNext={() => goToNextEmail(detail.email?.gmail_id)}
              onDeleteNext={() => deleteAndNext(detail.email?.gmail_id)}
              connected={connected}
            />
          </div>
        </div>
      )}

      {labelOpen && (
        <Modal
          title={labelMode === 'move' ? 'Move to' : 'Assign labels'}
          onClose={() => setLabelOpen(false)}
          actionLabel={labelMode === 'move' ? 'Move' : 'Apply'}
          onAction={applyLabels}
        >
          {labelMode === 'move' && (
            <p className="mb-2 text-xs text-stone-500">
              Adds selected label(s) and archives (removes from Inbox).
            </p>
          )}
          <div className="max-h-64 space-y-1 overflow-auto">
            {labels
              .filter((l) => l.type === 'user' || ['STARRED', 'IMPORTANT'].includes(l.id))
              .map((l) => (
                <label key={l.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={checkedLabels.has(l.id)}
                    onChange={(ev) => {
                      setCheckedLabels((prev) => {
                        const next = new Set(prev)
                        if (ev.target.checked) next.add(l.id)
                        else next.delete(l.id)
                        return next
                      })
                    }}
                  />
                  {l.name}
                </label>
              ))}
          </div>
        </Modal>
      )}

      {saveOpen && (
        <Modal title="Save prompt" onClose={() => setSaveOpen(false)} actionLabel="Save" onAction={savePrompt}>
          <label className="grid gap-1 text-sm">
            Label
            <input
              className="rounded-lg border border-stone-200 px-2 py-1.5"
              value={saveLabel}
              onChange={(e) => setSaveLabel(e.target.value)}
              autoFocus
            />
          </label>
        </Modal>
      )}

      {processOpen && (
        <Modal title="Process selected emails" onClose={() => setProcessOpen(false)} actionLabel="Run" onAction={runProcess}>
          <p className="mb-2 text-xs text-stone-500">
            Applies your prompt to {selectedIds().length} email(s), batched by context size.
          </p>
          <textarea
            className="min-h-24 w-full rounded-lg border border-stone-200 p-2 text-sm"
            placeholder="e.g. extract the books mentioned in these emails"
            value={processPrompt}
            onChange={(e) => setProcessPrompt(e.target.value)}
          />
        </Modal>
      )}

      {prefsOpen && (
        <Modal title="Preferences" onClose={() => setPrefsOpen(false)} actionLabel="Close" onAction={() => setPrefsOpen(false)}>
          <label className="mb-3 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!prefs.zero_knowledge}
              onChange={(e) => savePrefs({ zero_knowledge: e.target.checked })}
            />
            Zero-knowledge (do not store email content on server)
          </label>
          <label className="grid gap-1 text-sm">
            LLM context size (8192–64000)
            <input
              type="number"
              min={8192}
              max={64000}
              step={1024}
              className="rounded-lg border border-stone-200 px-2 py-1.5"
              defaultValue={prefs.llm_context_size || 8192}
              onBlur={(e) => {
                const n = Number(e.target.value)
                if (Number.isFinite(n)) savePrefs({ llm_context_size: n })
              }}
            />
          </label>
          <p className="mt-2 text-xs text-stone-500">
            Default context 8192. ZK default is off. Process results are discarded in ZK mode.
          </p>
        </Modal>
      )}

      {schedulesOpen && (
        <Modal
          title="Summarize schedules"
          onClose={() => setSchedulesOpen(false)}
          actionLabel="Close"
          onAction={() => setSchedulesOpen(false)}
          wide
        >
          <p className="mb-3 text-xs text-stone-500">
            Runs every N hours for the active account. Uses your current search filters when you create a schedule.
            Celery Beat checks due jobs about every 15 minutes.
          </p>

          <div className="mb-4 space-y-2 rounded-lg border border-stone-100 bg-stone-50/80 p-3">
            <p className="text-sm font-medium">New schedule from current filters</p>
            <p className="text-xs text-stone-500">
              Prompt: {prompt.trim() || '—'} · Days: {days || '—'} · Keyword: {keyword || '—'} ·
              Dates: {startDate || '—'} → {endDate || '—'}
            </p>
            <label className="grid gap-1 text-sm">
              Name
              <input
                className="rounded-lg border border-stone-200 px-2 py-1.5"
                value={schedLabel}
                onChange={(e) => setSchedLabel(e.target.value)}
                placeholder="e.g. Inbox last day"
              />
            </label>
            <label className="grid gap-1 text-sm">
              Every N hours (1–168)
              <input
                type="number"
                min={1}
                max={168}
                className="rounded-lg border border-stone-200 px-2 py-1.5"
                value={schedHours}
                onChange={(e) => setSchedHours(e.target.value)}
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={schedForce}
                onChange={(e) => setSchedForce(e.target.checked)}
              />
              Force re-summarize (ignore existing summaries)
            </label>
            <button
              type="button"
              className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm text-white disabled:opacity-40"
              disabled={!connected}
              onClick={createSchedule}
            >
              Create schedule
            </button>
          </div>

          {!schedules.length ? (
            <p className="text-sm text-stone-500">No schedules yet.</p>
          ) : (
            <ul className="max-h-72 space-y-2 overflow-auto">
              {schedules.map((s) => (
                <li
                  key={s.id}
                  className="rounded-lg border border-stone-200 bg-white p-3 text-sm"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold">{s.label}</p>
                      <p className="text-xs text-stone-500">
                        {s.account_email} · every {s.interval_hours}h
                        {s.force ? ' · force' : ''}
                      </p>
                      <p className="mt-1 text-xs text-stone-600">
                        {[s.prompt && `prompt: ${s.prompt}`, s.days != null && `days: ${s.days}`, s.keyword && `kw: ${s.keyword}`]
                          .filter(Boolean)
                          .join(' · ') || 'filter set'}
                      </p>
                      <p className="mt-1 text-xs text-stone-400">
                        Last: {s.last_run_at ? new Date(s.last_run_at).toLocaleString() : 'never'}
                        {s.last_status ? ` · ${s.last_status}` : ''}
                        {s.last_error ? ` · ${s.last_error}` : ''}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      <button
                        type="button"
                        className="rounded border px-2 py-0.5 text-xs"
                        onClick={() => patchSchedule(s.id, { enabled: !s.enabled })}
                      >
                        {s.enabled ? 'Disable' : 'Enable'}
                      </button>
                      <button
                        type="button"
                        className="rounded border px-2 py-0.5 text-xs"
                        onClick={() => runScheduleNow(s.id)}
                      >
                        Run now
                      </button>
                      <button
                        type="button"
                        className="rounded border px-2 py-0.5 text-xs text-red-700"
                        onClick={() => deleteSchedule(s.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Modal>
      )}
    </div>
  )
}

function emailFrameSrcDoc(html) {
  const body = (html || '').trim()
  if (!body) return ''
  // Open links in a new tab; keep styles readable inside the pane.
  return `<!doctype html><html><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<base target="_blank" rel="noopener noreferrer" />
<style>
  html, body { margin: 0; padding: 12px; background: #fff; color: #1c1917;
    font: 14px/1.45 system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
  img, video { max-width: 100%; height: auto; }
  a { color: #047857; }
  pre { white-space: pre-wrap; word-break: break-word; }
  table { max-width: 100%; }
</style></head><body>${body}</body></html>`
}

function EmailDetail({
  email: e,
  zk,
  bodyLoading,
  expanded,
  onToggleExpand,
  hasNext,
  onNext,
  onDeleteNext,
  connected,
}) {
  const href = gmailOpenUrl(e)
  const title = e.subject || '(no subject)'
  const html = (e.body_html || '').trim()
  const text = (e.body_text || '').trim()
  const srcDoc = emailFrameSrcDoc(html)
  return (
    <div
      className={
        expanded
          ? 'flex h-full min-h-0 flex-col gap-2'
          : 'flex max-h-[70vh] flex-col gap-2'
      }
    >
      <div className={`shrink-0 space-y-2 ${expanded ? 'max-h-[30vh] overflow-auto' : 'overflow-auto'}`}>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h2 className="text-lg font-semibold">{title}</h2>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <button
              type="button"
              className="rounded-lg border border-stone-200 px-2 py-1 text-xs text-stone-700 hover:bg-stone-50 disabled:opacity-40"
              disabled={!hasNext}
              onClick={onNext}
              title="Next email in search results"
            >
              Next
            </button>
            <button
              type="button"
              className="rounded-lg border border-stone-200 px-2 py-1 text-xs text-red-800 hover:bg-red-50 disabled:opacity-40"
              disabled={!connected}
              onClick={onDeleteNext}
              title="Trash this email and open the next"
            >
              Delete & next
            </button>
            {href && (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-emerald-800 hover:underline"
              >
                Open in Gmail ↗
              </a>
            )}
            <button
              type="button"
              className="rounded-lg border border-stone-200 px-2 py-1 text-xs text-stone-700 hover:bg-stone-50"
              onClick={onToggleExpand}
              title={expanded ? 'Exit full view (Esc)' : 'Expand to full viewport'}
            >
              {expanded ? 'Exit full view' : 'Expand'}
            </button>
          </div>
        </div>
        <p className="text-stone-500">
          {e.from_addr}
          {e.to_addr ? ` → ${e.to_addr}` : ''} ·{' '}
          {formatMailDate(e.date_iso, e.internal_date_ms)}
        </p>
        {(e.category || e.has_summary) && (
          <p className="text-xs">
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-900">
              {e.category || 'Summarized'}
              {e.category_confidence
                ? ` ${Math.round(e.category_confidence * 100)}%`
                : ''}
            </span>
          </p>
        )}
        {!zk && e.brief_summary && (
          <>
            <h3 className="font-semibold">Brief summary</h3>
            <p dangerouslySetInnerHTML={{ __html: linkifyHtml(e.brief_summary) }} />
            <h3 className="font-semibold">Key points</h3>
            <ul className="list-disc pl-5">
              {(e.key_points || []).map((p, i) => (
                <li key={i} dangerouslySetInnerHTML={{ __html: linkifyHtml(p) }} />
              ))}
            </ul>
            <h3 className="font-semibold">Details</h3>
            <p dangerouslySetInnerHTML={{ __html: linkifyHtml(e.details || '') }} />
          </>
        )}
        {zk && e.has_summary && !e.brief_summary && (
          <p className="text-stone-500">
            Zero-knowledge mode — summary content is not stored; full email below is loaded live.
          </p>
        )}
        {!e.has_summary && !e.brief_summary && (
          <p className="text-stone-500">Not summarized yet. Select and click Summarize.</p>
        )}
      </div>

      <div className="mt-2 flex min-h-0 flex-1 flex-col border-t border-stone-100 pt-3">
        <h3 className="mb-1 shrink-0 font-semibold">Full email</h3>
        {bodyLoading && !srcDoc && !text ? (
          <p className="text-stone-500">Loading message…</p>
        ) : srcDoc ? (
          <iframe
            title="Email body"
            className={
              expanded
                ? 'h-full min-h-0 w-full flex-1 rounded-lg border border-stone-200 bg-white'
                : 'min-h-[280px] w-full flex-1 rounded-lg border border-stone-200 bg-white'
            }
            sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin"
            referrerPolicy="no-referrer"
            srcDoc={srcDoc}
          />
        ) : text ? (
          <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words font-sans text-sm text-stone-800">
            {text}
          </pre>
        ) : (
          <p
            className="text-stone-500"
            dangerouslySetInnerHTML={{ __html: linkifyHtml(e.snippet || 'No body available.') }}
          />
        )}
      </div>
    </div>
  )
}

function Modal({ title, children, onClose, onAction, actionLabel, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div
        className={`w-full rounded-xl border border-stone-200 bg-white p-4 shadow-lg ${
          wide ? 'max-w-2xl' : 'max-w-md'
        }`}
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-semibold">{title}</h3>
          <button type="button" className="text-sm text-stone-500" onClick={onClose}>
            Close
          </button>
        </div>
        {children}
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm text-white"
            onClick={onAction}
          >
            {actionLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
