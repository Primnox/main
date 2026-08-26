import React from 'react';
import { FileText, Folder, Plus, Edit2 } from 'lucide-react';

export interface FileTreeItem {
  id: string;
  path: string;
  name: string;
  type: 'file' | 'folder';
  isModified?: boolean;
  isNew?: boolean;
  children?: FileTreeItem[];
  depth?: number;
}

interface FileTreeMarkersProps {
  items: FileTreeItem[];
  onFileClick?: (path: string) => void;
  touchCount?: number;
}

export const FileTreeMarkers: React.FC<FileTreeMarkersProps> = ({
  items,
  onFileClick,
  touchCount = 0,
}) => {
  const [expandedFolders, setExpandedFolders] = React.useState<Set<string>>(new Set());

  const toggleFolder = (id: string) => {
    const newExpanded = new Set(expandedFolders);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedFolders(newExpanded);
  };

  const renderItem = (item: FileTreeItem, depth: number = 0) => {
    const isFolder = item.type === 'folder';
    const isExpanded = expandedFolders.has(item.id);
    const hasChildren = item.children && item.children.length > 0;

    return (
      <div key={item.id}>
        <div
          className="flex items-center gap-2 px-2 py-1 cursor-pointer hover:bg-blue-50 rounded"
          style={{ marginLeft: `${depth * 12}px` }}
          onClick={() => {
            if (isFolder && hasChildren) {
              toggleFolder(item.id);
            }
            if (!isFolder) {
              onFileClick?.(item.path);
            }
          }}
        >
          {/* Folder toggle */}
          {isFolder && hasChildren ? (
            <span className={`text-gray-400 text-xs transition-transform ${isExpanded ? 'rotate-90' : ''}`}>
              ▶
            </span>
          ) : (
            <span className="w-4" />
          )}

          {/* Icon */}
          {isFolder ? (
            <Folder size={16} className="text-gray-600" />
          ) : (
            <FileText size={16} className="text-gray-500" />
          )}

          {/* Name */}
          <span className="text-sm text-gray-800 flex-1">{item.name}</span>

          {/* Status indicator */}
          {item.isNew && (
            <div className="flex items-center gap-1">
              <Plus size={14} className="text-green-600" />
              <span className="text-xs text-green-600 font-medium">new</span>
            </div>
          )}
          {item.isModified && !item.isNew && (
            <div className="flex items-center gap-1">
              <Edit2 size={14} className="text-blue-600" />
              <span className="text-xs text-blue-600 font-medium">modified</span>
            </div>
          )}
        </div>

        {/* Children */}
        {isFolder && isExpanded && hasChildren && (
          <div>
            {item.children!.map((child) => renderItem(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      {/* Header with count */}
      {touchCount > 0 && (
        <div className="px-4 py-2 bg-blue-50 border-b border-gray-200 flex items-center justify-between">
          <span className="text-sm font-medium text-gray-800">
            {touchCount} file{touchCount !== 1 ? 's' : ''} modified
          </span>
          <span className="text-xs text-gray-600">by this turn</span>
        </div>
      )}

      {/* File tree */}
      <div className="p-2 max-h-96 overflow-y-auto">
        {items.map((item) => renderItem(item))}
      </div>
    </div>
  );
};

export default FileTreeMarkers;
