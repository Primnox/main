/**
 * Unit 6 Prototype Demo
 *
 * Shows three artifact types and demonstrates why a unified lifecycle fails.
 */

import React, { useState } from 'react';
import { FileText, Download, History, X, Image, Layers } from 'lucide-react';
import { Artifact, WorkspaceData, AssetData } from './types';
import { workspaceToArtifact, pdfAssetToArtifact, slideAssetToArtifact, imageAssetToArtifact } from './converters';

// Mock data
const mockWorkspace: WorkspaceData = {
  id: 'ws:001',
  title: 'React Counter Component',
  kind: 'react',
  version: 3,
  current_version: 4,
  files: {
    'App.tsx': `import { useState } from 'react';\n\nexport default function Counter() {\n  const [count, setCount] = useState(0);\n  return (\n    <button onClick={() => setCount(count + 1)}>\n      Count: {count}\n    </button>\n  );\n}`,
  },
  versions: [
    { version: 1, summary: 'created', created_at: Date.now() - 60000 },
    { version: 2, summary: 'added state', created_at: Date.now() - 30000 },
    { version: 3, summary: 'refactored', created_at: Date.now() - 10000 },
    { version: 4, summary: 'fixed button', created_at: Date.now() },
  ],
};

const mockPdfAsset: AssetData = {
  id: 'asset:pdf-001',
  name: 'presentation.pdf',
  kind: 'pdf',
  status: 'ready',
  bytes: 2_500_000,
  mime: 'application/pdf',
  metadata: { page_count: 45, sha256: 'abc123' },
};

const mockSlideAsset: AssetData = {
  id: 'asset:slide-001',
  name: 'keynote.pptx',
  kind: 'slides',
  status: 'ready',
  bytes: 5_000_000,
  mime: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  metadata: { slide_count: 30, aspect: 16 / 9, sha256: 'def456' },
};

const mockImageAsset: AssetData = {
  id: 'asset:img-001',
  name: 'screenshot.png',
  kind: 'image',
  status: 'ready',
  bytes: 1_200_000,
  mime: 'image/png',
  metadata: { width: 2560, height: 1440, sha256: 'ghi789' },
};

/**
 * Artifact 1: Workspace (Canvas-like)
 * Shows: This CAN have a unified representation
 *        This CANNOT have unified lifecycle (local toggle state)
 */
