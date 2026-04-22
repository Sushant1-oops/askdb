import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import QueryPage from './pages/QueryPage';
import SchemaExplorer from './pages/SchemaExplorer';
import Connections from './pages/Connections';
import TableViewer from './pages/TableViewer';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/query" element={<QueryPage />} />
        <Route path="/schema" element={<SchemaExplorer />} />
        <Route path="/connections" element={<Connections />} />
        <Route path="/tables" element={<TableViewer />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
