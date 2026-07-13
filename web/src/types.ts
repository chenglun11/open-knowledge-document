export interface DocumentSummary {
  id: string; source_type: string; source_document_id: string; space_id: string; title: string
  path: string[]; status: string; visibility: string; revision: string; content_hash: string
  warning_count: number; asset_count: number; snapshot_ref: string; created_at: string; updated_at: string
}
export interface Job {
  id: string; kind: string; status: 'running' | 'succeeded' | 'failed'; source_document_id: string
  document_id: string; processed: number; warning_count: number; error: string; started_at: string; completed_at?: string
}
export interface Asset {
  document_id: string; id: string; source_asset_id: string; media_type: string; filename: string
  storage_ref: string; download_status: string; sha256: string; size: number; updated_at: string
}
export interface AuditEvent { id: number; event_type: string; actor: string; target_id: string; detail: Record<string, unknown>; created_at: string }
export interface Overview {
  documents: number; active_documents: number; warnings: number; assets: number; pending_assets: number; failed_jobs: number
  spaces: Array<{ space_id: string; documents: number }>; recent_jobs: Job[]; recent_documents: DocumentSummary[]
}
export interface ImportForm {
  document_id: string; revision: string; title: string; space_id: string; path: string[]; source_url: string
  permissions: { visibility: string }; payload: unknown
}
