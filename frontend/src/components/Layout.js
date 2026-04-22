import { useState, useEffect, useCallback, useMemo, useRef, memo } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import FloatingAssistant from '@/components/FloatingAssistant';
import {
  LayoutDashboard, Receipt, DollarSign, Users,
  Package, FileText, FolderArchive, Settings, Bell, Menu, LogOut, ChefHat, UserCog, ClipboardCheck,
  TrendingUp, ArrowRightLeft, Clock, ChevronDown, ChevronRight, ShoppingCart, Shield, Home, Sparkles,
} from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────
// Navigation tree — groups use `children`, links use `path`.
// `perm` on a group hides the whole group. Per-child `perm` hides leaves.
// ─────────────────────────────────────────────────────────────────────
const navTree = [
  { type: 'link', path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, perm: 'view_dashboard' },
  { type: 'link', path: '/orders',    label: 'Orders',    icon: ShoppingCart,    perm: 'view_expenses' },
  { type: 'group', key: 'expenses', label: 'Expenses', icon: Receipt, perm: 'view_expenses', matchPrefix: '/expenses',
    children: [
      { path: '/expenses?tab=raw_materials', label: 'Raw Materials',   matchQuery: { tab: 'raw_materials' } },
      { path: '/expenses?tab=salaries',      label: 'Salaries',        matchQuery: { tab: 'salaries' } },
      { path: '/expenses?tab=other',         label: 'Other Expenses',  matchQuery: { tab: 'other' } },
    ]},
  { type: 'link', path: '/sales', label: 'Sales', icon: DollarSign, perm: 'view_sales' },
  { type: 'group', key: 'items', label: 'Items', icon: Package, perm: 'view_items', matchPrefix: '/items',
    children: [
      { path: '/items',             label: 'Item Catalog' },
      { path: '/correction-memory', label: 'Product Matching Rules', perm: 'view_expenses' },
    ]},
  { type: 'group', key: 'vendors', label: 'Vendors', icon: Users, perm: 'view_vendors', matchPrefix: '/vendors',
    children: [
      { path: '/vendors',            label: 'Vendor Directory' },
      { path: '/vendor-comparison',  label: 'Vendor Pricing ($/LB)' },
    ]},
  { type: 'link', path: '/reports', label: 'Reports', icon: FileText, perm: 'view_reports' },
  { type: 'group', key: 'procurement', label: 'Procurement', icon: Sparkles, perm: 'view_reports', matchPrefix: '/procurement',
    children: [
      { path: '/procurement/smart-purchases', label: 'Smart Purchases' },
      { path: '/procurement/price-insights',  label: 'Price Intelligence' },
      { path: '/procurement/decisions',       label: 'Decisions' },
      { path: '/procurement/suggestions',     label: 'Suggestions Inbox' },
    ]},
  { type: 'link', path: '/records', label: 'Records Library', icon: FolderArchive, perm: 'view_records' },
];

const managerNav = [
  { path: '/users',     label: 'User Management', icon: UserCog, perm: 'view_users' },
  { path: '/approvals', label: 'Approvals',       icon: ClipboardCheck, perm: 'view_users' },
  { path: '/audit-log', label: 'Audit Log',       icon: Shield, perm: 'view_users' },
];

// ──────────────────────────────────────────────────────────────────────
const ALERT_CONFIG = {
  price_increase: { label: 'Price Increase', icon: TrendingUp, border: 'border-l-red-500', iconBg: 'bg-red-100', iconColor: 'text-red-600', badge: 'bg-red-100 text-red-700' },
  cheaper_vendor: { label: 'Cheaper Vendor', icon: ArrowRightLeft, border: 'border-l-emerald-500', iconBg: 'bg-emerald-100', iconColor: 'text-emerald-600', badge: 'bg-emerald-100 text-emerald-700' },
  not_ordered:    { label: 'Not Ordered',    icon: Clock, border: 'border-l-amber-500', iconBg: 'bg-amber-100', iconColor: 'text-amber-600', badge: 'bg-amber-100 text-amber-700' },
};
const SEV_ORDER = { high: 0, medium: 1, low: 2 };
const SEV_BADGE = {
  high: 'bg-red-600 text-white',
  medium: 'bg-amber-500 text-white',
  low: 'bg-slate-400 text-white',
};
function fmtPrice(n) { return `$${Number(n).toFixed(2)}`; }

// ─── Active-match helpers ────────────────────────────────────────────
function isChildActive(child, pathname, search) {
  if (child.matchQuery) {
    if (pathname !== child.path.split('?')[0]) return false;
    const params = new URLSearchParams(search);
    return Object.entries(child.matchQuery).every(([k, v]) => params.get(k) === v);
  }
  return pathname === child.path;
}
function isLinkActive(item, pathname) {
  return pathname === item.path;
}
function isGroupActive(group, pathname, search) {
  if (group.matchPrefix && pathname.startsWith(group.matchPrefix)) return true;
  return (group.children || []).some(c => isChildActive(c, pathname, search));
}