function WorkspaceViewer() {
  const artifact = workspaceToArtifact(mockWorkspace);
  const [open, setOpen] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState(artifact.current_version);

  return (
    <div className="border border-blue-300 bg-blue-50 rounded-lg p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-mono text-sm font-semibold text-blue-900">{artifact.title}</h3>
          <p className="text-xs text-blue-700 mt-1">Type: {artifact.type} | Kind: {artifact.preview.kind}</p>
          <p className="text-xs text-blue-600 mt-1">ID: {artifact.id}</p>
        </div>
        <button
          onClick={() => setOpen(!open)}
          className="px-2 py-1 bg-blue-500 text-white text-xs rounded hover:bg-blue-600 transition"
        >
          {open ? 'Close' : 'Open'}
        </button>
      </div>

      {open && artifact.content && (
        <div className="space-y-2">
          <pre className="bg-white p-2 rounded text-xs max-h-32 overflow-y-auto border border-blue-200 text-blue-900">
            {artifact.content}
          </pre>
          {artifact.versions && (
            <div className="text-xs">
              <label className="block text-blue-700 mb-1">Version ({selectedVersion}):</label>
              <div className="flex gap-1 flex-wrap">
                {artifact.versions.map(v => (
                  <button
                    key={v.version}
                    onClick={() => setSelectedVersion(v.version)}
                    className={`px-2 py-1 rounded text-xs transition ${
                      selectedVersion === v.version
                        ? 'bg-blue-600 text-white'
                        : 'bg-white border border-blue-300 text-blue-700 hover:bg-blue-100'
                    }`}
                  >
                    v{v.version}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      <p className="text-xs text-blue-600 mt-3">
        Status: {artifact.status} | Capabilities: Edit={artifact.capabilities.editable ? 'Y' : 'N'},
        Versions={artifact.capabilities.versionable ? 'Y' : 'N'}
      </p>
    </div>
  );
}

/**
 * Artifact 2: PDF Asset
 * Shows: This CAN have a unified representation
 *        This CANNOT have unified lifecycle (modal UI, parent-controlled)
 */
function PdfViewer() {
  const artifact = pdfAssetToArtifact(mockPdfAsset);
  const [showModal, setShowModal] = useState(false);

  return (
    <div className="border border-purple-300 bg-purple-50 rounded-lg p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-mono text-sm font-semibold text-purple-900">{artifact.title}</h3>
          <p className="text-xs text-purple-700 mt-1">Type: {artifact.type} | Kind: {artifact.preview.kind}</p>
          <p className="text-xs text-purple-600 mt-1">ID: {artifact.id}</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-2 py-1 bg-purple-500 text-white text-xs rounded hover:bg-purple-600 transition"
        >
          Preview
        </button>
      </div>

      <p className="text-xs text-purple-600">
        {artifact.preview.metadata?.pages} pages | {(mockPdfAsset.bytes / 1_000_000).toFixed(1)}MB
      </p>
      <p className="text-xs text-purple-600 mt-3">
        Status: {artifact.status} | Capabilities: Edit={artifact.capabilities.editable ? 'Y' : 'N'},
        Download={artifact.capabilities.downloadable ? 'Y' : 'N'}
      </p>

      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
          <div className="bg-white rounded-lg p-6 max-w-2xl w-full max-h-[80vh] flex flex-col">
            <div className="flex justify-between items-center mb-4">
              <h4 className="font-semibold">{artifact.title}</h4>
              <button onClick={() => setShowModal(false)} className="p-1 hover:bg-gray-100 rounded">
                <X size={16} />
              </button>
            </div>
            <div className="flex-1 bg-gray-100 rounded flex items-center justify-center">
              <p className="text-sm text-gray-600">PDF Preview (iframe would render here)</p>
            </div>
            <div className="mt-4 flex gap-2">
              <a href={artifact.preview.url} download className="px-3 py-1 bg-purple-500 text-white text-xs rounded hover:bg-purple-600">
                Download
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Artifact 3: Slide Deck
 * Shows: This CAN have a unified representation
 *        This CANNOT have unified lifecycle (different rendering, multistate)
 */
function SlideViewer() {
  const artifact = slideAssetToArtifact(mockSlideAsset);
  const [showModal, setShowModal] = useState(false);
  const [currentSlide, setCurrentSlide] = useState(1);

  return (
    <div className="border border-green-300 bg-green-50 rounded-lg p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-mono text-sm font-semibold text-green-900">{artifact.title}</h3>
          <p className="text-xs text-green-700 mt-1">Type: {artifact.type} | Kind: {artifact.preview.kind}</p>
          <p className="text-xs text-green-600 mt-1">ID: {artifact.id}</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-2 py-1 bg-green-500 text-white text-xs rounded hover:bg-green-600 transition"
        >
          Preview
        </button>
      </div>

      <p className="text-xs text-green-600">
        {artifact.preview.metadata?.slides} slides | Aspect {artifact.preview.metadata?.aspect}
      </p>
      <p className="text-xs text-green-600 mt-3">
        Status: {artifact.status} | Capabilities: Edit={artifact.capabilities.editable ? 'Y' : 'N'},
        Download={artifact.capabilities.downloadable ? 'Y' : 'N'}
      </p>

      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
          <div className="bg-white rounded-lg p-6 max-w-4xl w-full max-h-[80vh] flex flex-col">
            <div className="flex justify-between items-center mb-4">
              <h4 className="font-semibold">{artifact.title}</h4>
              <button onClick={() => setShowModal(false)} className="p-1 hover:bg-gray-100 rounded">
                <X size={16} />
              </button>
            </div>
            <div className="flex-1 bg-gray-100 rounded flex items-center justify-center mb-4">
              <div className="text-center">
                <p className="text-lg font-semibold text-gray-600">Slide {currentSlide}</p>
                <p className="text-sm text-gray-500">Slide content would render here</p>
              </div>
            </div>
            <div className="flex gap-2 items-center justify-between">
              <button
                onClick={() => setCurrentSlide(Math.max(1, currentSlide - 1))}
                className="px-3 py-1 bg-gray-200 text-xs rounded hover:bg-gray-300"
              >
                Previous
              </button>
              <span className="text-xs text-gray-600">
                {currentSlide} / {artifact.preview.metadata?.slides}
              </span>
              <button
                onClick={() =>
                  setCurrentSlide(Math.min(artifact.preview.metadata?.slides ?? 30, currentSlide + 1))
                }
                className="px-3 py-1 bg-gray-200 text-xs rounded hover:bg-gray-300"
              >
                Next
              </button>
              <a href={artifact.preview.url} download className="px-3 py-1 bg-green-500 text-white text-xs rounded hover:bg-green-600">
                Download
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function ArtifactModelDemo() {
  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">Unit 6: Artifact Model Prototype</h1>
        <p className="text-gray-600 mb-6">
          Three artifact types demonstrating unified metadata representation vs. divergent lifecycle patterns.
        </p>

        <div className="space-y-6">
          <section>
            <h2 className="text-lg font-semibold mb-3 text-blue-900 flex items-center gap-2">
              <FileText size={16} /> Artifact 1: Workspace (Editable, Versioned)
            </h2>
            <p className="text-sm text-gray-700 mb-3">
              Canvas-like: Toggled open/close locally, multi-file, versioning with revert.
            </p>
            <WorkspaceViewer />
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3 text-purple-900 flex items-center gap-2">
              <Layers size={16} /> Artifact 2: PDF Asset (Read-Only)
            </h2>
            <p className="text-sm text-gray-700 mb-3">
              AssetViewer-like: Modal UI, parent-controlled, single file, no editing.
            </p>
            <PdfViewer />
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3 text-green-900 flex items-center gap-2">
              <Image size={16} /> Artifact 3: Slide Deck (Asset)
            </h2>
            <p className="text-sm text-gray-700 mb-3">
              Different rendering: Pagination, aspect ratio, slide navigation.
            </p>
            <SlideViewer />
          </section>
        </div>

        <div className="mt-8 p-4 bg-yellow-50 border border-yellow-300 rounded-lg">
          <h3 className="font-semibold text-yellow-900 mb-2">Key Findings</h3>
          <ul className="text-sm text-yellow-800 space-y-1">
            <li>✅ All three map cleanly to unified <code className="bg-white px-1">Artifact</code> type</li>
            <li>✅ Shared metadata layer works: id, type, title, preview.kind, capabilities</li>
            <li>✗ Lifecycle CANNOT be unified: Canvas owns open/close state; Asset is parent-controlled</li>
            <li>✗ UI structure differs: Canvas is <code className="bg-white px-1">&lt;aside&gt;</code>; Asset is <code className="bg-white px-1">&lt;div fixed&gt;</code></li>
            <li>✓ Preview rendering can be shared: Both use format-specific branches</li>
            <li>✓ Type detection can be unified: Combine Canvas PROSE_EXT and Asset _EXT_KIND</li>
          </ul>
        </div>

        <div className="mt-6 p-4 bg-blue-50 border border-blue-300 rounded-lg">
          <h3 className="font-semibold text-blue-900 mb-2">Lifecycle State Machines</h3>
          <div className="grid grid-cols-2 gap-4 text-xs">
            <div>
              <p className="font-semibold text-blue-900 mb-1">Canvas (Workspace)</p>
              <pre className="bg-white p-2 text-blue-700 border border-blue-200 rounded overflow-auto">
{`[Unmounted] → [Closed] ← toggle
  ↓
[Loading] → [Ready] ← can edit/revert
  ↓
[Closed] (via toggle or nav)`}</pre>
            </div>
            <div>
              <p className="font-semibold text-blue-900 mb-1">Asset</p>
              <pre className="bg-white p-2 text-blue-700 border border-blue-200 rounded overflow-auto">
{`[Asset Exists] → [Modal spawned]
  ↓
[Loading Preview] → [Ready]
  ↓
[Dismissed] (escape or backdrop)`}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
