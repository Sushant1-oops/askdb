import { useState } from 'react';
import { Copy, Check } from 'lucide-react';

const SQL_KEYWORDS = /\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|AND|OR|NOT|IN|AS|ORDER BY|GROUP BY|HAVING|LIMIT|OFFSET|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|ALTER|DROP|INDEX|COUNT|SUM|AVG|MIN|MAX|DISTINCT|BETWEEN|LIKE|IS|NULL|EXISTS|UNION|ALL|CASE|WHEN|THEN|ELSE|END|ASC|DESC)\b/gi;

function highlightSQL(sql) {
  if (!sql) return '';
  return sql.replace(SQL_KEYWORDS, '<span class="keyword">$1</span>');
}

export default function SQLBlock({ sql, label }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div style={{ marginBottom: 4 }}>
      {label && <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)',
        textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>{label}</div>}
      <div className="sql-block">
        <button className="copy-btn" onClick={handleCopy}>
          {copied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
        </button>
        <code dangerouslySetInnerHTML={{ __html: highlightSQL(sql) }} />
      </div>
    </div>
  );
}
