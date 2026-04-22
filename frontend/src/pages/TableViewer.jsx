import { useState, useEffect } from 'react';
import { Table2, Database, RefreshCw } from 'lucide-react';
import { useConnection } from '../context/ConnectionContext';
import { getTableData, exportTable } from '../api';
import ResultTable from '../components/ResultTable';
import toast from 'react-hot-toast';

export default function TableViewer() {
  const { activeConnection, tables } = useConnection();
  const [selectedTable, setSelectedTable] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [limit, setLimit] = useState(100);

  useEffect(() => {
    if (tables.length > 0 && !selectedTable) setSelectedTable(tables[0]);
  }, [tables]);

  useEffect(() => {
    if (selectedTable && activeConnection) fetchData();
  }, [selectedTable, limit]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const result = await getTableData(activeConnection.connection_id, selectedTable, limit);
      setData(result);
    } catch (err) { toast.error(err.message); setData(null); }
    setLoading(false);
  };

  const handleExport = async (format) => {
    try {
      const blob = await exportTable(activeConnection.connection_id, selectedTable, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${selectedTable}.${format === 'excel' ? 'xlsx' : format}`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`Exported ${selectedTable} as ${format.toUpperCase()}`);
    } catch (err) { toast.error(`Export failed: ${err.message}`); }
  };

  if (!activeConnection) {
    return (
      <div className="empty-state" style={{ marginTop: 80 }}>
        <Database size={64} />
        <h3>No Database Connected</h3>
        <p>Connect to a database first to browse tables.</p>
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Table Viewer</h1>
        <p className="page-subtitle">Browse and export data from your database tables.</p>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap', alignItems: 'center' }}>
        <div className="form-group" style={{ minWidth: 200 }}>
          <select className="form-select" value={selectedTable}
            onChange={e => setSelectedTable(e.target.value)}>
            <option value="">Select a table...</option>
            {tables.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="form-group" style={{ minWidth: 120 }}>
          <select className="form-select" value={limit}
            onChange={e => setLimit(Number(e.target.value))}>
            {[25, 50, 100, 250, 500, 1000].map(n => (
              <option key={n} value={n}>{n} rows</option>
            ))}
          </select>
        </div>
        <button className="btn btn-secondary" onClick={fetchData} disabled={!selectedTable || loading}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {loading && <div className="loader"><div className="spinner" /> Loading table data...</div>}

      {data && data.success && data.columns && (
        <ResultTable columns={data.columns} rows={data.rows}
          title={<><Table2 size={16} /> {selectedTable}</>}
          onExport={handleExport} />
      )}

      {data && !data.success && (
        <div className="card" style={{ textAlign: 'center', padding: 40, color: 'var(--error)' }}>
          Error: {data.error}
        </div>
      )}

      {!data && !loading && selectedTable && (
        <div className="empty-state">
          <Table2 size={64} />
          <h3>Select a Table</h3>
          <p>Choose a table from the dropdown above to view its data.</p>
        </div>
      )}
    </>
  );
}
