import { useState, useEffect, useCallback, useMemo, useRef, memo } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import FloatingAssistant from '@/components/FloatingAssistant';
import {
  LayoutDashboard, Receipt, DollarSign, Users,
  Package, FileText, FolderArchive, MessageCircle, Settings, Bell, Menu, LogOut, ChefHat, UserCog, ClipboardCheck,
  TrendingUp, ArrowRightLeft, Clock, ChevronDown, ShoppingCart, Shield, Home, Scale
} from 'lucide-react';

const mainNav = [
  { path: '/expenses', label: 'Expenses', icon: Receipt },
  { path: '/sales', label: 'Sales', icon: DollarSign },
  { path: '/vendors', label: 'Vendors', icon: Users },
  { path: '/items', label: 'Items', icon: Package },
  { path: '/reports', label: 'Reports', icon: FileText },
  { path: '/purchase-decisions', label: 'Smart Purchases', icon: ShoppingCart },
  { path: '/vendor-comparison', label: 'Vendor $/LB', icon: Scale },
  { path: '/records', label: 'Records Library', icon: FolderArchive },
  { path: '/audit-log', label: 'Audit Log', icon: Shield },
];

const managerNav = [
  { path: '/users', label: 'User Management', icon: UserCog },
  { path: '/approvals', label: 'Approvals', icon: ClipboardCheck },
];

// ======================== ALERT CONFIG ========================
const ALERT_CONFIG = {
  price_increase: { label: 'Price Increase', icon: TrendingUp, border: 'border-l-red-500', iconBg: 'bg-red-100', iconColor: 'text-red-600', badge: 'bg-red-100 text-red-700' },
  cheaper_vendor: { label: 'Cheaper Vendor', icon: ArrowRightLeft, border: 'border-l-emerald-500', iconBg: 'bg-emerald-100', iconColor: 'text-emerald-600', badge: 'bg-emerald-100 text-emerald-700' },
  not_ordered:    { label: 'Not Ordered', icon: Clock, border: 'border-l-amber-500', iconBg: 'bg-amber-100', iconColor: 'text-amber-600', badge: 'bg-amber-100 text-amber-700' },
};

const SEV_ORDER = { high: 0, medium: 1, low: 2 };
const SEV_BADGE = {
  high: 'bg-red-600 text-white',
  medium: 'bg-amber-500 text-white',
  low: 'bg-slate-400 text-white',
};

function fmtPrice(n) { return `$${Number(n).toFixed(2)}`; }

// ======================== NAV LINK (stable component) ========================
const NavLink = memo(function NavLink({ item, isActive, onNavigate }) {
  return (
    <Link
      to={item.path}
      onClick={onNavigate}
      data-testid={`nav-${item.path.slice(1)}`}
      className={`flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors duration-150 ${
        isActive
          ? 'bg-teal-600/15 text-teal-400'
          : 'text-navy-400 hover:text-white hover:bg-navy-800/60'
      }`}
    >
      <item.icon className="w-[18px] h-[18px] flex-shrink-0" />
      <span>{item.label}</span>
    </Link>
  );
});

