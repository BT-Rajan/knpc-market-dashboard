import { useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import { EmailRecipientOut, EmailTemplateOut, EmailCredentialsOut, EmailLogOut, EmailSendResponse } from '../../types'

const SUB_TABS = ['Recipients', 'Templates', 'Send', 'Gmail Settings', 'Send Log'] as const
type SubTab = (typeof SUB_TABS)[number]

const inputStyle = { width: '100%', padding: '8px', border: '1px solid var(--border)', borderRadius: 4 }

// --- Recipients ---

function Recipients() {
  const [recipients, setRecipients] = useState<EmailRecipientOut[]>([])
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)

  function reload() {
    api.get<EmailRecipientOut[]>('/api/admin/email/recipients').then(setRecipients)
  }
  useEffect(reload, [])

  async function add() {
    setError(null)
    try {
      await api.post('/api/admin/email/recipients', { email, name: name || null })
      setEmail('')
      setName('')
      reload()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to add recipient')
    }
  }

  async function toggle(r: EmailRecipientOut) {
    await api.patch(`/api/admin/email/recipients/${r.id}`, { active: !r.active })
    reload()
  }

  async function remove(r: EmailRecipientOut) {
    await api.delete(`/api/admin/email/recipients/${r.id}`)
    reload()
  }

  return (
    <div>
      <div className="panel" style={{ padding: 18, marginBottom: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>Add to distribution list</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 12, alignItems: 'end' }}>
          <div className="field">
            <label>Email</label>
            <input style={inputStyle} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" />
          </div>
          <div className="field">
            <label>Name (optional)</label>
            <input style={inputStyle} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <button className="btn btn-brass" onClick={add} disabled={!email.trim()}>Add</button>
        </div>
        {error && <div style={{ color: 'var(--negative)', fontSize: 13, marginTop: 10 }}>{error}</div>}
      </div>

      <div className="panel">
        {recipients.length === 0 ? (
          <div style={{ padding: 20, color: 'var(--text-dim)', fontSize: 13 }}>No recipients yet.</div>
        ) : (
          recipients.map((r, i) => (
            <div key={r.id}>
              {i > 0 && <hr className="hairline" />}
              <div style={{ padding: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontSize: 14, color: r.active ? 'var(--text)' : 'var(--text-dim)' }}>
                    {r.name ? `${r.name} · ` : ''}{r.email}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn" onClick={() => toggle(r)}>{r.active ? 'Disable' : 'Enable'}</button>
                  <button className="btn btn-danger" onClick={() => remove(r)}>Delete</button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

// --- Templates ---

function emptyTemplateForm() {
  return { name: '', subject: '', body_html: '' }
}

function Templates() {
  const [templates, setTemplates] = useState<EmailTemplateOut[]>([])
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState(emptyTemplateForm())
  const [error, setError] = useState<string | null>(null)

  function reload() {
    api.get<EmailTemplateOut[]>('/api/admin/email/templates').then(setTemplates)
  }
  useEffect(reload, [])

  function edit(t: EmailTemplateOut) {
    setEditingId(t.id)
    setForm({ name: t.name, subject: t.subject, body_html: t.body_html })
  }

  function cancel() {
    setEditingId(null)
    setForm(emptyTemplateForm())
  }

  async function save() {
    setError(null)
    try {
      if (editingId != null) {
        await api.patch(`/api/admin/email/templates/${editingId}`, form)
      } else {
        await api.post('/api/admin/email/templates', form)
      }
      cancel()
      reload()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to save template')
    }
  }

  async function remove(t: EmailTemplateOut) {
    await api.delete(`/api/admin/email/templates/${t.id}`)
    reload()
  }

  return (
    <div>
      <div className="panel" style={{ marginBottom: 20 }}>
        {templates.length === 0 ? (
          <div style={{ padding: 20, color: 'var(--text-dim)', fontSize: 13 }}>No templates yet.</div>
        ) : (
          templates.map((t, i) => (
            <div key={t.id}>
              {i > 0 && <hr className="hairline" />}
              <div style={{ padding: 14, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14 }}>{t.name}</div>
                  <div className="mono" style={{ fontSize: 11.5, color: 'var(--text-dim)' }}>{t.subject}</div>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <button className="btn" onClick={() => edit(t)}>Edit</button>
                  <button className="btn btn-danger" onClick={() => remove(t)}>Delete</button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="panel" style={{ padding: 18 }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>{editingId != null ? 'Edit template' : 'New template'}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="field">
            <label>Name</label>
            <input style={inputStyle} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="field">
            <label>Subject (supports {'{{placeholders}}'})</label>
            <input style={inputStyle} value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} />
          </div>
          <div className="field">
            <label>Body HTML (supports {'{{placeholders}}'} — e.g. {'{{recipient_name}}'}, {'{{quarter}}'}, {'{{year}}'})</label>
            <textarea
              value={form.body_html}
              onChange={(e) => setForm({ ...form, body_html: e.target.value })}
              style={{ ...inputStyle, minHeight: 160, fontFamily: 'monospace', fontSize: 13 }}
            />
          </div>
          {error && <div style={{ color: 'var(--negative)', fontSize: 13 }}>{error}</div>}
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="btn btn-brass" onClick={save} disabled={!form.name.trim() || !form.subject.trim() || !form.body_html.trim()}>
              {editingId != null ? 'Save changes' : 'Create template'}
            </button>
            {editingId != null && <button className="btn" onClick={cancel}>Cancel</button>}
          </div>
        </div>
      </div>
    </div>
  )
}

// --- Gmail settings ---

function GmailSettings() {
  const [status, setStatus] = useState<EmailCredentialsOut | null>(null)
  const [address, setAddress] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function reload() {
    api.get<EmailCredentialsOut>('/api/admin/email/credentials').then(setStatus)
  }
  useEffect(reload, [])

  async function save() {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const body: Record<string, string> = {}
      if (address.trim()) body.gmail_address = address.trim()
      if (password.trim()) body.gmail_app_password = password.trim()
      const res = await api.put<EmailCredentialsOut>('/api/admin/email/credentials', body)
      setStatus(res)
      setPassword('')
      setMessage('Saved.')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to save')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel" style={{ padding: 20, maxWidth: 480 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>Gmail sender account</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div className="field">
          <label>
            Status {status && (status.configured
              ? <span className="positive" style={{ marginLeft: 6 }}>configured ({status.gmail_address})</span>
              : <span style={{ color: 'var(--text-dim)', marginLeft: 6 }}>not configured</span>)}
          </label>
        </div>
        <div className="field">
          <label>Gmail address</label>
          <input style={inputStyle} value={address} onChange={(e) => setAddress(e.target.value)} placeholder={status?.gmail_address || 'you@gmail.com'} />
        </div>
        <div className="field">
          <label>App password (Google Account → Security → 2-Step Verification → App passwords)</label>
          <input
            type="password"
            style={inputStyle}
            value={password}
            onChange={(e) => setPassword(e.target.value.replace(/\s/g, ''))}
            placeholder={status?.configured ? '•••••••••••• (enter to replace)' : '16-character app password'}
          />
        </div>
        <button className="btn btn-brass" onClick={save} disabled={busy || (!address.trim() && !password.trim())}>
          {busy ? 'Saving…' : 'Save'}
        </button>
        {message && <div style={{ fontSize: 13, color: 'var(--positive)' }}>{message}</div>}
        {error && <div style={{ fontSize: 13, color: 'var(--negative)' }}>{error}</div>}
      </div>
    </div>
  )
}

// --- Send ---

function Send() {
  const [recipients, setRecipients] = useState<EmailRecipientOut[]>([])
  const [templates, setTemplates] = useState<EmailTemplateOut[]>([])
  const [selectedRecipients, setSelectedRecipients] = useState<number[]>([])
  const [templateId, setTemplateId] = useState<number | null>(null)
  const [variablesText, setVariablesText] = useState('quarter=Q1\nyear=2026')
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<EmailSendResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<EmailRecipientOut[]>('/api/admin/email/recipients').then(setRecipients)
    api.get<EmailTemplateOut[]>('/api/admin/email/templates').then((ts) => {
      setTemplates(ts)
      if (ts.length > 0) setTemplateId(ts[0].id)
    })
  }, [])

  function toggleRecipient(id: number) {
    setSelectedRecipients((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  function selectAllActive() {
    setSelectedRecipients(recipients.filter((r) => r.active).map((r) => r.id))
  }

  function parseVariables(): Record<string, string> {
    const vars: Record<string, string> = {}
    for (const line of variablesText.split('\n')) {
      const idx = line.indexOf('=')
      if (idx > 0) vars[line.slice(0, idx).trim()] = line.slice(idx + 1).trim()
    }
    return vars
  }

  async function send() {
    if (!templateId || selectedRecipients.length === 0) return
    setSending(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.post<EmailSendResponse>('/api/admin/email/send', {
        template_id: templateId,
        recipient_ids: selectedRecipients,
        variables: parseVariables(),
      })
      setResult(res)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Send failed')
    } finally {
      setSending(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 560 }}>
      <div className="panel" style={{ padding: 18 }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>Template</div>
        <select style={inputStyle} value={templateId ?? ''} onChange={(e) => setTemplateId(Number(e.target.value))}>
          {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </div>

      <div className="panel" style={{ padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div className="eyebrow">Recipients</div>
          <button className="btn" onClick={selectAllActive}>Select all active</button>
        </div>
        {recipients.length === 0 ? (
          <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>No recipients on the distribution list yet.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {recipients.map((r) => (
              <label key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, opacity: r.active ? 1 : 0.5 }}>
                <input
                  type="checkbox"
                  checked={selectedRecipients.includes(r.id)}
                  onChange={() => toggleRecipient(r.id)}
                  disabled={!r.active}
                />
                {r.name ? `${r.name} · ${r.email}` : r.email}{!r.active && ' (disabled)'}
              </label>
            ))}
          </div>
        )}
      </div>

      <div className="panel" style={{ padding: 18 }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>Template variables (one per line: key=value)</div>
        <textarea
          value={variablesText}
          onChange={(e) => setVariablesText(e.target.value)}
          style={{ ...inputStyle, minHeight: 90, fontFamily: 'monospace', fontSize: 13 }}
        />
      </div>

      <button className="btn btn-brass" onClick={send} disabled={sending || !templateId || selectedRecipients.length === 0} style={{ padding: '10px' }}>
        {sending ? 'Sending…' : `Send to ${selectedRecipients.length} recipient(s)`}
      </button>

      {error && <div style={{ color: 'var(--negative)', fontSize: 13 }}>{error}</div>}

      {result && (
        <div className="panel" style={{ padding: 16, fontSize: 13 }}>
          <div style={{ marginBottom: 8 }}>{result.sent} sent, {result.failed} failed</div>
          {result.results.map((r, i) => (
            <div key={i} style={{ color: r.status === 'success' ? 'var(--positive)' : 'var(--negative)' }}>
              {r.recipient}: {r.status}{r.message ? ` — ${r.message}` : ''}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// --- Send log ---

function SendLog() {
  const [logs, setLogs] = useState<EmailLogOut[]>([])
  useEffect(() => {
    api.get<EmailLogOut[]>('/api/admin/email/logs').then(setLogs)
  }, [])

  return (
    <div className="panel">
      {logs.length === 0 ? (
        <div style={{ padding: 20, color: 'var(--text-dim)', fontSize: 13 }}>No sends logged yet.</div>
      ) : (
        logs.map((l, i) => (
          <div key={i}>
            {i > 0 && <hr className="hairline" />}
            <div style={{ padding: 12, fontSize: 13 }}>
              <span className="mono" style={{ color: 'var(--text-dim)' }}>{new Date(l.sent_at).toLocaleString()}</span>
              {' · '}
              <span style={{ color: l.status === 'success' ? 'var(--positive)' : 'var(--negative)' }}>{l.status}</span>
              {' · '}{l.template_name} → {l.recipient}
              {l.message && <div style={{ color: 'var(--text-dim)', fontSize: 12, marginTop: 4 }}>{l.message}</div>}
            </div>
          </div>
        ))
      )}
    </div>
  )
}

export default function Email() {
  const [tab, setTab] = useState<SubTab>('Recipients')

  return (
    <div>
      <div style={{ display: 'flex', gap: 4, marginBottom: 20 }}>
        {SUB_TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)} className={tab === t ? 'btn btn-brass' : 'btn'}>
            {t}
          </button>
        ))}
      </div>
      {tab === 'Recipients' && <Recipients />}
      {tab === 'Templates' && <Templates />}
      {tab === 'Send' && <Send />}
      {tab === 'Gmail Settings' && <GmailSettings />}
      {tab === 'Send Log' && <SendLog />}
    </div>
  )
}
