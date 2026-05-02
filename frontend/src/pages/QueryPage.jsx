import { useState, useRef } from 'react';
import { Send, Sparkles, Code2, AlertCircle, CheckCircle2, Clock, Database, Cpu, RotateCcw, Lightbulb } from 'lucide-react';
import { useConnection } from '../context/ConnectionContext';
import { queryNL, querySQL, exportQuery } from '../api';
import SQLBlock from '../components/SQLBlock';
import ResultTable from '../components/ResultTable';
import toast from 'react-hot-toast';

const EXAMPLE_QUERIES = [
  "Show me all customers from New York",
  "What are the top 5 most expensive products?",
  "How many orders were placed last month?",
  "Which customers have spent more than $500 total?",
  "Show the average order value by customer city",
  "List products that have never been ordered",
  "Show monthly revenue trends",
  "Which product categories generate the most revenue?",
];

export default function QueryPage() {
  const { activeConnection } = useConnection();
  const [mode, setMode] = useState('natural'); // 'natural' | 'sql'
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const inputRef = useRef(null);

  const handleSubmit = async (e) => {
    e?.preventDefault();
    if (!input.trim() || !activeConnection) return;
    setLoading(true);
    const startTime = Date.now();

    try {
      let data;
      if (mode === 'natural') {
        data = await queryNL(activeConnection.connection_id, input.trim());
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
        setResults(prev => [{
          id: Date.now(), type: 'nl', question: input.trim(),
          sql: data.generated_sql,
          result: data.query_result,
          model: data.model_used,
          retries: data.retries,
          serverTime: data.execution_time,
          dbType: data.db_type,
          time: elapsed,
        }, ...prev]);
      } else {
        data = await querySQL(activeConnection.connection_id, input.trim());
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
        setResults(prev => [{
          id: Date.now(), type: 'sql', sql: input.trim(),
          result: data.result,
          serverTime: data.execution_time,
          time: elapsed,
        }, ...prev]);
      }
      setInput('');
    } catch (err) {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
      setResults(prev => [{
        id: Date.now(), type: mode === 'natural' ? 'nl' : 'sql',
        question: mode === 'natural' ? input.trim() : undefined,
        sql: mode === 'sql' ? input.trim() : undefined,
        error: err.message, time: elapsed,
      }, ...prev]);
      toast.error(err.message);
    }
    setLoading(false);
  };

  const handleExport = async (result, format) => {
    if (!result.sql) return;
    try {
      const blob = await exportQuery(activeConnection.connection_id, result.sql, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `query_results.${format === 'excel' ? 'xlsx' : format}`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`Exported as ${format.toUpperCase()}`);
    } catch (err) { toast.error(`Export failed: ${err.message}`); }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
  };

  const handleExampleClick = (q) => {
    setInput(q);
    setMode('natural');
    inputRef.current?.focus();
  };

  if (!activeConnection) {
    return (
      <div className="empty-state" style={{ marginTop: 80 }}>
        <Database size={64} />
        <h3>No Database Connected</h3>
        <p>Connect to a database from the Connections page to start querying with AI.</p>
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">
          {mode === 'natural' ? '✨ AI Query Assistant' : '⚡ SQL Editor'}
        </h1>
        <p className="page-subtitle">
          {mode === 'natural'
            ? 'Ask questions in plain English and let AI generate the SQL for you.'
            : 'Write and execute SQL queries directly against your database.'}
        </p>
      </div>

      {/* Mode Tabs */}
      <div className="tabs" style={{ marginBottom: 24, width: 'fit-content' }}>
        <button className={`tab ${mode === 'natural' ? 'active' : ''}`}
          onClick={() => setMode('natural')}>
          <Sparkles size={14} style={{ marginRight: 6, verticalAlign: -2 }} /> Natural Language
        </button>
        <button className={`tab ${mode === 'sql' ? 'active' : ''}`}
          onClick={() => setMode('sql')}>
          <Code2 size={14} style={{ marginRight: 6, verticalAlign: -2 }} /> Direct SQL
        </button>
      </div>

      {/* Query Input */}
      <div style={{ marginBottom: 32 }}>
        <form onSubmit={handleSubmit}>
          <div className="query-input-wrapper">
            <textarea ref={inputRef} className="query-input" rows={1}
              placeholder={mode === 'natural'
                ? 'Ask a question... e.g. "Show me all customers who spent more than $1000"'
                : 'Write SQL... e.g. SELECT * FROM customers LIMIT 10'}
              value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              style={{ fontFamily: mode === 'sql' ? 'var(--font-mono)' : 'var(--font-sans)',
                fontSize: mode === 'sql' ? 14 : 16 }}
            />
            <button type="submit" className="query-submit-btn" disabled={loading || !input.trim()}>
              {loading ? <div className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} />
                : <Send size={18} />}
            </button>
          </div>
        </form>
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12,
            color: 'var(--accent)', fontSize: 14 }}>
            <div className="pulse-dot"><span /><span /><span /></div>
            {mode === 'natural' ? '🤖 AI is generating SQL with Groq (Llama 3.3 70B)...' : 'Executing query...'}
          </div>
        )}
      </div>

      {/* Results */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        {results.map(r => (
          <div key={r.id} className="animate-in" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Question (NL mode) */}
            {r.question && (
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                <div style={{ width: 32, height: 32, borderRadius: 8,
                  background: 'linear-gradient(135deg, var(--accent), #3b82f6)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Sparkles size={16} color="#fff" />
                </div>
                <div style={{ fontSize: 15, fontWeight: 600, paddingTop: 5 }}>{r.question}</div>
              </div>
            )}

            {/* Generated SQL */}
            {r.sql && <SQLBlock sql={r.sql} label={r.type === 'nl' ? 'Generated SQL' : 'Executed SQL'} />}

            {/* Model & retry info (NL mode) */}
            {r.type === 'nl' && r.model && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, fontSize: 12 }}>
                <span className="badge badge-info" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  <Cpu size={11} /> {r.model}
                </span>
                {r.dbType && (
                  <span className="badge badge-info">
                    {r.dbType.toUpperCase()} dialect
                  </span>
                )}
                {r.retries > 0 && (
                  <span className="badge badge-warning" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    <RotateCcw size={11} /> {r.retries} self-correction{r.retries > 1 ? 's' : ''}
                  </span>
                )}
                {r.serverTime && (
                  <span className="badge badge-info">
                    Server: {r.serverTime}s
                  </span>
                )}
              </div>
            )}

            {/* Error */}
            {r.error && (
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12,
                background: 'var(--error-bg)', border: '1px solid rgba(239,68,68,0.3)',
                borderRadius: 'var(--radius)', padding: 16 }}>
                <AlertCircle size={20} style={{ color: 'var(--error)', flexShrink: 0, marginTop: 2 }} />
                <div>
                  <div style={{ fontWeight: 700, color: 'var(--error)', marginBottom: 4 }}>Error</div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{r.error}</div>
                </div>
              </div>
            )}

            {/* Success message (no rows) */}
            {r.result && r.result.success && !r.result.columns && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12,
                background: 'var(--success-bg)', border: '1px solid rgba(16,185,129,0.3)',
                borderRadius: 'var(--radius)', padding: 16 }}>
                <CheckCircle2 size={20} style={{ color: 'var(--success)' }} />
                <div>
                  <span style={{ fontWeight: 700, color: 'var(--success)' }}>
                    Query executed successfully
                  </span>
                  {r.result.rows_affected != null && (
                    <span style={{ color: 'var(--text-secondary)', marginLeft: 8 }}>
                      — {r.result.rows_affected} rows affected
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Result error */}
            {r.result && !r.result.success && r.result.error && (
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12,
                background: 'var(--error-bg)', border: '1px solid rgba(239,68,68,0.3)',
                borderRadius: 'var(--radius)', padding: 16 }}>
                <AlertCircle size={20} style={{ color: 'var(--error)', flexShrink: 0, marginTop: 2 }} />
                <div>
                  <div style={{ fontWeight: 700, color: 'var(--error)', marginBottom: 4 }}>Execution Error</div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                    {r.result.error}
                  </div>
                </div>
              </div>
            )}

            {/* Result Table */}
            {r.result && r.result.success && r.result.columns && (
              <ResultTable columns={r.result.columns} rows={r.result.rows}
                onExport={(fmt) => handleExport(r, fmt)} />
            )}

            {/* Timing */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6,
              fontSize: 12, color: 'var(--text-muted)' }}>
              <Clock size={12} /> Completed in {r.time}s
            </div>

            <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '8px 0' }} />
          </div>
        ))}
      </div>

      {results.length === 0 && !loading && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24, marginTop: 32 }}>
          <div className="empty-state" style={{ marginBottom: 0 }}>
            <Sparkles size={64} />
            <h3>Ready to Query</h3>
            <p>Type a question above or try one of the examples below.</p>
          </div>
          {mode === 'natural' && (
            <div style={{ width: '100%', maxWidth: 700 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
                fontSize: 13, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase',
                letterSpacing: '0.5px' }}>
                <Lightbulb size={14} /> Example Queries
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {EXAMPLE_QUERIES.map((q, i) => (
                  <button key={i} className="btn btn-ghost btn-sm"
                    style={{ fontSize: 13, textAlign: 'left' }}
                    onClick={() => handleExampleClick(q)}>
                    "{q}"
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
