import React, { useMemo } from 'react';
import { Download, Copy } from 'lucide-react';
import { ArtifactCard, type CardAction, type CardMetadata } from './ArtifactCard';

/**
 * TableCard
 * Display tabular data with:
 * - Column headers
 * - Row count metadata
 * - Export to CSV/JSON
 * - Horizontal scroll on mobile
 */

export interface TableCardProps {
  id: string;
  title: string;
  headers: string[];
  rows: (string | number | boolean | null)[][];
  onExportCSV?: (data: string) => void;
  onExportJSON?: (data: string) => void;
  isMobile?: boolean;
}

const rowsToCSV = (headers: string[], rows: (string | number | boolean | null)[][]): string => {
  const headerLine = headers.map((h) => `"${h}"`).join(',');
  const dataLines = rows.map((row) =>
    row.map((cell) => {
      if (cell === null || cell === undefined) return '""';
      if (typeof cell === 'string') return `"${cell.replace(/"/g, '""')}"`;
      return String(cell);
    }).join(',')
  );
  return [headerLine, ...dataLines].join('\n');
};

const rowsToJSON = (headers: string[], rows: (string | number | boolean | null)[][]): string => {
  const data = rows.map((row) => {
    const obj: Record<string, any> = {};
    headers.forEach((header, index) => {
      obj[header] = row[index];
    });
    return obj;
  });
  return JSON.stringify(data, null, 2);
};

export const TableCard: React.FC<TableCardProps> = ({
  id,
  title,
  headers,
  rows,
  onExportCSV,
  onExportJSON,
  isMobile = false,
}) => {
  const metadata: CardMetadata = useMemo(
    () => ({
      status: 'success',
      itemCount: rows.length,
      type: `${rows.length} rows × ${headers.length} columns`,
    }),
    [rows.length, headers.length]
  );

  const csvData = useMemo(() => rowsToCSV(headers, rows), [headers, rows]);
  const jsonData = useMemo(() => rowsToJSON(headers, rows), [headers, rows]);

  const actions: CardAction[] = useMemo(() => {
    const acts: CardAction[] = [];

    if (onExportCSV) {
      acts.push({
        id: 'export-csv',
        label: 'Export CSV',
        icon: <Download size={14} />,
        level: 'common',
        onClick: () => {
          onExportCSV(csvData);
          // Trigger download
          const element = document.createElement('a');
          const file = new Blob([csvData], { type: 'text/csv' });
          element.href = URL.createObjectURL(file);
          element.download = `${title.replace(/\s+/g, '_')}.csv`;
          document.body.appendChild(element);
          element.click();
          document.body.removeChild(element);
        },
      });
    }

    acts.push({
      id: 'copy-json',
      label: 'Copy JSON',
      icon: <Copy size={14} />,
      level: 'common',
      onClick: () => {
        navigator.clipboard.writeText(jsonData);
      },
    });

    if (onExportJSON) {
      acts.push({
        id: 'export-json',
        label: 'Export JSON',
        icon: <Download size={14} />,
        level: 'advanced',
        onClick: () => {
          onExportJSON(jsonData);
          // Trigger download
          const element = document.createElement('a');
          const file = new Blob([jsonData], { type: 'application/json' });
          element.href = URL.createObjectURL(file);
          element.download = `${title.replace(/\s+/g, '_')}.json`;
          document.body.appendChild(element);
          element.click();
          document.body.removeChild(element);
        },
      });
    }

    return acts;
  }, [onExportCSV, onExportJSON, csvData, jsonData, title]);

  const truncateCell = (value: string | number | boolean | null, maxLength: number = 50): string => {
    if (value === null || value === undefined) return '—';
    const str = String(value);
    return str.length > maxLength ? str.slice(0, maxLength) + '…' : str;
  };

  return (
    <ArtifactCard
      id={id}
      type="table"
      title={title}
      metadata={metadata}
      actions={actions}
      isMobile={isMobile}
    >
      {/* Table */}
      <div className={isMobile ? 'overflow-x-auto' : ''}>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-on-surface/[0.09]">
              {headers.map((header, idx) => (
                <th
                  key={idx}
                  className="px-3 py-2 text-left font-semibold text-on-surface/80 bg-on-surface/[0.02] text-xs"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 50).map((row, rowIdx) => (
              <tr key={rowIdx} className={`border-b border-on-surface/[0.05] ${rowIdx % 2 === 0 ? '' : 'bg-on-surface/[0.01]'}`}>
                {row.map((cell, cellIdx) => (
                  <td key={cellIdx} className="px-3 py-2 text-xs text-on-surface/70 font-mono">
                    {truncateCell(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination info */}
      {rows.length > 50 && (
        <div className="mt-3 text-xs text-on-surface/60 text-center">
          Showing 50 of {rows.length} rows
        </div>
      )}

      {/* Preview stats */}
      <div className="mt-3 flex gap-3 text-[11px] text-on-surface/60">
        <span>Columns: {headers.length}</span>
        <span>Rows: {rows.length}</span>
        <span>Total cells: {headers.length * rows.length}</span>
      </div>
    </ArtifactCard>
  );
};

export default TableCard;
