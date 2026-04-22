const API = 'http://localhost:8000/api';

async function request(url, options = {}) {
  const res = await fetch(`${API}${url}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res;
}

const json = (url, opts) => request(url, opts).then(r => r.json());

// Database
export const connectDB = (data) => json('/database/connect', { method: 'POST', body: JSON.stringify(data) });
export const listConnections = () => json('/database/connections');
export const getConnection = (id) => json(`/database/connections/${id}`);
export const disconnectDB = (id) => request(`/database/connections/${id}`, { method: 'DELETE' }).then(r => r.json());
export const listTables = (id) => json(`/database/connections/${id}/tables`);
export const getTableSchema = (id, table) => json(`/database/connections/${id}/tables/${table}/schema`);
export const getTableData = (id, table, limit = 100) => json(`/database/connections/${id}/tables/${table}/data?limit=${limit}`);
export const getDatabaseSchema = (id) => json(`/database/connections/${id}/schema`);

// Query
export const queryNL = (connectionId, question) => json('/query/natural-language', { method: 'POST', body: JSON.stringify({ connection_id: connectionId, question }) });
export const querySQL = (connectionId, sql_query) => json('/query/sql', { method: 'POST', body: JSON.stringify({ connection_id: connectionId, sql_query }) });
export const modelStatus = () => json('/query/model-status');

// Export
export const exportTable = async (connectionId, tableName, format) => {
  const res = await request('/export/table', { method: 'POST', body: JSON.stringify({ connection_id: connectionId, table_name: tableName, format }) });
  return res.blob();
};
export const exportQuery = async (connectionId, sqlQuery, format, filename) => {
  const res = await request('/export/query', { method: 'POST', body: JSON.stringify({ connection_id: connectionId, sql_query: sqlQuery, format, filename }) });
  return res.blob();
};
