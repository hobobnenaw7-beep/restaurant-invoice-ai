import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { Toaster } from "@/components/ui/sonner";
import { StableErrorBoundary } from "@/components/StableErrorBoundary";
import Layout from "@/components/Layout";
import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import ProfitDashboard from "@/pages/ProfitDashboard";
import ExpensesPage from "@/pages/ExpensesPage";
import SalesPage from "@/pages/SalesPage";
import VendorsPage from "@/pages/VendorsPage";
import VendorDetailPage from "@/pages/VendorDetailPage";
import ItemsPage from "@/pages/ItemsPage";
import ReportsPage from "@/pages/ReportsPage";
import RecordsLibraryPage from "@/pages/RecordsLibraryPage";
import UserManagementPage from "@/pages/UserManagementPage";
import ApprovalsPage from "@/pages/ApprovalsPage";
import ChatPage from "@/pages/ChatPage";
import SettingsPage from "@/pages/SettingsPage";
import PurchaseDecisionsPage from "@/pages/PurchaseDecisionsPage";
import AuditLogPage from "@/pages/AuditLogPage";
import CorrectionMemoryPage from "@/pages/CorrectionMemoryPage";
import VendorComparisonPage from "@/pages/VendorComparisonPage";
import { ShieldOff } from 'lucide-react';

// Priority-ordered list of pages for landing page resolution.
// After login, the user lands on the first page they have permission to access.
const LANDING_PRIORITY = [
  { path: '/dashboard', perm: 'view_dashboard' },
  { path: '/sales', perm: 'view_sales' },
  { path: '/expenses', perm: 'view_expenses' },
  { path: '/records', perm: 'view_records' },
  { path: '/reports', perm: 'view_reports' },
  { path: '/vendors', perm: 'view_vendors' },
  { path: '/items', perm: 'view_items' },
  { path: '/users', perm: 'view_users' },
];

function getFirstAllowedPath(perms) {
  if (!perms) return null;
  for (const entry of LANDING_PRIORITY) {
    if (perms[entry.perm]) return entry.path;
  }
  return null;
}

function NoAccessPage() {
  const { logout } = useAuth();
  const handleLogout = () => {
    logout();
    window.location.href = '/login';
  };
  return (
    <div className="flex h-screen items-center justify-center bg-slate-50">
      <div className="text-center max-w-sm px-6">
        <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-5">
          <ShieldOff className="w-8 h-8 text-slate-400" />
        </div>
        <h1 className="font-heading text-xl font-bold text-navy-900 mb-2">No Accessible Pages</h1>
        <p className="text-sm text-slate-500 mb-6">
          Your account does not have visibility permissions for any pages. Please contact your manager to update your access.
        </p>
        <button
          onClick={handleLogout}
          className="px-4 py-2 text-sm font-semibold text-white bg-teal-600 hover:bg-teal-700 rounded-lg transition-colors"
          data-testid="no-access-logout-btn"
        >
          Log Out
        </button>
      </div>
    </div>
  );
}

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex h-screen items-center justify-center"><div className="animate-spin w-8 h-8 border-2 border-teal-600 border-t-transparent rounded-full" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Layout><StableErrorBoundary>{children}</StableErrorBoundary></Layout>;
}

function PermRoute({ children, perm }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex h-screen items-center justify-center"><div className="animate-spin w-8 h-8 border-2 border-teal-600 border-t-transparent rounded-full" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  const perms = user?.permissions || {};
  if (perm && !perms[perm]) {
    // Redirect to first allowed page, not hardcoded /dashboard
    const fallback = getFirstAllowedPath(perms);
    if (!fallback) return <Navigate to="/no-access" replace />;
    return <Navigate to={fallback} replace />;
  }
  return <Layout><StableErrorBoundary>{children}</StableErrorBoundary></Layout>;
}

function PublicRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex h-screen items-center justify-center"><div className="animate-spin w-8 h-8 border-2 border-teal-600 border-t-transparent rounded-full" /></div>;
  if (user) {
    // Redirect to first allowed page, not hardcoded /dashboard
    const landing = getFirstAllowedPath(user?.permissions);
    return <Navigate to={landing || '/no-access'} replace />;
  }
  return children;
}

function SmartLanding() {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex h-screen items-center justify-center"><div className="animate-spin w-8 h-8 border-2 border-teal-600 border-t-transparent rounded-full" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  const landing = getFirstAllowedPath(user?.permissions);
  return <Navigate to={landing || '/no-access'} replace />;
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
          <Route path="/no-access" element={<NoAccessPage />} />
          <Route path="/dashboard" element={<PermRoute perm="view_dashboard"><DashboardPage /></PermRoute>} />
          <Route path="/profit-center" element={<PermRoute perm="view_dashboard"><ProfitDashboard /></PermRoute>} />
          <Route path="/expenses" element={<PermRoute perm="view_expenses"><ExpensesPage /></PermRoute>} />
          <Route path="/sales" element={<PermRoute perm="view_sales"><SalesPage /></PermRoute>} />
          <Route path="/vendors" element={<PermRoute perm="view_vendors"><VendorsPage /></PermRoute>} />
          <Route path="/vendors/:id" element={<PermRoute perm="view_vendors"><VendorDetailPage /></PermRoute>} />
          <Route path="/items" element={<PermRoute perm="view_items"><ItemsPage /></PermRoute>} />
          <Route path="/reports" element={<PermRoute perm="view_reports"><ReportsPage /></PermRoute>} />
          <Route path="/records" element={<PermRoute perm="view_records"><RecordsLibraryPage /></PermRoute>} />
          <Route path="/users" element={<PermRoute perm="view_users"><UserManagementPage /></PermRoute>} />
          <Route path="/approvals" element={<PermRoute perm="view_users"><ApprovalsPage /></PermRoute>} />
          <Route path="/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
          <Route path="/purchase-decisions" element={<PermRoute perm="view_reports"><PurchaseDecisionsPage /></PermRoute>} />
          <Route path="/audit-log" element={<PermRoute perm="view_users"><AuditLogPage /></PermRoute>} />
          <Route path="/vendor-comparison" element={<PermRoute perm="view_vendors"><VendorComparisonPage /></PermRoute>} />
          <Route path="/correction-memory" element={<PermRoute perm="view_expenses"><CorrectionMemoryPage /></PermRoute>} />
          <Route path="*" element={<SmartLanding />} />
        </Routes>
        <Toaster position="top-right" richColors />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
