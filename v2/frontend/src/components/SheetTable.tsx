

export function SheetTable({ sheet }: { sheet: any }) {
  return (
    <div className="flex-1 min-h-0 overflow-auto custom-scrollbar p-3">
      <table className="w-full text-[12px] border-collapse">
        {sheet.header?.length > 0 && (
          <thead className="sticky top-0">
            <tr>
              {sheet.header.map((h: string, i: number) => (
                <th key={i} className="text-left font-semibold px-2.5 py-1.5 bg-surface border-b border-on-surface/[0.14] whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {sheet.rows.map((row: string[], r: number) => (
            <tr key={r} className="hover:bg-on-surface/[0.03]">
              {row.map((cell, c) => (
                <td key={c} className="px-2.5 py-1 border-b border-on-surface/[0.05] text-on-surface/75 whitespace-nowrap">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {sheet.truncated && (
        <p className="px-label pt-3">
          Showing {sheet.rows.length} of {sheet.total_rows} rows.
        </p>
      )}
    </div>
  );
}
