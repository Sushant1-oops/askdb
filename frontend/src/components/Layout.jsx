import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, Database, Table2, Workflow, Zap } from 'lucide-react';
import { useConnection } from '../context/ConnectionContext';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/query', icon: MessageSquare, label: 'AI Query' },
  { to: '/schema', icon: Workflow, label: 'Schema Explorer' },
  { to: '/tables', icon: Table2, label: 'Table Viewer' },
  { to: '/connections', icon: Database, label: 'Connections' },
];

export default function Layout() {
  const location = useLocation();
  const { activeConnection } = useConnection();
  const pageTitle = navItems.find(n => n.to === location.pathname)?.label || 'QueryForge';

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <a href="/" className="sidebar-logo">
            <div className="sidebar-logo-icon"><Zap size={20} /></div>
            <span className="sidebar-logo-text">QueryForge</span>
          </a>
        </div>
        <nav className="sidebar-nav">
          <div className="nav-section-title">Navigation</div>
          {navItems.map(item => (
            <NavLink key={item.to} to={item.to} end
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <item.icon size={18} />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          {activeConnection ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
              background: 'var(--success-bg)', borderRadius: 'var(--radius-sm)',
              border: '1px solid rgba(16,185,129,0.3)' }}>
              <span className="badge-dot" style={{ width: 8, height: 8, borderRadius: '50%',
                background: 'var(--success)', flexShrink: 0 }} />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--success)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {activeConnection.database}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {activeConnection.db_type} · Connected
                </div>
              </div>
            </div>
          ) : (
            <div style={{ padding: '8px 12px', background: 'var(--warning-bg)',
              borderRadius: 'var(--radius-sm)', border: '1px solid rgba(245,158,11,0.3)',
              fontSize: 13, color: 'var(--warning)', fontWeight: 600, textAlign: 'center' }}>
              No database connected
            </div>
          )}
        </div>
      </aside>
      <main className="main-content">
        <header className="topbar">
          <h1 className="topbar-title">{pageTitle}</h1>
          <div className="topbar-actions">
            {activeConnection && (
              <span className="badge badge-success">
                <span className="badge-dot" /> {activeConnection.db_type.toUpperCase()}
              </span>
            )}
          </div>
        </header>
        <div className="page animate-in">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
