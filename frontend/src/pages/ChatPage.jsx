import { useState, useRef, useEffect } from 'react';
import {
  Send, Bot, User, BarChart3, LineChart as LineChartIcon, PieChart as PieChartIcon,
  AreaChart as AreaChartIcon, Code2, Table2, ChevronDown, ChevronUp,
  Database, Cpu, Clock, RotateCcw, Sparkles, TrendingUp
} from 'lucide-react';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, AreaChart, Area,
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer
} from 'recharts';
import { useConnection } from '../context/ConnectionContext';
import { queryChat } from '../api';
import SQLBlock from '../components/SQLBlock';
import ResultTable from '../components/ResultTable';
import toast from 'react-hot-toast';

const CHART_COLORS = [
  '#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1',
];

const CHART_TYPES = [
  { key: 'bar', icon: BarChart3, label: 'Bar' },
  { key: 'line', icon: LineChartIcon, label: 'Line' },
  { key: 'pie', icon: PieChartIcon, label: 'Pie' },
  { key: 'area', icon: AreaChartIcon, label: 'Area' },
];

const EXAMPLE_PROMPTS = [
  "What is our total revenue by product category?",
  "Show me monthly sales trends",
  "Which customers have the highest order values?",
  "Why might sales be declining? Analyze the data.",
  "What is the projected annual turnover based on current data?",
  "Compare revenue across different regions",
];

