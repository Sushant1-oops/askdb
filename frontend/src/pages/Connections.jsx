import { useState, useEffect } from 'react';
import { Plus, Trash2, Database, RefreshCw } from 'lucide-react';
import { useConnection } from '../context/ConnectionContext';
import { disconnectDB } from '../api';
import ConnectModal from '../components/ConnectModal';
import toast from 'react-hot-toast';

export default function Connections() {
  const { connections, activeConnection, refresh, selectConnection, clearConnection } = useConnection();
  const [showConnect, setShowConnect] = useState(false);

  useEffect(() => { refresh(); }, []);

  const handleDisconnect = async (id) => {
    try {
      await disconnectDB(id);
      if (activeConnection?.connection_id === id) clearConnection();
      await refresh();
      toast.success('Disconnected');
    } catch (err) { toast.error(err.message); }
  };

  const dbIcon = (type) => {
    const map = { postgresql: '🐘', mysql: '🐬', sqlite: '📁' };
    return map[type] || '🗄️';
  };

  return (
    <>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Database Connections</h1>
          <p className="page-subtitle">Manage your database connections.</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary" onClick={refresh}><RefreshCw size={16} /> Refresh</button>
          <button className="btn btn-primary" onClick={() => setShowConnect(true)}>
            <Plus size={16} /> New Connection
          </button>
        </div>
      </div>

      {connections.length === 0 ? (
        <div className="empty-state" style={{ marginTop: 60 }}>
          <Database size={64} />
          <h3>No Connections</h3>
          <p>Add a database connection to get started.</p>
          <button className="btn btn-primary btn-lg" style={{ marginTop: 16 }}
            onClick={() => setShowConnect(true)}>
            <Plus size={18} /> Connect Database
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {connections.map(conn => (
            <div key={conn.connection_id}
              className={`connection-card ${activeConnection?.connection_id === conn.connection_id ? 'active' : ''}`}
              onClick={() => selectConnection(conn)}>
              <div className={`connection-icon ${conn.db_type}`}>
                {dbIcon(conn.db_type)}
              </div>
              <div className="connection-info">
                <div className="connection-name">{conn.database}</div>
                <div className="connection-meta">
                  <span>{conn.db_type.toUpperCase()}</span>
                  <span>ID: {conn.connection_id.slice(0, 8)}...</span>
                  <span>Since: {new Date(conn.created_at).toLocaleTimeString()}</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                {activeConnection?.connection_id === conn.connection_id && (
                  <span className="badge badge-success"><span className="badge-dot" /> Active</span>
                )}
                <button className="btn btn-danger btn-sm"
                  onClick={(e) => { e.stopPropagation(); handleDisconnect(conn.connection_id); }}>
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showConnect && <ConnectModal onClose={() => setShowConnect(false)} />}
    </>
  );
}
