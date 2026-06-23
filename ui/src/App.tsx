import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Analyze from './pages/Analyze';
import Trends from './pages/Trends';
import Reports from './pages/Reports';
import Workflow from './pages/Workflow';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="analyze" element={<Analyze />} />
        <Route path="trends" element={<Trends />} />
        <Route path="reports" element={<Reports />} />
        <Route path="workflow" element={<Workflow />} />
      </Route>
    </Routes>
  );
}
