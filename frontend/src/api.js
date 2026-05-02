const API = 'http://localhost:8000/api';

/**
 * Make an API request with timeout and error handling.
 * @param {string} url - API path
 * @param {object} options - fetch options
 * @param {number} timeoutMs - timeout in milliseconds (default 120s for LLM queries)
 */
async function request(url, options = {}, timeoutMs = 120000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API}${url}`, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      signal: controller.signal,
      ...options,
    });

    clearTimeout(timer);

    if (!res.ok) {
      let errBody;
      try {
        errBody = await res.json();
      } catch {
        errBody = { detail: res.statusText };
      }
      const msg = errBody.detail || errBody.message || `HTTP ${res.status}: ${res.statusText}`;
      throw new Error(msg);
    }

    return res;
  } catch (err) {
    clearTimeout(timer);
    if (err.name === 'AbortError') {
      throw new Error('Request timed out — the server took too long to respond. Try a simpler query.');
    }
    throw err;
  }
}

const json = (url, opts, timeout) => request(url, opts, timeout).then(r => r.json());

// Database
export const connectDB = (data) => json('/database/connect', { method: 'POST', body: JSON.stringify(data) });
export const listConnections = () => json('/database/connections');
export const getConnection = (id) => json(`/database/connections/${id}`);
export const disconnectDB = (id) => request(`/database/connections/${id}`, { method: 'DELETE' }).then(r => r.json());
export const listTables = (id) => json(`/database/connections/${id}/tables`);
export const getTableSchema = (id, table) => json(`/database/connections/${id}/tables/${table}/schema`);
export const getTableData = (id, table, limit = 100) => json(`/database/connections/${id}/tables/${table}/data?limit=${limit}`);
export const getDatabaseSchema = (id) => json(`/database/connections/${id}/schema`);

// Query — longer timeout (120s) for LLM-generated queries
export const queryNL = (connectionId, question) =>
  json('/query/natural-language', { method: 'POST', body: JSON.stringify({ connection_id: connectionId, question }) }, 120000);
export const querySQL = (connectionId, sql_query) =>
  json('/query/sql', { method: 'POST', body: JSON.stringify({ connection_id: connectionId, sql_query }) }, 30000);
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
