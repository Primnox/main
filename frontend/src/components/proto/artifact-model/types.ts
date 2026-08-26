/**
 * Unit 6: Unified Artifact Model Types
 *
 * Tests whether Canvas and AssetViewer can share a common type.
 * Conclusion: Yes for metadata, No for lifecycle.
 */

export type ArtifactKind =
  | 'markdown' | 'python' | 'typescript' | 'html' | 'react' | 'shell'
  | 'pdf' | 'image' | 'sheets' | 'slides' | 'video' | 'text' | 'code'
  | 'unsupported';

export type ArtifactType = 'workspace' | 'asset';

export type ArtifactStatus = 'idle' | 'loading' | 'ready' | 'error' | 'editing';

export type ArtifactSource = 'generated' | 'uploaded';

/**
 * Core unified artifact shape — all artifacts conform to this.
 *
 * However, the lifecycle CANNOT be unified because:
 * - Canvas owns open/close state locally (toggle)
 * - Asset's open/close is parent-controlled (modal via prop)
 * - Their mutation models differ (versioned vs immutable)
 */
export type Artifact = {
  // Identity
  id: string;                                 // ws:xxx or asset:xxx
  type: ArtifactType;                         // Determines lifecycle

  // Content
  title: string;
  content?: string;                           // Single-file string
  files?: Record<string, string>;             // Multi-file (workspace only)

  // Preview metadata
  preview: {
    kind: ArtifactKind;
    url?: string;                             // Asset download/preview URL
    metadata?: Record<string, string | number | undefined>;       // Kind-specific (e.g., page_count)
  };

  // Versioning (workspace only)
  versions?: Array<{
    version: number;
    summary: string | null;
    created_at: number;
  }>;
  version?: number;                           // Currently viewing version
  current_version?: number;                   // Latest version

  // Capabilities — drives what UI is shown
  capabilities: {
    editable: boolean;                        // Can modify content
    versionable: boolean;                     // Has revert/history
    downloadable: boolean;                    // Has download button
    previewable: boolean;                     // Can show preview
    multiFile?: boolean;                      // Multiple files (workspace)
  };

  // Persistence and origin
  persistence: {
    source: ArtifactSource;                   // 'generated' or 'uploaded'
    created_at: number;
    origin_turn_id?: string;
    conversation_id?: string;
    sha256?: string;                          // Content hash (asset only)
  };

  // Lifecycle actions — consumers define these
  actions?: {
    open?: () => Promise<void>;
    close?: () => void;
    revert?: (version: number) => Promise<void>;
    download?: (path?: string) => void;
    edit?: (path: string, content: string) => Promise<void>;
    copy?: (text: string) => void;
  };

  // Runtime state
  status: ArtifactStatus;
  error?: string;
  busy?: boolean;
};

/**
 * What can be unified — metadata only
 */
export type ArtifactMetadata = Pick<Artifact,
  'id' | 'type' | 'title' | 'preview' | 'capabilities' | 'persistence' | 'status'
>;

/**
 * Simulated workspace data (from backend)
 */
export type WorkspaceData = {
  id: string;
  title: string;
  kind: string;
  version: number;
  current_version: number;
  files: Record<string, string>;
  versions: Array<{ version: number; summary: string | null; created_at: number }>;
};

/**
 * Simulated asset data (from backend)
 */
export type AssetData = {
  id: string;
  name: string;
  kind: ArtifactKind;
  status: 'ingesting' | 'ready' | 'failed';
  bytes: number;
  mime?: string;
  metadata?: Record<string, string | number | undefined>;
};
