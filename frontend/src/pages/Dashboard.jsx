import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Database, MessageSquare, Table2, Workflow, Plus, Zap, Activity } from 'lucide-react';
import { useConnection } from '../context/ConnectionContext';
import { modelStatus } from '../api';
import ConnectModal from '../components/ConnectModal';

export default function Dashboard() {
  const navigate = useNavigate();
  const { connections, activeConnection, tables, refresh } = useConnection();
  const [showConnect, setShowConnect] = useState(false);
  const [llmStatus, setLlmStatus] = useState(null);

  useEffect(() => { refresh(); checkLLM(); }, []);

  const checkLLM = async () => {
    try { const s = await modelStatus(); setLlmStatus(s); } catch { setLlmStatus(null); }
  };

  const stats = [
    { icon: Database, label: 'Connections', value: connections.length, color: 'purple' },
    { icon: Table2, label: 'Tables', value: tables.length, color: 'blue' },
    { icon: Activity, label: 'LLM Model', value: llmStatus?.available ? 'Online' : 'Offline',
      color: llmStatus?.available ? 'green' : 'orange' },
    { icon: Zap, label: 'Status', value: activeConnection ? 'Connected' : 'Idle', color: 'green' },
  ];

  const quickActions = [
    { icon: MessageSquare, label: 'AI Query', desc: 'Ask questions in natural language', to: '/query', color: 'var(--accent)' },
    { icon: Workflow, label: 'Schema', desc: 'Explore database structure', to: '/schema', color: 'var(--info)' },
    { icon: Table2, label: 'Tables', desc: 'Browse and search table data', to: '/tables', color: 'var(--success)' },
    { icon: Plus, label: 'Connect', desc: 'Add a new database connection', action: () => setShowConnect(true), color: 'var(--warning)' },
  ];

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Welcome to QueryForge</h1>
        <p className="page-subtitle">Transform natural language into powerful SQL queries with AI. Connect your database and start querying.</p>
      </div>

      <div className="grid-4" style={{ marginBottom: 32 }}>
        {stats.map((s, i) => (
          <div className="stat-card" key={i} style={{ animationDelay: `${i * 60}ms` }}>
            <div className={`stat-icon ${s.color}`}><s.icon size={22} /></div>
            <div>
              <div className="stat-value">{s.value}</div>
              <div className="stat-label">{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>Quick Actions</h2>
        <div className="grid-4">
          {quickActions.map((a, i) => (
            <div key={i} className="card" style={{ cursor: 'pointer' }}
              onClick={() => a.to ? navigate(a.to) : a.action?.()}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{ width: 44, height: 44, borderRadius: 12,
                  background: `${a.color}15`, display: 'flex', alignItems: 'center',
                  justifyContent: 'center', color: a.color }}>
                  <a.icon size={22} />
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 2 }}>{a.label}</div>
                  <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{a.desc}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {!activeConnection && (
        <div className="card" style={{ textAlign: 'center', padding: 48 }}>
          <Database size={48} style={{ color: 'var(--text-muted)', marginBottom: 16, opacity: 0.4 }} />
          <h3 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8, color: 'var(--text-secondary)' }}>
            Get Started
          </h3>
          <p style={{ color: 'var(--text-muted)', marginBottom: 20, maxWidth: 400, margin: '0 auto 20px' }}>
            Connect to a database to start exploring schemas and querying data with AI.
          </p>
          <button className="btn btn-primary btn-lg" onClick={() => setShowConnect(true)}>
            <Plus size={18} /> Connect Database
          </button>
        </div>
      )}

      {activeConnection && tables.length > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="card-title"><Table2 size={18} /> Connected Tables</span>
            <span className="badge badge-info">{tables.length} tables</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {tables.map(t => (
              <span key={t} className="badge badge-info" style={{ cursor: 'pointer' }}
                onClick={() => navigate('/tables')}>{t}</span>
            ))}
          </div>
        </div>
      )}

      {showConnect && <ConnectModal onClose={() => setShowConnect(false)} />}
    </>
  );
}
