import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import api from '../services/api'
import { getLoginUrl } from '../utils/apiUrl'
import AppsMenu from './AppsMenu'
import {
  escapeHtml,
  formatMailDate,
  gmailOpenUrl,
  linkifyHtml,
  shortFrom,
  snippetWords,
} from '../utils/format'
import {
  clearAllZkSummariesForUser,
  loadZkSummaries,
  saveZkSummaries,
  zkStorageKey,
} from '../utils/zkSummaries'

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
  /** 'summary' = from-click view; 'full' = subject-click view */
  const [detailPane, setDetailPane] = useState('summary')
  const [bodyLoading, setBodyLoading] = useState(false)
  const [detailExpanded, setDetailExpanded] = useState(false)
  const detailFetchSeq = useRef(0)
  const [prompts, setPrompts] = useState([])
  const [promptSelect, setPromptSelect] = useState('')
  const [labels, setLabels] = useState([])
  const [labelMode, setLabelMode] = useState(null) // 'labels' | 'move'
  const [labelOpen, setLabelOpen] = useState(false)
  const [labelSearch, setLabelSearch] = useState('')
  const [checkedLabels, setCheckedLabels] = useState(() => new Set())
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveLabel, setSaveLabel] = useState('')
  const [processOpen, setProcessOpen] = useState(false)
  const [processPrompt, setProcessPrompt] = useState('')
  const [progress, setProgress] = useState(null)
  const [prefsOpen, setPrefsOpen] = useState(false)
  const [zkConfirmOpen, setZkConfirmOpen] = useState(false)
  const [zkEnabling, setZkEnabling] = useState(false)
  const [schedulesOpen, setSchedulesOpen] = useState(false)
  const [searchHelpOpen, setSearchHelpOpen] = useState(false)
  const [schedules, setSchedules] = useState([])
  const [schedLabel, setSchedLabel] = useState('')
  const [schedHours, setSchedHours] = useState('24')
  const [schedForce, setSchedForce] = useState(false)
  const [forceSummarize, setForceSummarize] = useState(false)
  const sessionSummarized = useRef(new Set())
  const [sessionSummaries, setSessionSummaries] = useState({})
  const sessionSummariesRef = useRef({})
  const zkHydratedKey = useRef('')
  const zkPersistEnabled = useRef(false)
  const previewTimer = useRef(null)
  const shiftHeldRef = useRef(false)

  sessionSummariesRef.current = sessionSummaries

  const preferText = (...vals) => {
    for (const v of vals) {
      if (typeof v === 'string' && v.trim()) return v
    }
    return ''
  }
  const preferList = (...vals) => {
    for (const v of vals) {
      if (Array.isArray(v) && v.length) return v
    }
    return []
  }

  /** Merge list/detail row with session/local ZK summaries; never let empty API fields wipe them. */
  const mergeSessionSummary = (row, apiEmail = null, summaries = sessionSummariesRef.current) => {
    if (!row?.gmail_id) return row
    const api = apiEmail && typeof apiEmail === 'object' ? apiEmail : {}
    const s = summaries[row.gmail_id] || {}
    const brief_summary = preferText(s.brief_summary, row.brief_summary, api.brief_summary)
    const key_points = preferList(s.key_points, row.key_points, api.key_points)
    const details = preferText(s.details, row.details, api.details)
    const category = preferText(s.category, row.category, api.category)
    const category_confidence =
      s.category_confidence ||
      row.category_confidence ||
      api.category_confidence ||
      0
    return {
      ...row,
      ...api,
      brief_summary,
      key_points,
      details,
      category,
      category_confidence,
      has_summary: !!(
        brief_summary ||
        category ||
        s.has_summary ||
        row.has_summary ||
        api.has_summary
      ),
    }
  }

  const activeAccount = useMemo(() => {
    if (!status?.accounts?.length) return null
    return (
      status.accounts.find((a) => a.id === status.active_account_id) ||
      status.accounts[0]
    )
  }, [status])

  const zkUserKey = user?.id || user?.pk || user?.email || 'anon'
  const zkAccountKey = activeAccount?.id || ''
  const zeroKnowledge = !!status?.preferences?.zero_knowledge

  // Hydrate ZK summaries from localStorage for this user + account.
  useEffect(() => {
    if (!zeroKnowledge || !zkAccountKey) {
      zkHydratedKey.current = ''
      zkPersistEnabled.current = false
      return
    }
    const key = zkStorageKey(zkUserKey, zkAccountKey)
    const loaded = loadZkSummaries(zkUserKey, zkAccountKey)
    zkPersistEnabled.current = false
    zkHydratedKey.current = key
    sessionSummariesRef.current = loaded
    setSessionSummaries(loaded)
    sessionSummarized.current = new Set(Object.keys(loaded))
    setEmails((prev) => prev.map((e) => mergeSessionSummary(e, null, loaded)))
    setDetail((d) =>
      d?.kind === 'email'
        ? { kind: 'email', email: mergeSessionSummary(d.email, null, loaded) }
        : d,
    )
    // Avoid the same-tick persist effect writing {} over localStorage.
    const t = window.setTimeout(() => {
      zkPersistEnabled.current = true
    }, 0)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zeroKnowledge, zkUserKey, zkAccountKey])

  // Persist ZK summaries in this browser only.
  useEffect(() => {
    if (!zeroKnowledge || !zkAccountKey || !zkPersistEnabled.current) return
    const key = zkStorageKey(zkUserKey, zkAccountKey)
    if (zkHydratedKey.current !== key) return
    saveZkSummaries(zkUserKey, zkAccountKey, sessionSummaries)
  }, [sessionSummaries, zeroKnowledge, zkUserKey, zkAccountKey])

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
      const merged = (data.emails || []).map((e) => mergeSessionSummary(e, null))
      setEmails(merged)
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
    setLabelSearch('')
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

  const selectableLabels = useMemo(() => {
    const q = labelSearch.trim().toLowerCase()
    return labels
      .filter((l) => l.type === 'user' || ['STARRED', 'IMPORTANT'].includes(l.id))
      .filter((l) => !q || (l.name || '').toLowerCase().includes(q))
  }, [labels, labelSearch])

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

  const hasLocalSummaryText = (gmailId) => {
    if (!gmailId) return false
    const row = emails.find((x) => x.gmail_id === gmailId)
    const local = sessionSummariesRef.current[gmailId]
    return !!(
      preferText(row?.brief_summary, local?.brief_summary) ||
      (local?.key_points || row?.key_points || []).length ||
      preferText(row?.details, local?.details)
    )
  }

  const runSummarize = async () => {
    const ids = selectedIds()
    if (!ids.length) return

    // ZK (and local cache): skip IDs that already have summary text in this browser.
    // Server cannot see localStorage, so skipping must happen here unless Force is on.
    const toRun = forceSummarize
      ? ids
      : ids.filter((id) => {
          if (zeroKnowledge) return !hasLocalSummaryText(id)
          const row = emails.find((x) => x.gmail_id === id)
          return !(row?.has_summary || hasLocalSummaryText(id))
        })
    const skippedLocal = ids.length - toRun.length
    if (!toRun.length) {
      flash(
        `All ${ids.length} selected already have summaries. Enable Force to re-summarize.`,
        'ok',
      )
      return
    }

    flash(
      skippedLocal
        ? `Summarizing ${toRun.length} (skipped ${skippedLocal} already summarized)…`
        : 'Summarizing…',
    )
    setProgress({ status: 'processing', message: 'Starting…', percentage: 0 })
    try {
      const start = await api.json(`${API}/summarize/`, {
        method: 'POST',
        body: JSON.stringify({
          gmail_ids: toRun,
          account_id: activeAccount?.id,
          force: !!forceSummarize,
        }),
      })
      const done = await pollTask(start.task_id)
      if (done.status === 'failed') throw new Error(done.message || 'Summarize failed')
      const incoming = done.summaries || {}
      const incomingIds = Object.keys(incoming)
      if (incomingIds.length) {
        const nextMap = { ...sessionSummariesRef.current, ...incoming }
        sessionSummariesRef.current = nextMap
        zkPersistEnabled.current = true
        setSessionSummaries(nextMap)
        incomingIds.forEach((id) => sessionSummarized.current.add(id))
      }
      setEmails((prev) =>
        prev.map((e) => {
          const s = incoming[e.gmail_id]
          if (!s) return e
          return mergeSessionSummary({ ...e, ...s, has_summary: true }, null, {
            [e.gmail_id]: s,
          })
        }),
      )
      setDetail((d) => {
        if (d?.kind !== 'email' || !d.email?.gmail_id) return d
        const s = incoming[d.email.gmail_id]
        if (!s) return d
        return {
          kind: 'email',
          email: mergeSessionSummary({ ...d.email, ...s, has_summary: true }, null, {
            [d.email.gmail_id]: s,
          }),
        }
      })
      if (incomingIds.length) setDetailPane('summary')
      const nDone = done.done?.length || 0
      const nSkip = (done.skipped?.length || 0) + skippedLocal
      if (zeroKnowledge && nDone > 0 && !incomingIds.length) {
        flash(
          `Job finished (${nDone}) but no summary text was returned for this browser. Check celery-worker, then Summarize again.`,
          'error',
        )
      } else {
        flash(`Summarized ${nDone}, skipped ${nSkip}.`, 'ok')
      }
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
    return data
  }

  const requestZeroKnowledge = (wantOn) => {
    const currentlyOn = !!status?.preferences?.zero_knowledge
    if (!wantOn) {
      if (!currentlyOn) return
      savePrefs({ zero_knowledge: false }).catch((err) =>
        flash(err.message || 'Could not update preferences', 'error'),
      )
      return
    }
    if (currentlyOn) return
    setPrefsOpen(false)
    setZkConfirmOpen(true)
  }

  const confirmEnableZeroKnowledge = async () => {
    if (zkEnabling) return
    setZkEnabling(true)
    try {
      const data = await api.json(`${API}/preferences/`, {
        method: 'PATCH',
        body: JSON.stringify({
          zero_knowledge: true,
          confirm_scrub: true,
        }),
      })
      setStatus((s) => (s ? { ...s, preferences: data } : s))
      clearAllZkSummariesForUser(zkUserKey)
      sessionSummarized.current = new Set()
      sessionSummariesRef.current = {}
      setSessionSummaries({})
      if (zkAccountKey) {
        zkHydratedKey.current = zkStorageKey(zkUserKey, zkAccountKey)
        zkPersistEnabled.current = true
      }
      setEmails((prev) =>
        prev.map((e) => ({
          ...e,
          has_summary: false,
          brief_summary: '',
          key_points: [],
          details: '',
          category: '',
          category_confidence: 0,
        })),
      )
      setDetail((f) =>
        f?.kind === 'email'
          ? {
              kind: 'email',
              email: {
                ...f.email,
                has_summary: false,
                brief_summary: '',
                key_points: [],
                details: '',
                category: '',
                category_confidence: 0,
              },
            }
          : f,
      )
      const n = data?.scrubbed?.summaries_deleted ?? 0
      flash(`Zero-knowledge enabled. Deleted ${n} stored summaries.`, 'ok')
      setZkConfirmOpen(false)
    } catch (err) {
      flash(err.message || 'Could not enable zero-knowledge', 'error')
    } finally {
      setZkEnabling(false)
    }
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
    // Prefer current list row + any local ZK summary immediately.
    setDetail({
      kind: 'email',
      email: mergeSessionSummary(row),
    })
    setBodyLoading(true)
    try {
      const q = activeAccount?.id
        ? `?account_id=${encodeURIComponent(activeAccount.id)}`
        : ''
      const data = await api.json(`${API}/emails/${encodeURIComponent(row.gmail_id)}/${q}`)
      if (seq !== detailFetchSeq.current) return
      // ZK API omits summary text — mergeSessionSummary keeps local/session fields.
      setDetail({
        kind: 'email',
        email: mergeSessionSummary(row, data.email || {}),
      })
    } catch (e) {
      if (seq !== detailFetchSeq.current) return
      flash(String(e.message || e), 'error')
    } finally {
      if (seq === detailFetchSeq.current) setBodyLoading(false)
    }
  }

  const focusEmailRow = (row, idx, pane = 'summary') => {
    if (!row) return
    setFocusId(row.gmail_id)
    setSelected(new Set([row.gmail_id]))
    setAnchorIndex(idx)
    setDetailPane(pane === 'full' ? 'full' : 'summary')
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
    focusEmailRow(next, idx + 1, detailPane)
  }

  const deleteAndNext = async (fromId) => {
    if (!fromId) return
    const idx = emails.findIndex((e) => e.gmail_id === fromId)
    const next = idx >= 0 ? emails[idx + 1] : null
    const pane = detailPane
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
        focusEmailRow(next, idx, pane) // after removal, next sits at old idx
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

  const openRowPane = (ev, idx, id, pane) => {
    ev.stopPropagation()
    const row = emails.find((x) => x.gmail_id === id)
    if (shiftHeldRef.current && anchorIndex != null) {
      setFocusId(id)
      setDetailPane(pane === 'full' ? 'full' : 'summary')
      if (row) loadEmailDetail(row)
      selectRange(idx, true)
      return
    }
    focusEmailRow(row, idx, pane)
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
      <header className="mb-1 border-b border-stone-200 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-4">
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-emerald-900">Gmail Assistant</h1>
              <p className="text-sm text-stone-500">
                Search · select · act · summarize only what you choose
              </p>
            </div>
            <nav className="flex items-center gap-2 text-sm">
              <AppsMenu current="gmail" />
            </nav>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span
              className={`inline-block h-2.5 w-2.5 rounded-full ${
                connected ? 'bg-emerald-600' : 'bg-stone-300'
              }`}
              title={connected ? 'Connected' : 'Not connected'}
            />
            <button type="button" className="text-stone-600 hover:text-stone-900" onClick={openSchedules}>
              Schedules
            </button>
            <button type="button" className="text-stone-600 hover:text-stone-900" onClick={() => setPrefsOpen(true)}>
              Prefs
            </button>
            <span className="hidden text-stone-400 sm:inline">|</span>
            <span className="max-w-[160px] truncate text-stone-500" title={user?.email}>
              {user?.username || user?.email}
            </span>
            <button
              type="button"
              className="rounded-lg border border-stone-200 px-3 py-1 text-stone-700 hover:bg-stone-50"
              onClick={logout}
            >
              Log out
            </button>
          </div>
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

      <section className="grid grid-cols-1 gap-2 md:grid-cols-[1fr_auto_auto]">
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
          aria-label="Search help"
          title="Search syntax help"
          onClick={() => setSearchHelpOpen(true)}
          className="flex h-10 w-10 items-center justify-center self-center rounded-full border border-stone-200 bg-white text-sm font-semibold text-stone-600 hover:bg-stone-50"
        >
          ?
        </button>
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
        <label className="flex items-center gap-1 text-xs text-stone-600" title="Re-run LLM even if a summary already exists (needed to refresh ZK local cache)">
          <input
            type="checkbox"
            checked={forceSummarize}
            onChange={(e) => setForceSummarize(e.target.checked)}
          />
          Force
        </label>
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
            : 'grid h-[70vh] min-h-[420px] grid-cols-1 gap-3 lg:grid-cols-[1.4fr_1fr]'
        }
      >
        <section className="min-h-0 overflow-auto rounded-xl border border-stone-200 bg-white">
          {!emails.length ? (
            <p className="p-4 text-sm text-stone-500">No messages. Try a search.</p>
          ) : (
            emails.map((e, idx) => {
              const local = sessionSummaries[e.gmail_id]
              const hasLocalText = !!(
                preferText(e.brief_summary, local?.brief_summary) ||
                (local?.key_points || []).length ||
                preferText(e.details, local?.details)
              )
              // ZK: "Summarized" only when this browser has summary text.
              // Non-ZK: server has_summary or local/session text.
              const summarized = zeroKnowledge
                ? hasLocalText
                : !!(
                    e.has_summary ||
                    hasLocalText ||
                    sessionSummarized.current.has(e.gmail_id)
                  )
              const categoryLabel =
                preferText(e.category, local?.category) || ''
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
                    className="grid grid-cols-[9rem_1fr_auto] gap-x-3 gap-y-0.5 px-2 py-2 text-left text-sm"
                    onMouseDown={noteShift}
                  >
                    <button
                      type="button"
                      className="truncate text-left font-semibold hover:text-emerald-800 hover:underline"
                      onClick={(ev) => openRowPane(ev, idx, e.gmail_id, 'summary')}
                      title="Show summary · Shift+click to select a range"
                    >
                      {shortFrom(e.from_addr)}
                    </button>
                    <button
                      type="button"
                      className="truncate text-left font-semibold hover:text-emerald-800 hover:underline"
                      onClick={(ev) => openRowPane(ev, idx, e.gmail_id, 'full')}
                      title="Show full email · Shift+click to select a range"
                      dangerouslySetInnerHTML={{
                        __html: escapeHtml(e.subject || '(no subject)'),
                      }}
                    />
                    <span className="text-xs text-stone-500">
                      {formatMailDate(e.date_iso, e.internal_date_ms)}
                    </span>
                    <button
                      type="button"
                      className="col-span-2 truncate text-left text-xs text-stone-500 hover:text-emerald-800"
                      onClick={(ev) => openRowPane(ev, idx, e.gmail_id, 'summary')}
                      title="Show summary"
                      dangerouslySetInnerHTML={{
                        __html: linkifyHtml(snippetWords(e.snippet)),
                      }}
                    />
                    {summarized && (
                      <span className="col-span-2 text-[0.7rem] text-emerald-800">
                        Summarized{categoryLabel ? ` · ${categoryLabel}` : ''}
                      </span>
                    )}
                    {zeroKnowledge && !summarized && (e.category || e.has_category) && (
                      <span className="col-span-2 text-[0.7rem] text-stone-500">
                        Categorized{e.category ? ` · ${e.category}` : ''} · no local summary
                      </span>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </section>

        <section className="flex min-h-0 flex-col rounded-xl border border-stone-200 bg-white p-4 text-sm">
          {!detail && (
            <p className="text-stone-500">
              Click <span className="font-medium text-stone-700">from</span> for summary,{' '}
              <span className="font-medium text-stone-700">subject</span> for full email — or
              Summarize / Process selected.
            </p>
          )}
          {detail?.kind === 'process' && (
            <div className="min-h-0 flex-1 space-y-2 overflow-auto">
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
            <div className="flex min-h-0 flex-1 flex-col">
              <EmailDetail
                email={detail.email}
                zk={!!prefs.zero_knowledge}
                pane={detailPane}
                onPaneChange={setDetailPane}
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
            </div>
          )}
        </section>
      </main>

      {detailExpanded && detail?.kind === 'email' && (
        <div className="fixed inset-0 z-40 flex flex-col bg-[#f6f1e8] p-3 md:p-4">
          <div className="mx-auto flex h-full w-full max-w-[1600px] flex-col rounded-xl border border-stone-200 bg-white p-4 shadow-lg">
            <EmailDetail
              email={detail.email}
              zk={!!prefs.zero_knowledge}
              pane={detailPane}
              onPaneChange={setDetailPane}
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
          onClose={() => {
            setLabelOpen(false)
            setLabelSearch('')
          }}
          actionLabel={labelMode === 'move' ? 'Move' : 'Apply'}
          onAction={applyLabels}
        >
          {labelMode === 'move' && (
            <p className="mb-2 text-xs text-stone-500">
              Adds selected label(s) and archives (removes from Inbox).
            </p>
          )}
          <input
            type="search"
            autoFocus
            className="mb-2 w-full rounded-lg border border-stone-200 px-2 py-1.5 text-sm"
            placeholder="Search labels…"
            value={labelSearch}
            onChange={(e) => setLabelSearch(e.target.value)}
          />
          {checkedLabels.size > 0 && (
            <p className="mb-2 text-xs text-stone-500">
              {checkedLabels.size} selected
              {labelSearch.trim() ? ' (selection kept while filtering)' : ''}
            </p>
          )}
          <div className="max-h-64 space-y-1 overflow-auto">
            {selectableLabels.length === 0 ? (
              <p className="py-3 text-center text-sm text-stone-500">No labels match.</p>
            ) : (
              selectableLabels.map((l) => (
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
              ))
            )}
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
          <div className="mb-3 flex items-start gap-3 text-sm">
            <button
              type="button"
              role="switch"
              aria-checked={!!prefs.zero_knowledge}
              onClick={() => requestZeroKnowledge(!prefs.zero_knowledge)}
              className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors ${
                prefs.zero_knowledge ? 'bg-emerald-700' : 'bg-stone-300'
              }`}
            >
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                  prefs.zero_knowledge ? 'left-5' : 'left-0.5'
                }`}
              />
            </button>
            <div>
              <p className="font-medium text-stone-800">Zero-knowledge</p>
              <p className="text-xs text-stone-500">
                Do not store email content on the server. Summaries stay in this browser only.
                Enabling deletes server-stored summaries and clears local browser cache for your accounts.
              </p>
            </div>
          </div>
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
          <p className="mt-2 text-xs text-stone-500">Default context 8192. ZK default is off.</p>
        </Modal>
      )}

      {zkConfirmOpen && (
        <Modal
          title="Enable zero-knowledge?"
          onClose={() => {
            if (zkEnabling) return
            setZkConfirmOpen(false)
            setPrefsOpen(true)
          }}
          actionLabel={zkEnabling ? 'Deleting…' : 'Delete & enable'}
          onAction={confirmEnableZeroKnowledge}
          actionClassName="bg-amber-800 hover:bg-amber-900"
          actionDisabled={zkEnabling}
          zClassName="z-[60]"
        >
          <div className="space-y-2 text-sm text-stone-700">
            <p className="font-medium text-amber-900">
              This permanently deletes stored Gmail Assistant data for your account.
            </p>
            <ul className="list-disc space-y-1 pl-5 text-stone-600">
              <li>All saved email summaries on the server (text, categories, snippets)</li>
              <li>Stored process/summarize job results on this server</li>
              <li>Local browser-cached summaries for your Gmail accounts on this device</li>
            </ul>
            <p className="text-stone-600">
              Your Gmail mailbox, OAuth connection, saved prompts, and schedules are kept.
              After this, new summaries are kept only in this browser, not on the server.
            </p>
            <p className="text-xs text-stone-500">This cannot be undone.</p>
          </div>
        </Modal>
      )}

      {searchHelpOpen && (
        <Modal
          title="Search help"
          onClose={() => setSearchHelpOpen(false)}
          actionLabel="Close"
          onAction={() => setSearchHelpOpen(false)}
          wide
        >
          <SearchHelpContent />
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

function SearchHelpContent() {
  const examples = [
    {
      title: 'Natural language',
      rows: [
        ['find email from smithsonian, borowitz in inbox', 'Multiple senders (comma = OR)'],
        ['Get emails from the last day in inbox', 'Inbox + last 24h'],
        ['from alice@example.com last 7 days', 'One sender + newer_than:7d'],
        ['emails from the past 12 hours', 'newer_than:12h'],
      ],
    },
    {
      title: 'Senders with commas in the name',
      rows: [
        ['q:from:"Hello, Money"', 'Quoted from: — NL commas split senders'],
        ['q:from:news@hellomoney.com', 'Prefer email address when you know it'],
      ],
    },
    {
      title: 'Raw Gmail operators',
      rows: [
        ['q:in:inbox newer_than:2d', 'Prefix q: to pass operators through'],
        ['q:from:boss@co.com subject:invoice', 'Combine operators'],
        ['q:label:receipts after:2026/01/01', 'Label + date'],
        ['in:inbox from:alice@co.com', 'Operators without q: (no find/get/show)'],
      ],
    },
    {
      title: 'UI qualifier fields',
      rows: [
        ['Days = 7', 'Adds newer_than:7d (overrides NL time window)'],
        ['Start / End date', 'Adds after: / before: (YYYY/MM/DD)'],
        ['Keyword', 'Subject/body term; multi-word is quoted'],
      ],
    },
  ]
  return (
    <div className="max-h-[70vh] space-y-4 overflow-auto text-sm">
      <p className="text-stone-600">
        Search builds a Gmail <code className="rounded bg-stone-100 px-1">q=</code> string
        (rule-based, not LLM). Use the live <span className="font-medium">Gmail query</span> preview
        under the prompt to verify. Ctrl/Cmd+Enter runs search.
      </p>
      {examples.map((section) => (
        <div key={section.title}>
          <h4 className="mb-1.5 font-semibold text-stone-800">{section.title}</h4>
          <ul className="space-y-2">
            {section.rows.map(([ex, note]) => (
              <li key={ex} className="rounded-lg border border-stone-100 bg-stone-50/80 px-3 py-2">
                <code className="block break-all text-emerald-900">{ex}</code>
                <span className="mt-0.5 block text-xs text-stone-500">{note}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <p className="text-xs text-stone-500">
        Tip: for display names that contain a comma, always use{' '}
        <code className="rounded bg-stone-100 px-1">q:from:&quot;Exact Name&quot;</code>.
      </p>
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
  pane = 'summary',
  onPaneChange,
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
  const hasSummaryText = !!(e.brief_summary || '').trim()
  const showFull = pane === 'full'
  const showSummary = pane === 'summary'

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="shrink-0 space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h2 className="text-lg font-semibold">{title}</h2>
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-stone-200 text-stone-700 hover:bg-stone-50 disabled:opacity-40"
              disabled={!hasNext}
              onClick={onNext}
              title="Next email"
              aria-label="Next email"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
            <button
              type="button"
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-stone-200 text-red-800 hover:bg-red-50 disabled:opacity-40"
              disabled={!connected}
              onClick={onDeleteNext}
              title="Delete & next"
              aria-label="Delete and next"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3m-7 0h8"
                />
              </svg>
            </button>
            {href && (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-stone-200 text-emerald-800 hover:bg-emerald-50"
                title="Open in Gmail"
                aria-label="Open in Gmail"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                  />
                </svg>
              </a>
            )}
            <button
              type="button"
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-stone-200 text-stone-700 hover:bg-stone-50"
              onClick={onToggleExpand}
              title={expanded ? 'Exit full view (Esc)' : 'Expand'}
              aria-label={expanded ? 'Exit full view' : 'Expand'}
            >
              {expanded ? (
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25"
                  />
                </svg>
              ) : (
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15"
                  />
                </svg>
              )}
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
      </div>

      {showSummary && (
        <div className="min-h-0 flex-1 space-y-2 overflow-auto border-t border-stone-100 pt-3">
          {hasSummaryText ? (
            <>
              {zk && (
                <p className="text-xs text-amber-800">
                  Zero-knowledge — summary kept in this browser only; not stored on the server.
                </p>
              )}
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
          ) : zk && (e.category || e.has_category || e.has_summary) ? (
            <p className="text-stone-500">
              This message was categorized on the server, but summary text is not stored there in
              zero-knowledge mode and is missing from this browser. Select it and click Summarize
              again to load the summary locally.
            </p>
          ) : (
            <p className="text-stone-500">
              Not summarized yet. Select and click Summarize — or click the subject for the full
              email.
            </p>
          )}
        </div>
      )}

      {showFull && (
        <div className="flex min-h-0 flex-1 flex-col border-t border-stone-100 pt-3">
          <h3 className="mb-1 shrink-0 font-semibold">Full email</h3>
          {bodyLoading && !srcDoc && !text ? (
            <p className="text-stone-500">Loading message…</p>
          ) : srcDoc ? (
            <iframe
              title="Email body"
              className="h-full min-h-0 w-full flex-1 rounded-lg border border-stone-200 bg-white"
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
      )}
    </div>
  )
}

function Modal({
  title,
  children,
  onClose,
  onAction,
  actionLabel,
  wide,
  actionClassName,
  actionDisabled,
  zClassName,
}) {
  return (
    <div
      className={`fixed inset-0 flex items-center justify-center bg-black/30 p-4 ${zClassName || 'z-50'}`}
      onClick={onClose}
    >
      <div
        className={`w-full rounded-xl border border-stone-200 bg-white p-4 shadow-lg ${
          wide ? 'max-w-2xl' : 'max-w-md'
        }`}
        onClick={(ev) => ev.stopPropagation()}
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
            disabled={actionDisabled}
            className={`rounded-lg px-3 py-1.5 text-sm text-white disabled:opacity-50 ${
              actionClassName || 'bg-emerald-700'
            }`}
            onClick={onAction}
          >
            {actionLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
