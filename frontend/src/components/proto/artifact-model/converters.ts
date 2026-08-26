/**
 * Convert backend types to unified Artifact model
 *
 * This proves that metadata unification works.
 * The lifecycle, however, cannot be unified.
 */

import { Artifact, WorkspaceData, AssetData } from './types';

export function workspaceToArtifact(ws: WorkspaceData): Artifact {
  const behind = ws.version !== ws.current_version;
  return {
    id: ws.id,
    type: 'workspace',
    title: ws.title,
    content: Object.values(ws.files)[0] ?? '',
    files: ws.files,
    preview: {
      kind: ws.kind as any,
      metadata: { fileCount: Object.keys(ws.files).length },
    },
    versions: ws.versions,
    version: ws.version,
    current_version: ws.current_version,
    capabilities: {
      editable: true,
      versionable: true,
      downloadable: true,
      previewable: true,
      multiFile: Object.keys(ws.files).length > 1,
    },
    persistence: {
      source: 'generated',
      created_at: ws.versions[0]?.created_at ?? Date.now(),
      origin_turn_id: 'turn:12345',
      conversation_id: 'conv:67890',
    },
    status: 'ready',
    error: behind ? `Showing v${ws.version}, current is v${ws.current_version}` : undefined,
  };
}

/**
 * Example: Asset (PDF document)
 */
export function pdfAssetToArtifact(asset: AssetData): Artifact {
  return {
    id: asset.id,
    type: 'asset',
    title: asset.name,
    preview: {
      kind: 'pdf',
      url: `/api/assets/${asset.id}/download`,
      metadata: {
        pages: asset.metadata?.page_count,
        bytes: asset.bytes,
      },
    },
    capabilities: {
      editable: false,
      versionable: false,
      downloadable: true,
      previewable: true,
    },
    persistence: {
      source: 'uploaded',
      created_at: Date.now(),
      sha256: asset.metadata?.sha256 as string,
      conversation_id: 'conv:67890',
    },
    status: asset.status === 'ready' ? 'ready' : 'loading',
    error: asset.status === 'failed' ? asset.metadata?.error as string : undefined,
  };
}

/**
 * Example: Asset (Slide deck)
 */
export function slideAssetToArtifact(asset: AssetData): Artifact {
  return {
    id: asset.id,
    type: 'asset',
    title: asset.name,
    preview: {
      kind: 'slides',
      url: `/api/assets/${asset.id}/download`,
      metadata: {
        slides: asset.metadata?.slide_count ?? 12,
        aspect: asset.metadata?.aspect ?? (16 / 9),
      },
    },
    capabilities: {
      editable: false,
      versionable: false,
      downloadable: true,
      previewable: true,
    },
    persistence: {
      source: 'uploaded',
      created_at: Date.now(),
      sha256: asset.metadata?.sha256 as string,
      conversation_id: 'conv:67890',
    },
    status: asset.status === 'ready' ? 'ready' : 'loading',
  };
}

/**
 * Example: Asset (Image)
 */
export function imageAssetToArtifact(asset: AssetData): Artifact {
  return {
    id: asset.id,
    type: 'asset',
    title: asset.name,
    preview: {
      kind: 'image',
      url: `/api/assets/${asset.id}/download?inline=1`,
      metadata: {
        bytes: asset.bytes,
        mime: asset.mime,
      },
    },
    capabilities: {
      editable: false,
      versionable: false,
      downloadable: true,
      previewable: true,
    },
    persistence: {
      source: 'uploaded',
      created_at: Date.now(),
      sha256: asset.metadata?.sha256 as string,
      conversation_id: 'conv:67890',
    },
    status: asset.status === 'ready' ? 'ready' : 'loading',
  };
}
