import { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  Archive,
  ArrowRight,
  BookOpen,
  Braces,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Clipboard,
  Code2,
  Database,
  Download,
  FileJson,
  FileText,
  Fingerprint,
  Image,
  Layers3,
  LoaderCircle,
  Network,
  PanelRight,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  Table2,
  Upload,
  X,
} from 'lucide-react'
import { SAMPLE_TEXT } from './sample'
import type { ConversionForm, OkdDocument, OkdNode } from './types'

type InspectorTab = 'inspect' | 'assets' | 'handoff' | 'json'
type ApiState = 'checking' | 'online' | 'offline'

const DEFAULT_FORM: ConversionForm = {
  documentId: 'doc-demo-001',
  revision: '7',
  title: 'Search reliability proposal',
  spaceId: 'engineering',
  path: 'Engineering / Architecture',
  sourceUrl: 'https://example.invalid/wiki/doc-demo-001',
  visibility: 'restricted',
}

function nodeLabel(node: OkdNode): string {
  if (node.text) return node.text
  const text = node.content?.map(nodeLabel).filter(Boolean).join(' ') ?? ''
  return text || node.type.replaceAll('_', ' ')
}

function nodeIcon(type: string) {
  if (type === 'image') return <Image size={14} />
  if (type === 'table' || type === 'table_cell') return <Table2 size={14} />
  if (type === 'code_block') return <Code2 size={14} />
  if (type === 'doc') return <FileText size={14} />
  if (type === 'unsupported' || type === 'unsupported_inline') return <AlertTriangle size={14} />
  return <CircleDot size={12} />
}

function flattenNodes(root?: OkdNode): OkdNode[] {
  if (!root) return []
  return [root, ...(root.content?.flatMap(flattenNodes) ?? [])]
}

function renderInline(node: OkdNode): string {
  if (node.type === 'text') {
    let value = node.text ?? ''
    for (const mark of node.marks ?? []) {
      if (mark.type === 'bold') value = `**${value}**`
      if (mark.type === 'italic') value = `_${value}_`
      if (mark.type === 'code') value = `\`${value}\``
      if (mark.type === 'strike') value = `~~${value}~~`
      if (mark.type === 'link') value = `[${value}](${String(mark.attrs?.href ?? '')})`
    }
    return value
  }
  if (node.type === 'mention_user') return `@${String(node.attrs?.user_id ?? 'user')}`
  if (node.type === 'mention_document') {
    return `[linked document](${String(node.attrs?.url ?? '')})`
  }
  if (node.type === 'equation') return `$${String(node.attrs?.content ?? '')}$`
  if (node.type === 'unsupported_inline') return '`[unsupported inline]`'
  return node.content?.map(renderInline).join('') ?? ''
}

function projectMarkdown(node: OkdNode, depth = 0): string {
  const inline = node.content?.map(renderInline).join('') ?? ''
  const nested = node.content?.filter((child) => child.type !== 'text').map((child) => projectMarkdown(child, depth + 1)).join('') ?? ''
  switch (node.type) {
    case 'doc':
      return node.content?.map((child) => projectMarkdown(child, depth)).join('') ?? ''
    case 'heading':
      return `${'#'.repeat(Number(node.attrs?.level ?? 1))} ${inline}\n\n`
    case 'paragraph':
      return `${inline}\n\n${nested}`
    case 'list_item':
      return `${node.attrs?.kind === 'ordered' ? '1.' : '-'} ${inline}\n${nested}`
    case 'code_block':
      return `\`\`\`${String(node.attrs?.language ?? '')}\n${inline}\n\`\`\`\n\n`
    case 'blockquote':
      return `${(node.content ?? []).map((child) => projectMarkdown(child, depth)).join('').split('\n').filter(Boolean).map((line) => `> ${line}`).join('\n')}\n\n`
    case 'callout':
      return `> **Note**\n> ${(node.content ?? []).map(renderInline).join('')}\n\n${nested}`
    case 'divider':
      return '---\n\n'
    case 'image':
      return `![image](asset://${String(node.attrs?.asset_id ?? '')})\n\n`
    case 'file':
      return `[attachment](asset://${String(node.attrs?.asset_id ?? '')})\n\n`
    case 'table':
      return `<!-- table projection pending: ${(node.content ?? []).length} cells -->\n\n`
    case 'unsupported':
      return `<!-- unsupported ${String(node.attrs?.source_type ?? 'block')}: ${node.source_payload_ref ?? ''} -->\n\n`
    default:
      return nested
  }
}