// ======================== NOTIFICATION PANEL ========================
const NotificationPanel = memo(function NotificationPanel({ alerts, open, onClose, containerRef }) {
  const [filter, setFilter] = useState('all');
  const [filterOpen, setFilterOpen] = useState(false);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (containerRef?.current && !containerRef.current.contains(e.target)) {
        onCloseRef.current();
      }
    };
    const timer = setTimeout(() => document.addEventListener('mousedown', handler), 10);
    return () => { clearTimeout(timer); document.removeEventListener('mousedown', handler); };
  }, [open, containerRef]); // removed onClose from deps — use ref instead

  if (!open) return null;

  const sorted = [...alerts].sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9));
  const filtered = filter === 'all' ? sorted : sorted.filter(a => a.type === filter);

  const filterOptions = [
    { value: 'all', label: 'All Alerts' },
    { value: 'price_increase', label: 'Price Increase' },
    { value: 'cheaper_vendor', label: 'Cheaper Vendor' },
    { value: 'not_ordered', label: 'Not Ordered' },
  ];

  return (
    <div className="absolute right-0 top-full mt-2 w-[380px] max-h-[480px] bg-white rounded-xl border border-slate-200 shadow-xl z-50 flex flex-col overflow-hidden" data-testid="notification-panel">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <Bell className="w-4 h-4 text-navy-900" />
          <span className="text-xs font-bold text-navy-900">Smart Alerts</span>
          <Badge className="text-[9px] bg-slate-100 text-slate-500 h-4 px-1.5">{alerts.length}</Badge>
        </div>
        {/* Filter dropdown */}
        <div className="relative">
          <button
            className="flex items-center gap-1 text-[10px] font-semibold text-slate-500 hover:text-navy-900 transition-colors px-2 py-1 rounded-md hover:bg-slate-50"
            onClick={() => setFilterOpen(!filterOpen)}
            data-testid="alert-filter-btn"
          >
            Filter <ChevronDown className="w-3 h-3" />
          </button>
          {filterOpen && (
            <div className="absolute right-0 top-full mt-1 w-36 bg-white border border-slate-200 rounded-lg shadow-lg z-10 py-1" data-testid="alert-filter-dropdown">
              {filterOptions.map(opt => (
                <button
                  key={opt.value}
                  className={`w-full text-left px-3 py-1.5 text-[11px] transition-colors ${filter === opt.value ? 'bg-teal-50 text-teal-700 font-semibold' : 'text-slate-600 hover:bg-slate-50'}`}
                  onClick={() => { setFilter(opt.value); setFilterOpen(false); }}
                  data-testid={`alert-filter-${opt.value}`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Alert list */}
      <div className="flex-1 overflow-y-auto" data-testid="alert-list">
        {filtered.length === 0 ? (
          <div className="text-center py-10 text-xs text-slate-400">No alerts match this filter</div>
        ) : (
          filtered.map((alert, i) => {
            const cfg = ALERT_CONFIG[alert.type] || ALERT_CONFIG.not_ordered;
            const Icon = cfg.icon;
            return (
              <div key={i} className={`flex items-start gap-2.5 px-4 py-3 border-b border-slate-50 border-l-[3px] ${cfg.border} hover:bg-slate-50/60 transition-colors`} data-testid={`notif-alert-${i}`}>
                <div className={`w-7 h-7 rounded-lg ${cfg.iconBg} flex items-center justify-center flex-shrink-0 mt-0.5`}>
                  <Icon className={`w-3.5 h-3.5 ${cfg.iconColor}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                    <span className="text-[11px] font-bold text-navy-900">{alert.item_name}</span>
                    <span className={`text-[8px] font-bold uppercase px-1.5 py-0 rounded ${SEV_BADGE[alert.severity] || SEV_BADGE.low}`}>{alert.severity}</span>
                    <span className={`text-[9px] font-semibold px-1.5 py-0 rounded ${cfg.badge}`}>{cfg.label}</span>
                  </div>
                  <p className="text-[10px] text-slate-500 leading-snug">
                    {alert.type === 'price_increase' && (
                      <>{fmtPrice(alert.old_price)} <span className="text-red-500">&rarr;</span> <span className="font-semibold text-red-600">{fmtPrice(alert.new_price)}</span> <span className="text-slate-400">(+{alert.change_pct}%)</span>{alert.vendor && <> &middot; {alert.vendor}</>}</>
                    )}
                    {alert.type === 'cheaper_vendor' && (
                      <>{fmtPrice(alert.current_price)} at {alert.vendor} <span className="text-emerald-500">&rarr;</span> <span className="font-semibold text-emerald-600">{fmtPrice(alert.cheaper_price)}</span> at <span className="font-medium text-emerald-700">{alert.cheaper_vendor}</span> <span className="text-slate-400">(-{alert.savings_pct}%)</span></>
                    )}
                    {alert.type === 'not_ordered' && (
                      <><span className="font-semibold text-amber-600">{alert.days_since}d</span> since last order{alert.vendor && <> &middot; {alert.vendor}</>}{alert.last_price > 0 && <> &middot; {fmtPrice(alert.last_price)}</>}</>
                    )}
                  </p>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Footer */}
      <Link to="/dashboard" onClick={onClose} className="block px-4 py-2.5 border-t border-slate-100 text-center text-[11px] font-semibold text-teal-600 hover:bg-teal-50/50 transition-colors" data-testid="view-all-alerts-link">
        View all on Dashboard
      </Link>
    </div>
  );
});

// ======================== SIDEBAR CONTENT ========================
const SidebarContent = memo(function SidebarContent({ user, pathname, onNavigate, onLogout }) {
  return (
    <div className="flex flex-col h-full bg-navy-950 text-white" data-testid="sidebar">
      <div className="p-5 border-b border-navy-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-teal-600 flex items-center justify-center flex-shrink-0">
            <ChefHat className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-heading font-bold text-sm tracking-tight leading-tight">Restaurant</h1>
            <p className="text-[11px] text-navy-400 font-medium">Accountant AI</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        {mainNav.map(item => (
          <NavLink key={item.path} item={item} isActive={pathname === item.path} onNavigate={onNavigate} />
        ))}
        {user?.role === 'manager' && (
          <>
            <div className="pt-3 pb-1 px-3"><p className="text-[10px] font-bold text-navy-600 uppercase tracking-widest">Management</p></div>
            {managerNav.map(item => (
              <NavLink key={item.path} item={item} isActive={pathname === item.path} onNavigate={onNavigate} />
            ))}
          </>
        )}
      </nav>

      <div className="border-t border-navy-800">
        <div className="px-3 pt-3 pb-1">
          <NavLink item={{ path: '/settings', label: 'Settings', icon: Settings }} isActive={pathname === '/settings'} onNavigate={onNavigate} />
        </div>
        <div className="p-4 pt-2">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-full bg-teal-600 flex items-center justify-center text-xs font-bold flex-shrink-0">
              {user?.name?.charAt(0)?.toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{user?.name || 'User'}</p>
              <p className="text-[11px] text-navy-400 truncate">{user?.restaurant_name || ''}</p>
            </div>
          </div>
          <Button
            onClick={onLogout}
            variant="ghost"
            className="w-full justify-start text-navy-400 hover:text-white hover:bg-navy-800/60 h-8 text-xs"
            data-testid="logout-btn"
          >
            <LogOut className="w-4 h-4 mr-2" />
            Log out
          </Button>
        </div>
      </div>
    </div>
  );
});

// ======================== LAYOUT ========================
export default function Layout({ children }) {
  const { user, api, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const bellContainerRef = useRef(null);

  // Fetch alerts once on mount
  useEffect(() => {
    if (!api) return;
    let mounted = true;
    api.get('/dashboard/summary').then(res => {
      if (mounted) setAlerts(res.data?.smart_alerts || []);
    }).catch(() => {});
    return () => { mounted = false; };
  }, [api]);

  const highCount = useMemo(() => alerts.filter(a => a.severity === 'high').length, [alerts]);

  const handleCloseAlerts = useCallback(() => setAlertsOpen(false), []);
  const handleCloseMobile = useCallback(() => setMobileOpen(false), []);
  const handleToggleAlerts = useCallback(() => setAlertsOpen(prev => !prev), []);

  return (
    <div className="flex h-screen bg-slate-50/80">
      <aside className="hidden lg:flex w-64 flex-shrink-0 border-r border-navy-800">
        <div className="w-full">
          <SidebarContent user={user} pathname={location.pathname} onNavigate={handleCloseMobile} onLogout={logout} />
        </div>
      </aside>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="p-0 w-64 bg-navy-950 border-none">
          <SidebarContent user={user} pathname={location.pathname} onNavigate={handleCloseMobile} onLogout={logout} />
        </SheetContent>
      </Sheet>

      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="h-14 flex items-center justify-between px-4 lg:px-6 glass-header border-b border-slate-200/50 sticky top-0 z-10" data-testid="top-header">
          <div className="flex items-center w-20">
            <button
              onClick={() => setMobileOpen(true)}
              className="lg:hidden p-2 rounded-md hover:bg-slate-100 transition-colors"
              data-testid="mobile-menu-btn"
            >
              <Menu className="w-5 h-5 text-slate-600" />
            </button>
          </div>
          <button
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-slate-100 transition-colors group"
            data-testid="header-home-btn"
          >
            <Home className="w-4 h-4 text-slate-400 group-hover:text-slate-600 transition-colors" />
            <span className="text-xs font-medium text-slate-400 group-hover:text-slate-600 transition-colors hidden sm:inline">Dashboard</span>
          </button>
          <div className="flex items-center justify-end w-20">
            <div className="relative" ref={bellContainerRef}>
              <Button
                variant="ghost"
                size="icon"
                className="relative"
                onClick={handleToggleAlerts}
                data-testid="notifications-btn"
              >
                <Bell className="w-[18px] h-[18px] text-slate-500" />
                {alerts.length > 0 && (
                  <Badge className={`absolute -top-0.5 -right-0.5 h-4 min-w-4 p-0 px-0.5 flex items-center justify-center text-[10px] border-0 ${highCount > 0 ? 'bg-red-500 text-white' : 'bg-amber-500 text-white'}`} data-testid="alert-count-badge">
                    {alerts.length}
                  </Badge>
                )}
              </Button>
              <NotificationPanel alerts={alerts} open={alertsOpen} onClose={handleCloseAlerts} containerRef={bellContainerRef} />
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-auto p-5 lg:p-8">
          {children}
        </div>
      </main>
      <FloatingAssistant />
    </div>
  );
}
