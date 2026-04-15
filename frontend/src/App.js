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
  if (perm && !perms[perm]) return <Navigate to="/dashboard" replace />;
  return <Layout><StableErrorBoundary>{children}</StableErrorBoundary></Layout>;
}

function PublicRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex h-screen items-center justify-center"><div className="animate-spin w-8 h-8 border-2 border-teal-600 border-t-transparent rounded-full" /></div>;
  if (user) return <Navigate to="/dashboard" replace />;
  return children;
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
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
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
        <Toaster position="top-right" richColors />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