function ChartRenderer({ chart, overrideType }) {
  const type = overrideType || chart.type;
  const data = chart.data || [];
  const xKey = chart.xKey || 'label';
  const yKeys = chart.yKeys || ['value'];
  const yKeyLabels = chart.yKeyLabels || {};

  if (!data.length) return null;

  const customTooltipStyle = {
    backgroundColor: 'rgba(22,22,58,0.95)',
    border: '1px solid rgba(139,92,246,0.3)',
    borderRadius: '8px',
    padding: '10px 14px',
    boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
    color: '#e8e8ff',
    fontSize: '13px',
  };

  if (type === 'pie') {
    return (
      <ResponsiveContainer width="100%" height={360}>
        <PieChart>
          <Pie
            data={data}
            dataKey={yKeys[0]}
            nameKey={xKey}
            cx="50%"
            cy="50%"
            outerRadius={130}
            innerRadius={60}
            paddingAngle={3}
            label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
            labelLine={{ stroke: '#6b6b99', strokeWidth: 1 }}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={customTooltipStyle} />
          <Legend
            wrapperStyle={{ color: '#9d9dcc', fontSize: '12px', paddingTop: '16px' }}
          />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  if (type === 'scatter') {
    return (
      <ResponsiveContainer width="100%" height={360}>
        <ScatterChart margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(139,92,246,0.1)" />
          <XAxis
            dataKey={xKey} name={xKey}
            tick={{ fill: '#9d9dcc', fontSize: 12 }}
            axisLine={{ stroke: 'rgba(139,92,246,0.2)' }}
          />
          <YAxis
            dataKey={yKeys[0]} name={yKeyLabels[yKeys[0]] || yKeys[0]}
            tick={{ fill: '#9d9dcc', fontSize: 12 }}
            axisLine={{ stroke: 'rgba(139,92,246,0.2)' }}
          />
          <Tooltip contentStyle={customTooltipStyle} cursor={{ strokeDasharray: '3 3' }} />
          <Scatter data={data} fill="#8b5cf6" />
        </ScatterChart>
      </ResponsiveContainer>
    );
  }

  // Bar, Line, or Area
  const ChartComponent = type === 'line' ? LineChart : type === 'area' ? AreaChart : BarChart;

  return (
    <ResponsiveContainer width="100%" height={360}>
      <ChartComponent data={data} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(139,92,246,0.1)" />
        <XAxis
          dataKey={xKey}
          tick={{ fill: '#9d9dcc', fontSize: 12 }}
          axisLine={{ stroke: 'rgba(139,92,246,0.2)' }}
          tickLine={{ stroke: 'rgba(139,92,246,0.2)' }}
          angle={data.length > 8 ? -35 : 0}
          textAnchor={data.length > 8 ? 'end' : 'middle'}
          height={data.length > 8 ? 80 : 40}
        />
        <YAxis
          tick={{ fill: '#9d9dcc', fontSize: 12 }}
          axisLine={{ stroke: 'rgba(139,92,246,0.2)' }}
          tickLine={{ stroke: 'rgba(139,92,246,0.2)' }}
        />
        <Tooltip contentStyle={customTooltipStyle} cursor={{ fill: 'rgba(139,92,246,0.08)' }} />
        {yKeys.length > 1 && (
          <Legend wrapperStyle={{ color: '#9d9dcc', fontSize: '12px', paddingTop: '8px' }} />
        )}
        {yKeys.map((yKey, i) => {
          const color = CHART_COLORS[i % CHART_COLORS.length];
          const label = yKeyLabels[yKey] || yKey;

          if (type === 'line') {
            return (
              <Line key={yKey} type="monotone" dataKey={yKey} name={label}
                stroke={color} strokeWidth={2.5} dot={{ r: 4, fill: color }}
                activeDot={{ r: 6, stroke: '#fff', strokeWidth: 2 }}
              />
            );
          }
          if (type === 'area') {
            return (
              <Area key={yKey} type="monotone" dataKey={yKey} name={label}
                stroke={color} strokeWidth={2} fill={color} fillOpacity={0.15}
              />
            );
          }
          return (
            <Bar key={yKey} dataKey={yKey} name={label}
              fill={color} radius={[6, 6, 0, 0]} maxBarSize={60}
            />
          );
        })}
      </ChartComponent>
    </ResponsiveContainer>
  );
}


export default function ChatPage() {
  const { activeConnection } = useConnection();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSubmit = async (e) => {
    e?.preventDefault();
    if (!input.trim() || !activeConnection || loading) return;

    const userMessage = input.trim();
    setInput('');

    // Add user message
    const userMsg = { id: Date.now(), role: 'user', content: userMessage };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      // Build history from previous messages
      const history = messages.map(m => ({
        role: m.role,
        content: m.role === 'user' ? m.content : (m.answer || m.content),
      }));

      const data = await queryChat(activeConnection.connection_id, userMessage, history);

      const assistantMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        answer: data.answer,
        chart: data.chart,
        generatedSql: data.generated_sql,
        queryResult: data.query_result,
        modelUsed: data.model_used,
        retries: data.retries,
        executionTime: data.execution_time,
        dbType: data.db_type,
        showChart: false,
        chartOverride: null,
        showSql: false,
        showData: false,
      };

      setMessages(prev => [...prev, assistantMsg]);
    } catch (err) {
      const errorMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        answer: `❌ **Error:** ${err.message}`,
        chart: null,
        error: true,
      };
      setMessages(prev => [...prev, errorMsg]);
      toast.error(err.message);
    }
    setLoading(false);
  };

  const toggleMsgProp = (msgId, prop) => {
    setMessages(prev => prev.map(m =>
      m.id === msgId ? { ...m, [prop]: !m[prop] } : m
    ));
  };

  const setChartOverride = (msgId, chartType) => {
    setMessages(prev => prev.map(m =>
      m.id === msgId ? { ...m, chartOverride: chartType, showChart: true } : m
    ));
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
  };

  const handleExampleClick = (q) => {
    setInput(q);
    inputRef.current?.focus();
  };

  if (!activeConnection) {
    return (
      <div className="empty-state" style={{ marginTop: 80 }}>
        <Database size={64} />
        <h3>No Database Connected</h3>
        <p>Connect to a database from the Connections page to start analyzing with AI.</p>
      </div>
    );
  }

  return (
    <div className="chat-page">
      {/* Header */}
      <div className="page-header">
        <h1 className="page-title">🧠 AI Analyst</h1>
        <p className="page-subtitle">
          Ask business questions, get insights with data-driven answers and interactive visualizations.
        </p>
      </div>

      {/* Chat Messages */}
      <div className="chat-messages">
        {messages.length === 0 && !loading && (
          <div className="chat-welcome">
            <div className="chat-welcome-icon">
              <TrendingUp size={40} />
            </div>
            <h2>What would you like to analyze?</h2>
            <p>Ask me anything about your data — trends, comparisons, insights, or visualizations.</p>
            <div className="chat-examples">
              {EXAMPLE_PROMPTS.map((q, i) => (
                <button key={i} className="chat-example-btn" onClick={() => handleExampleClick(q)}>
                  <Sparkles size={14} />
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map(msg => (
          <div key={msg.id} className={`chat-msg chat-msg-${msg.role}`}>
            {/* Avatar */}
            <div className={`chat-avatar chat-avatar-${msg.role}`}>
              {msg.role === 'user' ? <User size={18} /> : <Bot size={18} />}
            </div>

            {/* Content */}
            <div className={`chat-bubble chat-bubble-${msg.role}`}>
              {msg.role === 'user' ? (
                <div className="chat-text">{msg.content}</div>
              ) : (
                <div className="chat-assistant-content">
                  {/* Answer text */}
                  <div className="chat-answer" dangerouslySetInnerHTML={{
                    __html: (msg.answer || '').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                      .replace(/\n/g, '<br/>')
                      .replace(/- /g, '• ')
                  }} />

                  {/* Action buttons row */}
                  <div className="chat-actions">
                    {/* Visualize Data button */}
                    {msg.chart && (
                      <button
                        className={`chat-action-btn ${msg.showChart ? 'active' : ''}`}
                        onClick={() => toggleMsgProp(msg.id, 'showChart')}
                      >
                        <BarChart3 size={14} />
                        {msg.showChart ? 'Hide Chart' : 'Visualize Data'}
                      </button>
                    )}

                    {/* Show SQL button */}
                    {msg.generatedSql && (
                      <button
                        className={`chat-action-btn ${msg.showSql ? 'active' : ''}`}
                        onClick={() => toggleMsgProp(msg.id, 'showSql')}
                      >
                        <Code2 size={14} />
                        {msg.showSql ? 'Hide SQL' : 'Show SQL'}
                      </button>
                    )}

                    {/* Show Data button */}
                    {msg.queryResult?.success && msg.queryResult?.columns && (
                      <button
                        className={`chat-action-btn ${msg.showData ? 'active' : ''}`}
                        onClick={() => toggleMsgProp(msg.id, 'showData')}
                      >
                        <Table2 size={14} />
                        {msg.showData ? 'Hide Data' : 'Show Data'}
                      </button>
                    )}
                  </div>

                  {/* Chart section — shown only on button click */}
                  {msg.showChart && msg.chart && (
                    <div className="chat-chart-container animate-in">
                      <div className="chat-chart-header">
                        <div className="chat-chart-title">
                          {msg.chart.title || 'Data Visualization'}
                        </div>
                        {/* Chart type switcher */}
                        <div className="chat-chart-types">
                          {CHART_TYPES.map(ct => {
                            const Icon = ct.icon;
                            const isActive = (msg.chartOverride || msg.chart.type) === ct.key;
                            return (
                              <button
                                key={ct.key}
                                className={`chat-chart-type-btn ${isActive ? 'active' : ''}`}
                                onClick={() => setChartOverride(msg.id, ct.key)}
                                title={ct.label}
                              >
                                <Icon size={14} />
                              </button>
                            );
                          })}
                        </div>
                      </div>
                      <ChartRenderer
                        chart={msg.chart}
                        overrideType={msg.chartOverride}
                      />
                    </div>
                  )}

                  {/* SQL block — collapsible */}
                  {msg.showSql && msg.generatedSql && (
                    <div className="animate-in" style={{ marginTop: 8 }}>
                      <SQLBlock sql={msg.generatedSql} label="Generated SQL" />
                    </div>
                  )}

                  {/* Data table — collapsible */}
                  {msg.showData && msg.queryResult?.success && msg.queryResult?.columns && (
                    <div className="animate-in" style={{ marginTop: 8 }}>
                      <ResultTable
                        columns={msg.queryResult.columns}
                        rows={msg.queryResult.rows}
                        title={`Query Results (${msg.queryResult.row_count} rows)`}
                      />
                    </div>
                  )}

                  {/* Meta badges */}
                  {msg.modelUsed && (
                    <div className="chat-meta">
                      <span className="badge badge-info" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <Cpu size={11} /> {msg.modelUsed}
                      </span>
                      {msg.retries > 0 && (
                        <span className="badge badge-warning" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          <RotateCcw size={11} /> {msg.retries} correction{msg.retries > 1 ? 's' : ''}
                        </span>
                      )}
                      {msg.executionTime && (
                        <span className="badge badge-info" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          <Clock size={11} /> {msg.executionTime}s
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Loading indicator */}
        {loading && (
          <div className="chat-msg chat-msg-assistant">
            <div className="chat-avatar chat-avatar-assistant">
              <Bot size={18} />
            </div>
            <div className="chat-bubble chat-bubble-assistant">
              <div className="chat-typing">
                <div className="pulse-dot"><span /><span /><span /></div>
                <span>Analyzing your data with AI...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="chat-input-area">
        <form onSubmit={handleSubmit} className="chat-input-form">
          <textarea
            ref={inputRef}
            className="chat-input"
            rows={1}
            placeholder="Ask a business question... e.g. &quot;Why are sales declining?&quot; or &quot;Show revenue by category as a pie chart&quot;"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button type="submit" className="chat-send-btn" disabled={loading || !input.trim()}>
            {loading
              ? <div className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} />
              : <Send size={18} />}
          </button>
        </form>
      </div>
    </div>
  );
}
