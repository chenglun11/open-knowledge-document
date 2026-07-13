export type Mark = {
  type: string
  attrs?: Record<string, unknown>
}

export type OkdNode = {
  id?: string
  type: string
  attrs?: Record<string, unknown>
  text?: string
  marks?: Mark[]
  content?: OkdNode[]
  source_payload_ref?: string
}

export type Asset = {
  id: string
  media_type: string
  filename?: string
  size?: number
  storage_ref: string
  source_asset_id?: string
  download_status?: 'pending' | 'downloaded' | 'failed' | 'unavailable'
  sha256?: string
}

export type OkdDocument = {
  schema_version: string
  id: string
  source: Record<string, unknown>
  metadata: {
    title: string
    path: string[]
    status: string
    [key: string]: unknown
  }
  permissions?: Record<string, unknown>
  document: OkdNode
  assets: Asset[]
  source_snapshot: Record<string, unknown>
  conversion?: {
    converter?: string
    converter_version?: string
    converted_at?: string
    warnings?: string[]
  }
}

export type ConversionForm = {
  documentId: string
  revision: string
  title: string
  spaceId: string
  path: string
  sourceUrl: string
  visibility: 'public' | 'organization' | 'restricted' | 'unknown'
}