function TreeNode({
  node,
  selected,
  onSelect,
  depth = 0,
}: {
  node: OkdNode
  selected?: OkdNode
  onSelect: (node: OkdNode) => void
  depth?: number
}) {
  const [open, setOpen] = useState(depth < 3)
  const children = node.content ?? []
  const hasChildren = children.length > 0
  const identity = node.id || `${node.type}-${depth}`
  const isSelected = selected === node
  return (
    <div className="tree-branch" data-depth={depth}>
      <div className={`tree-node ${isSelected ? 'is-selected' : ''} ${node.type.startsWith('unsupported') ? 'is-warning' : ''}`}>
        <button
          className="tree-toggle"
          type="button"
          aria-label={open ? 'Collapse children' : 'Expand children'}
          onClick={() => setOpen((value) => !value)}
          disabled={!hasChildren}
        >
          {hasChildren ? open ? <ChevronDown size={14} /> : <ChevronRight size={14} /> : <span className="toggle-dot" />}
        </button>
        <button className="tree-main" type="button" onClick={() => onSelect(node)}>
          <span className="tree-icon">{nodeIcon(node.type)}</span>
          <span className="tree-copy">
            <span className="tree-type">{node.type}</span>
            <span className="tree-label">{nodeLabel(node).slice(0, 120)}</span>
          </span>
          <span className="tree-id">{identity}</span>
        </button>
      </div>
      {hasChildren && open && (
        <div className="tree-children">
          {children.map((child, index) => (
            <TreeNode
              key={child.id || `${child.type}-${index}`}
              node={child}
              selected={selected}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function JsonView({ value }: { value: unknown }) {
  return <pre className="json-view">{JSON.stringify(value, null, 2)}</pre>
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    await navigator.clipboard.writeText(value)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }
  return (
    <button className="icon-button" type="button" onClick={copy} title="Copy to clipboard">
      {copied ? <Check size={15} /> : <Clipboard size={15} />}
    </button>
  )
}

export default function App() {
  const [sourceText, setSourceText] = useState(SAMPLE_TEXT)
  const [form, setForm] = useState<ConversionForm>(DEFAULT_FORM)
  const [document, setDocument] = useState<OkdDocument | null>(null)
  const [selected, setSelected] = useState<OkdNode | undefined>()
  const [tab, setTab] = useState<InspectorTab>('inspect')
  const [apiState, setApiState] = useState<ApiState>('checking')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sourceSearch, setSourceSearch] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((response) => {
        if (!response.ok) throw new Error('offline')
        setApiState('online')
      })
      .catch(() => setApiState('offline'))
  }, [])

  const nodes = useMemo(() => flattenNodes(document?.document), [document])
  const warnings = document?.conversion?.warnings ?? []
  const markdown = useMemo(() => (document ? projectMarkdown(document.document).trim() : ''), [document])
  const filteredNodeCount = useMemo(() => {
    const query = sourceSearch.trim().toLowerCase()
    if (!query) return nodes.length
    return nodes.filter((node) => `${node.type} ${node.id ?? ''} ${nodeLabel(node)}`.toLowerCase().includes(query)).length
  }, [nodes, sourceSearch])

  async function convert() {
    setBusy(true)
    setError('')
    try {
      const payload = JSON.parse(sourceText)
      const response = await fetch('/api/convert/feishu', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          payload,
          document_id: form.documentId,
          revision: form.revision,
          title: form.title,
          space_id: form.spaceId,
          path: form.path.split('/').map((part) => part.trim()).filter(Boolean),
          source_url: form.sourceUrl,
          permissions: { visibility: form.visibility },
          snapshot_ref: `workbench://${form.documentId}/revision-${form.revision}.json`,
        }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Conversion failed')
      setDocument(body)
      setSelected(body.document)
      setApiState('online')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Conversion failed')
    } finally {
      setBusy(false)
    }
  }

  function updateForm<K extends keyof ConversionForm>(key: K, value: ConversionForm[K]) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  function readFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      setSourceText(String(reader.result ?? ''))
      setError('')
    }
    reader.readAsText(file)
  }

  function downloadDocument() {
    if (!document) return
    const blob = new Blob([`${JSON.stringify(document, null, 2)}\n`], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = window.document.createElement('a')
    anchor.href = url
    anchor.download = `${form.documentId}.okd.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const bookName = document?.metadata.path[0] || 'Unsorted'
  const chapterName = document?.metadata.path.slice(1).join(' / ') || 'Root'

  return (
    <main className="workbench-shell">
      <header className="masthead">
        <div className="brand-block">
          <div className="brand-mark"><Braces size={19} strokeWidth={2.4} /></div>
          <div>
            <p className="eyebrow">Open Knowledge Document</p>
            <h1>Conversion Workbench</h1>
          </div>
        </div>
        <div className="pipeline-strip" aria-label="Conversion pipeline">
          <span className="pipeline-step is-active"><Database size={13} /> Feishu blocks</span>
          <ArrowRight size={14} />
          <span className="pipeline-step is-active"><Network size={13} /> OKD 0.1</span>
          <ArrowRight size={14} />
          <span className="pipeline-step"><BookOpen size={13} /> BookStack</span>
        </div>
        <div className={`api-badge ${apiState}`}>
          <span className="status-light" />
          {apiState === 'checking' ? 'Checking API' : apiState === 'online' ? 'Converter online' : 'Converter offline'}
        </div>
      </header>

      <section className="stat-rail">
        <div><span>Schema</span><strong>{document?.schema_version ?? '0.1.0-draft'}</strong></div>
        <div><span>Blocks</span><strong>{Math.max(0, nodes.length - 1).toString().padStart(2, '0')}</strong></div>
        <div><span>Assets</span><strong>{String(document?.assets.length ?? 0).padStart(2, '0')}</strong></div>
        <div className={warnings.length ? 'has-warning' : ''}><span>Warnings</span><strong>{String(warnings.length).padStart(2, '0')}</strong></div>
        <div><span>Visibility</span><strong>{String(document?.permissions?.visibility ?? form.visibility)}</strong></div>
      </section>

      <section className="workspace-grid">
        <aside className="source-panel panel">
          <div className="panel-heading">
            <div>
              <span className="panel-number">01</span>
              <h2>Source specimen</h2>
            </div>
            <button className="icon-button" type="button" onClick={() => fileInput.current?.click()} title="Import JSON">
              <Upload size={15} />
            </button>
            <input ref={fileInput} className="sr-only" type="file" accept="application/json,.json" onChange={readFile} />
          </div>

          <div className="source-fields">
            <label><span>Document ID</span><input value={form.documentId} onChange={(e) => updateForm('documentId', e.target.value)} /></label>
            <label><span>Revision</span><input value={form.revision} onChange={(e) => updateForm('revision', e.target.value)} /></label>
            <label className="field-wide"><span>Title</span><input value={form.title} onChange={(e) => updateForm('title', e.target.value)} /></label>
            <label><span>Space</span><input value={form.spaceId} onChange={(e) => updateForm('spaceId', e.target.value)} /></label>
            <label>
              <span>Visibility</span>
              <select value={form.visibility} onChange={(e) => updateForm('visibility', e.target.value as ConversionForm['visibility'])}>
                <option value="unknown">Unknown</option>
                <option value="restricted">Restricted</option>
                <option value="organization">Organization</option>
                <option value="public">Public</option>
              </select>
            </label>
            <label className="field-wide"><span>Path <i>separate with /</i></span><input value={form.path} onChange={(e) => updateForm('path', e.target.value)} /></label>
          </div>

          <div className="editor-label">
            <span><FileJson size={14} /> Feishu block response</span>
            <div>
              <button type="button" onClick={() => setSourceText(SAMPLE_TEXT)}>Reset sample</button>
              <CopyButton value={sourceText} />
            </div>
          </div>
          <textarea
            className="source-editor"
            aria-label="Feishu block response JSON"
            value={sourceText}
            spellCheck={false}
            onChange={(event) => setSourceText(event.target.value)}
          />
          {error && <div className="error-banner"><X size={14} /> {error}</div>}
          <button className="convert-button" type="button" onClick={convert} disabled={busy || apiState === 'offline'}>
            {busy ? <LoaderCircle className="spin" size={17} /> : <Play size={16} fill="currentColor" />}
            {busy ? 'Converting specimen…' : 'Run conversion'}
            <span>⌘ ↵</span>
          </button>
        </aside>

        <section className="tree-panel panel">
          <div className="panel-heading">
            <div>
              <span className="panel-number">02</span>
              <h2>Normalized tree</h2>
            </div>
            <div className="tree-search">
              <Search size={14} />
              <input placeholder="Find node…" value={sourceSearch} onChange={(event) => setSourceSearch(event.target.value)} />
              <span>{filteredNodeCount}</span>
            </div>
          </div>
          {document ? (
            <div className="tree-scroll">
              <div className="document-identity">
                <span>Canonical ID</span>
                <strong>{document.id}</strong>
                <small>{document.metadata.path.join(' / ')}</small>
              </div>
              <TreeNode node={document.document} selected={selected} onSelect={setSelected} />
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-orbit"><Layers3 size={30} /></div>
              <h3>No normalized tree yet</h3>
              <p>Run the sample conversion to inspect block fidelity, provenance and downstream projections.</p>
              <button type="button" onClick={convert}><Play size={14} /> Convert sample</button>
            </div>
          )}
        </section>

        <aside className="inspector-panel panel">
          <div className="panel-heading inspector-heading">
            <div>
              <span className="panel-number">03</span>
              <h2>Inspector</h2>
            </div>
            {document && <button className="icon-button" type="button" onClick={downloadDocument} title="Download OKD JSON"><Download size={15} /></button>}
          </div>
          <nav className="inspector-tabs" aria-label="Inspector views">
            <button className={tab === 'inspect' ? 'is-active' : ''} onClick={() => setTab('inspect')}><PanelRight size={13} /> Inspect</button>
            <button className={tab === 'assets' ? 'is-active' : ''} onClick={() => setTab('assets')}><Archive size={13} /> Assets</button>
            <button className={tab === 'handoff' ? 'is-active' : ''} onClick={() => setTab('handoff')}><BookOpen size={13} /> Handoff</button>
            <button className={tab === 'json' ? 'is-active' : ''} onClick={() => setTab('json')}><Braces size={13} /> JSON</button>
          </nav>

          <div className="inspector-scroll">
            {!document && <div className="inspector-placeholder">Select a converted document to begin examination.</div>}
            {document && tab === 'inspect' && (
              <>
                <div className="specimen-card selected-specimen">
                  <div className="specimen-kicker">Selected node</div>
                  <div className="specimen-title">{nodeIcon(selected?.type ?? 'doc')} {selected?.type ?? 'doc'}</div>
                  <div className="specimen-id">{selected?.id || 'root document'}</div>
                </div>
                <div className="inspection-group">
                  <h3><Fingerprint size={14} /> Provenance</h3>
                  <dl>
                    <div><dt>Source</dt><dd>{String(document.source.type)}</dd></div>
                    <div><dt>Revision</dt><dd>{String(document.source.revision)}</dd></div>
                    <div><dt>Snapshot</dt><dd>{String(document.source_snapshot.storage_ref)}</dd></div>
                  </dl>
                </div>
                {selected?.marks?.length ? (
                  <div className="inspection-group">
                    <h3>Marks</h3>
                    <div className="tag-row">{selected.marks.map((mark, index) => <span key={`${mark.type}-${index}`}>{mark.type}</span>)}</div>
                  </div>
                ) : null}
                <div className="inspection-group code-group">
                  <div className="group-title"><h3>Node payload</h3><CopyButton value={JSON.stringify(selected ?? document.document, null, 2)} /></div>
                  <JsonView value={selected ?? document.document} />
                </div>
                {warnings.length > 0 && (
                  <div className="inspection-group warning-group">
                    <h3><AlertTriangle size={14} /> Conversion warnings</h3>
                    <ol>{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ol>
                  </div>
                )}
              </>
            )}

            {document && tab === 'assets' && (
              <div className="asset-view">
                <div className="section-intro">
                  <h3>Asset manifest</h3>
                  <p>Binary bytes are intentionally absent until the asset pipeline downloads and hashes them.</p>
                </div>
                {document.assets.length === 0 ? <div className="minor-empty">No asset references in this document.</div> : document.assets.map((asset) => (
                  <article className="asset-card" key={asset.id}>
                    <div className="asset-icon">{asset.media_type.startsWith('image') ? <Image size={18} /> : <FileText size={18} />}</div>
                    <div>
                      <strong>{asset.filename || asset.source_asset_id || asset.id}</strong>
                      <span>{asset.media_type}</span>
                      <code>{asset.storage_ref}</code>
                    </div>
                    <span className={`asset-status ${asset.download_status}`}>{asset.download_status}</span>
                  </article>
                ))}
              </div>
            )}

            {document && tab === 'handoff' && (
              <div className="handoff-view">
                <div className="section-intro">
                  <h3>BookStack projection</h3>
                  <p>This is a dry projection. A future adapter will own API calls and target IDs.</p>
                </div>
                <div className="route-map">
                  <div><span>Book</span><strong>{bookName}</strong></div>
                  <ArrowRight size={15} />
                  <div><span>Chapter</span><strong>{chapterName}</strong></div>
                  <ArrowRight size={15} />
                  <div><span>Page</span><strong>{document.metadata.title}</strong></div>
                </div>
                <div className="adapter-contract">
                  <h4><ShieldCheck size={15} /> Adapter boundary</h4>
                  <dl>
                    <div><dt>Mode</dt><dd>read-only mirror</dd></div>
                    <div><dt>External ID</dt><dd>{document.id}</dd></div>
                    <div><dt>Update guard</dt><dd>source revision {String(document.source.revision)}</dd></div>
                    <div><dt>Assets</dt><dd>{document.assets.length} references</dd></div>
                    <div><dt>Permission</dt><dd>{String(document.permissions?.visibility ?? 'unknown')}</dd></div>
                  </dl>
                </div>
                <div className="markdown-preview">
                  <div className="group-title"><h4>Markdown projection</h4><CopyButton value={markdown} /></div>
                  <pre>{markdown || 'No Markdown-compatible content.'}</pre>
                </div>
              </div>
            )}

            {document && tab === 'json' && (
              <div className="full-json">
                <div className="group-title"><h3>Complete OKD document</h3><CopyButton value={JSON.stringify(document, null, 2)} /></div>
                <JsonView value={document} />
              </div>
            )}
          </div>
        </aside>
      </section>

      <footer className="workbench-footer">
        <div><RefreshCw size={12} /> Source remains authoritative</div>
        <div><ShieldCheck size={12} /> No silent loss</div>
        <div><Fingerprint size={12} /> Every node traceable</div>
        <span>OKD laboratory build · 0.1.0</span>
      </footer>
    </main>
  )
}
