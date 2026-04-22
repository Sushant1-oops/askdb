import { ChevronDown, ChevronUp, Download } from 'lucide-react';
import { useState } from 'react';

export default function ResultTable({ columns, rows, title, onExport }) {
  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState('asc');

  if (!columns || columns.length === 0) return null;

  const handleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('asc'); }
  };

  const sorted = sortCol ? [...rows].sort((a, b) => {
    const va = a[sortCol], vb = b[sortCol];
    if (va == null) return 1; if (vb == null) return -1;
    const cmp = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb));
    return sortDir === 'asc' ? cmp : -cmp;
  }) : rows;

  return (
    <div className="result-panel animate-in">
      <div className="result-panel-header">
        <div className="result-panel-title">
          {title || 'Query Results'}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="result-stats">
            <span className="result-stat"><strong>{rows.length}</strong> rows</span>
            <span className="result-stat"><strong>{columns.length}</strong> columns</span>
          </div>
          {onExport && (
            <div style={{ display: 'flex', gap: 6 }}>
              {['csv', 'excel', 'pdf'].map(fmt => (
                <button key={fmt} className="btn btn-ghost btn-sm"
                  onClick={() => onExport(fmt)} title={`Export as ${fmt.toUpperCase()}`}>
                  <Download size={14} /> {fmt.toUpperCase()}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="result-panel-body">
        <div className="table-wrapper">
          <table className="result-table">
            <thead>
              <tr>
                <th style={{ width: 50, textAlign: 'center' }}>#</th>
                {columns.map(col => (
                  <th key={col} onClick={() => handleSort(col)}
                    style={{ cursor: 'pointer', userSelect: 'none' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      {col}
                      {sortCol === col && (sortDir === 'asc'
                        ? <ChevronUp size={14} /> : <ChevronDown size={14} />)}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, i) => (
                <tr key={i}>
                  <td style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>{i + 1}</td>
                  {columns.map(col => (
                    <td key={col} title={row[col] != null ? String(row[col]) : ''}>
                      {row[col] != null ? String(row[col]) : <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>NULL</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
