import { createContext, useContext, useState, useCallback } from 'react';
import { listConnections, listTables, getDatabaseSchema } from '../api';

const ConnectionContext = createContext(null);

export function ConnectionProvider({ children }) {
  const [connections, setConnections] = useState([]);
  const [activeConnection, setActiveConnection] = useState(null);
  const [tables, setTables] = useState([]);
  const [schema, setSchema] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await listConnections();
      setConnections(data.connections || []);
    } catch { setConnections([]); }
  }, []);

  const selectConnection = useCallback(async (conn) => {
    setActiveConnection(conn);
    setLoading(true);
    try {
      const [t, s] = await Promise.all([
        listTables(conn.connection_id),
        getDatabaseSchema(conn.connection_id),
      ]);
      setTables(t.tables || []);
      setSchema(s);
    } catch { setTables([]); setSchema(null); }
    setLoading(false);
  }, []);

  const clearConnection = useCallback(() => {
    setActiveConnection(null);
    setTables([]);
    setSchema(null);
  }, []);

  return (
    <ConnectionContext.Provider value={{
      connections, activeConnection, tables, schema, loading,
      refresh, selectConnection, clearConnection, setConnections,
    }}>
      {children}
    </ConnectionContext.Provider>
  );
}

export const useConnection = () => {
  const ctx = useContext(ConnectionContext);
  if (!ctx) throw new Error('useConnection must be inside ConnectionProvider');
  return ctx;
};
