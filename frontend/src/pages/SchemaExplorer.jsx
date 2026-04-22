import { useState } from 'react';
import { ChevronRight, ChevronDown, Table2, Key, Hash, Database } from 'lucide-react';
import { useConnection } from '../context/ConnectionContext';

export default function SchemaExplorer() {
  const { activeConnection, schema } = useConnection();
  const [expanded, setExpanded] = useState({});

  const toggle = (table) => setExpanded(p => ({ ...p, [table]: !p[table] }));

  if (!activeConnection) {
    return (
      <div className="empty-state" style={{ marginTop: 80 }}>
        <Database size={64} />
        <h3>No Database Connected</h3>
        <p>Connect to a database first to explore its schema.</p>
      </div>
    );
  }

  if (!schema || !schema.tables) {
    return <div className="loader"><div className="spinner" /> Loading schema...</div>;
  }

  const tableNames = Object.keys(schema.tables);

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Schema Explorer</h1>
        <p className="page-subtitle">
          Database: <strong>{schema.database}</strong> · {tableNames.length} tables
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {tableNames.map(table => {
          const cols = schema.tables[table].columns;
          const isOpen = expanded[table];
          return (
            <div key={table} className="schema-table">
              <div className="schema-table-header" onClick={() => toggle(table)}>
                <span className="schema-table-name">
                  {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  <Table2 size={16} style={{ color: 'var(--info)' }} />
                  {table}
                  <span className="badge badge-info" style={{ marginLeft: 8 }}>
                    {cols.length} columns
                  </span>
                </span>
              </div>
              {isOpen && (
                <div className="schema-columns animate-in">
                  {cols.map(col => (
                    <div key={col.name} className="schema-column">
                      {col.primary_key ? <Key size={12} style={{ color: 'var(--warning)' }} />
                        : <Hash size={12} style={{ color: 'var(--text-muted)' }} />}
                      <span className="schema-col-name">{col.name}</span>
                      <span className="schema-col-type">{col.type}</span>
                      {col.primary_key && <span className="schema-col-pk">PK</span>}
                      {!col.nullable && (
                        <span style={{ fontSize: 10, color: 'var(--error)', fontWeight: 600 }}>NOT NULL</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}
