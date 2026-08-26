import React, { useMemo, useState } from 'react';
import { Copy, Download, Check } from 'lucide-react';
import { ArtifactCard, type CardAction, type CardMetadata } from './ArtifactCard';

/**
 * CodeCard
 * Display code snippets with:
 * - Language detection/label
 * - Line count metadata
 * - Syntax highlighting (basic)
 * - Copy to clipboard
 * - Download as file
 */

export interface CodeCardProps {
  id: string;
  title: string;
  code: string;
  language?: string;
  fileName?: string;
  onCopy?: (code: string) => void;
  onDownload?: (code: string, fileName: string) => void;
  isMobile?: boolean;
}

const LANGUAGE_COLORS: Record<string, string> = {
  python: 'bg-blue-500/20 text-blue-600',
  javascript: 'bg-yellow-500/20 text-yellow-600',
  typescript: 'bg-blue-600/20 text-blue-700',
  json: 'bg-purple-500/20 text-purple-600',
  bash: 'bg-slate-500/20 text-slate-600',
  sql: 'bg-orange-500/20 text-orange-600',
  html: 'bg-red-500/20 text-red-600',
  css: 'bg-indigo-500/20 text-indigo-600',
  jsx: 'bg-cyan-500/20 text-cyan-600',
  tsx: 'bg-cyan-600/20 text-cyan-700',
};

/**
 * Simple syntax highlighting for common patterns
 * This is a basic implementation; for production, use Shiki or Highlight.js
 */
const highlightCode = (code: string, language?: string) => {
  if (!language) return code;

  // This is just a demo - in production, use a real syntax highlighter
  const keywords = {
    python: ['def', 'class', 'import', 'from', 'if', 'else', 'for', 'while', 'return', 'True', 'False', 'None'],
    javascript: ['const', 'let', 'var', 'function', 'class', 'import', 'export', 'if', 'else', 'for', 'while', 'return'],
    typescript: ['const', 'let', 'var', 'function', 'class', 'interface', 'type', 'import', 'export', 'async', 'await'],
    bash: ['echo', 'if', 'then', 'else', 'for', 'while', 'do', 'done', 'function'],
  };

  const keywordList = keywords[language.toLowerCase()] || [];
  const keywordRegex = new RegExp(`\\b(${keywordList.join('|')})\\b`, 'g');

  // Just return as-is for now - real implementation would use proper parsing
  return code;
};

export const CodeCard: React.FC<CodeCardProps> = ({
  id,
  title,
  code,
  language = 'javascript',
  fileName,
  onCopy,
  onDownload,
  isMobile = false,
}) => {
  const [copied, setCopied] = useState(false);

  const lineCount = useMemo(() => code.split('\n').length, [code]);
  const fileName_derived = fileName || `code.${language === 'python' ? 'py' : 'js'}`;

  const metadata: CardMetadata = useMemo(
    () => ({
      status: 'success',
      type: language,
      itemCount: lineCount,
    }),
    [language, lineCount]
  );

  const handleCopy = async () => {
    onCopy?.(code);
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    onDownload?.(code, fileName_derived);
    // In real implementation, trigger actual download
    const element = document.createElement('a');
    const file = new Blob([code], { type: 'text/plain' });
    element.href = URL.createObjectURL(file);
    element.download = fileName_derived;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  const actions: CardAction[] = [
    {
      id: 'copy',
      label: copied ? 'Copied!' : 'Copy',
      icon: copied ? <Check size={14} className="text-primary" /> : <Copy size={14} />,
      level: 'core',
      onClick: handleCopy,
    },
    {
      id: 'download',
      label: 'Download',
      icon: <Download size={14} />,
      level: 'common',
      onClick: handleDownload,
    },
  ];

  return (
    <ArtifactCard
      id={id}
      type="code"
      title={title}
      metadata={metadata}
      actions={actions}
      isMobile={isMobile}
    >
      {/* Code Display */}
      <div className="space-y-2">
        {/* Language Badge */}
        <div className={`inline-block px-2.5 py-1 rounded text-xs font-medium ${LANGUAGE_COLORS[language.toLowerCase()] || 'bg-gray-200 text-gray-700'}`}>
          {language.charAt(0).toUpperCase() + language.slice(1)}
        </div>

        {/* Code Block */}
        <pre className="bg-on-surface/[0.02] border border-on-surface/[0.05] rounded text-[10px] font-mono text-on-surface/80 overflow-x-auto p-3 leading-relaxed max-h-96">
          <code>{code}</code>
        </pre>

        {/* Stats */}
        <div className="flex items-center gap-3 text-[11px] text-on-surface/60">
          <span>{lineCount} line{lineCount !== 1 ? 's' : ''}</span>
          <span>{code.length} character{code.length !== 1 ? 's' : ''}</span>
        </div>
      </div>
    </ArtifactCard>
  );
};

export default CodeCard;
