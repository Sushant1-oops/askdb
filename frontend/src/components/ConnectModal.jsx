import { useState } from 'react';
import { X, Database, Loader2 } from 'lucide-react';
import { connectDB } from '../api';
import { useConnection } from '../context/ConnectionContext';
import toast from 'react-hot-toast';

const DB_TYPES = [
  { value: 'sqlite', label: 'SQLite', icon: '📁' },
  { value: 'postgresql', label: 'PostgreSQL', icon: '🐘' },
  { value: 'mysql', label: 'MySQL', icon: '🐬' },
];

export default function ConnectModal({ onClose }) {
  const { refresh, selectConnection } = useConnection();
  const [dbType, setDbType] = useState('sqlite');
  const [form, setForm] = useState({ database: '', host: 'localhost', port: '', username: '', password: '', file_path: '' });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = { db_type: dbType, database: form.database };
      if (dbType === 'sqlite') {
        payload.file_path = form.file_path || form.database;
      } else {
        payload.host = form.host;
        payload.port = parseInt(form.port) || (dbType === 'postgresql' ? 5432 : 3306);
        payload.username = form.username;
        payload.password = form.password;
      }
      const result = await connectDB(payload);
      toast.success(`Connected to ${form.database}`);
      await refresh();
      await selectConnection(result);
      onClose();
    } catch (err) {
      toast.error(err.message);
    }
    setLoading(false);
  };

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal animate-in" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Database size={20} style={{ color: 'var(--accent)' }} /> Connect Database
          </span>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label className="form-label">Database Type</label>
              <div style={{ display: 'flex', gap: 8 }}>
                {DB_TYPES.map(t => (
                  <button key={t.value} type="button"
                    className={`btn ${dbType === t.value ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ flex: 1 }}
                    onClick={() => setDbType(t.value)}>
                    {t.icon} {t.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Database Name</label>
              <input className="form-input" placeholder="mydb" required
                value={form.database} onChange={e => set('database', e.target.value)} />
            </div>
            {dbType === 'sqlite' ? (
              <div className="form-group">
                <label className="form-label">File Path</label>
                <input className="form-input" placeholder="/path/to/database.db"
                  value={form.file_path} onChange={e => set('file_path', e.target.value)} />
              </div>
            ) : (
              <>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Host</label>
                    <input className="form-input" placeholder="localhost"
                      value={form.host} onChange={e => set('host', e.target.value)} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Port</label>
                    <input className="form-input" type="number"
                      placeholder={dbType === 'postgresql' ? '5432' : '3306'}
                      value={form.port} onChange={e => set('port', e.target.value)} />
                  </div>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Username</label>
                    <input className="form-input" placeholder="user"
                      value={form.username} onChange={e => set('username', e.target.value)} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Password</label>
                    <input className="form-input" type="password" placeholder="••••••"
                      value={form.password} onChange={e => set('password', e.target.value)} />
                  </div>
                </div>
              </>
            )}
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? <><Loader2 size={16} className="spinner" /> Connecting...</> : 'Connect'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