// ─── NavLink (leaf) ──────────────────────────────────────────────────
const NavLink = memo(function NavLink({ item, isActive, onNavigate }) {
  const Icon = item.icon;
  return (
    <Link
      to={item.path}
      onClick={onNavigate}
      data-testid={`nav-${item.path.replace(/^\//, '').replace(/[/?=&]/g, '-')}`}
      className={`flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors duration-150 ${
        isActive
          ? 'bg-teal-600/15 text-teal-400'
          : 'text-navy-400 hover:text-white hover:bg-navy-800/60'
      }`}
    >
      {Icon && <Icon className="w-[18px] h-[18px] flex-shrink-0" />}
      <span>{item.label}</span>
    </Link>
  );
});

// ─── NavGroup (expandable) ───────────────────────────────────────────
const NavGroup = memo(function NavGroup({ group, pathname, search, perms, onNavigate, forceOpen }) {
  const active = isGroupActive(group, pathname, search);
  const [open, setOpen] = useState(active || !!forceOpen);
  useEffect(() => { if (active) setOpen(true); }, [active]);

  const children = (group.children || []).filter(c => !c.perm || perms[c.perm]);
  if (children.length === 0) return null;
  const Icon = group.icon;

  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        data-testid={`nav-group-${group.key}`}
        className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors duration-150 ${
          active
            ? 'bg-teal-600/15 text-teal-400'
            : 'text-navy-400 hover:text-white hover:bg-navy-800/60'
        }`}
      >
        {Icon && <Icon className="w-[18px] h-[18px] flex-shrink-0" />}
        <span className="flex-1 text-left">{group.label}</span>
        {open
          ? <ChevronDown className="w-4 h-4 flex-shrink-0 opacity-70" />
          : <ChevronRight className="w-4 h-4 flex-shrink-0 opacity-70" />}
      </button>
      {open && (
        <div className="ml-3 pl-3 border-l border-navy-800 mt-0.5 mb-1 space-y-0.5" data-testid={`nav-group-${group.key}-children`}>
          {children.map(c => {
            const activeChild = isChildActive(c, pathname, search);
            return (
              <Link
                key={c.path}
                to={c.path}
                onClick={onNavigate}
                data-testid={`nav-child-${group.key}-${c.label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}`}
                className={`block px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors duration-150 ${
                  activeChild
                    ? 'bg-teal-600/15 text-teal-400'
                    : 'text-navy-500 hover:text-white hover:bg-navy-800/60'
                }`}
              >
                {c.label}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
});

// ─── NotificationPanel (unchanged) ───────────────────────────────────
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
  }, [open, containerRef]);

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
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <Bell className="w-4 h-4 text-navy-900" />
          <span className="text-xs font-bold text-navy-900">Smart Alerts</span>
          <Badge className="text-[9px] bg-slate-100 text-slate-500 h-4 px-1.5">{alerts.length}</Badge>
        </div>
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

      <Link to="/dashboard" onClick={onClose} className="block px-4 py-2.5 border-t border-slate-100 text-center text-[11px] font-semibold text-teal-600 hover:bg-teal-50/50 transition-colors" data-testid="view-all-alerts-link">
        View all on Dashboard
      </Link>
    </div>
  );
});

// ─── Sidebar ─────────────────────────────────────────────────────────
const SidebarContent = memo(function SidebarContent({ user, pathname, search, onNavigate, onLogout }) {
  const perms = user?.permissions || {};
  const filteredTree = navTree.filter(n => !n.perm || perms[n.perm]);
  const filteredManager = managerNav.filter(n => !n.perm || perms[n.perm]);

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
        {filteredTree.map(n => n.type === 'link'
          ? <NavLink key={n.path} item={n} isActive={isLinkActive(n, pathname)} onNavigate={onNavigate} />
          : <NavGroup key={n.key} group={n} pathname={pathname} search={search} perms={perms} onNavigate={onNavigate} />
        )}

        {filteredManager.length > 0 && (
          <>
            <div className="pt-3 pb-1 px-3"><p className="text-[10px] font-bold text-navy-600 uppercase tracking-widest">Management</p></div>
            {filteredManager.map(item => (
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

// ─── Layout ──────────────────────────────────────────────────────────
export default function Layout({ children }) {
  const { user, api, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const bellContainerRef = useRef(null);

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
          <SidebarContent user={user} pathname={location.pathname} search={location.search} onNavigate={handleCloseMobile} onLogout={logout} />
        </div>
      </aside>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="p-0 w-64 bg-navy-950 border-none">
          <SidebarContent user={user} pathname={location.pathname} search={location.search} onNavigate={handleCloseMobile} onLogout={logout} />
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
