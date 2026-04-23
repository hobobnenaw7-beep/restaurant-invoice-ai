import { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { dataEvents } from '@/lib/dataEvents';
import {
  TrendingUp, TrendingDown, Calendar, DollarSign, Receipt,
  ShoppingCart, ClipboardList, Boxes, ChevronRight, Award,
  AlertTriangle, Activity, Clock,
} from 'lucide-react';

/* ─────────────────────── helpers ─────────────────────── */
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];
const YEAR_OPTIONS = (() => { const cur = new Date().getFullYear(); const y = []; for (let i = 2020; i <= cur + 1; i++) y.push(i); return y; })();

function fmtCurrency(n) {
  if (n == null) return '$0';
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${(n / 1_000).toFixed(1)}k`;
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function pctChange(curr, prev) {
  if (!prev || prev === 0) return null;
  return ((curr - prev) / prev) * 100;
}

/* ────────────────────── % delta pill (the ONLY colored piece) ────────────────────── */
function DeltaPill({ pct, positiveIsGood = true, testId }) {
  if (pct === null || pct === undefined) {
    return <span className="text-[11px] text-slate-400 tabular-nums" data-testid={testId}>—</span>;
  }
  const isUp = pct > 0;
  // For Expenses "positive change" (up) is BAD → red.  For Sales it's GOOD → green.
  const good = positiveIsGood ? isUp : !isUp;
  const color = Math.abs(pct) < 0.1
    ? 'text-slate-400'
    : good ? 'text-emerald-600' : 'text-rose-600';
  const Icon = isUp ? TrendingUp : TrendingDown;
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-semibold tabular-nums ${color}`} data-testid={testId} data-delta-direction={isUp ? 'up' : 'down'}>
      <Icon className="w-3 h-3" />
      {isUp ? '+' : ''}{pct.toFixed(1)}%
    </span>
  );
}

/* ────────────────────── Stat card (neutral) ────────────────────── */
function StatCard({ label, value, pct, positiveIsGood = true, Icon, iconTint = 'text-slate-400', onClick, testId, prevLabel }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative text-left bg-white border border-slate-200 rounded-xl px-5 py-4 hover:border-slate-300 transition-colors w-full"
      data-testid={testId}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">{label}</span>
        {Icon && <Icon className={`w-4 h-4 ${iconTint}`} aria-hidden="true" />}
      </div>
      <div className="mt-2 flex items-baseline gap-3">
        <span className="text-2xl font-bold text-slate-900 tabular-nums" data-testid={`${testId}-value`}>{value}</span>
        <DeltaPill pct={pct} positiveIsGood={positiveIsGood} testId={`${testId}-delta`} />
      </div>
      {prevLabel && (
        <p className="mt-0.5 text-[10px] text-slate-400">vs {prevLabel}</p>
      )}
    </button>
  );
}

/* ────────────────────── Nav card (neutral) ────────────────────── */
function NavCard({ label, Icon, iconTint, to, testId, navigate }) {
  return (
    <button
      type="button"
      onClick={() => navigate(to)}
      className="group flex items-center justify-between bg-white border border-slate-200 rounded-xl px-5 py-4 hover:border-slate-300 transition-colors w-full"
      data-testid={testId}
    >
      <div className="flex items-center gap-3">
        {Icon && <Icon className={`w-4 h-4 ${iconTint}`} aria-hidden="true" />}
        <span className="text-sm font-semibold text-slate-800">{label}</span>
      </div>
      <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-slate-500 transition-colors" />
    </button>
  );
}

/* ────────────────────── Insights: Price Movement ────────────────────── */
function PriceMovement({ alerts, loading, onItemClick }) {
  // Use intelligence alerts (big recent vs older changes) as the price-movement source.
  const rows = useMemo(() => {
    return (alerts || [])
      .map(a => ({
        item: a.item,
        pct: a.change_pct,
        current: a.current_avg,
        previous: a.previous_avg,
      }))
      .sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct))
      .slice(0, 4);
  }, [alerts]);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5" data-testid="price-movement-card">
      <div className="flex items-center gap-2 mb-3">
        <Activity className="w-4 h-4 text-sky-400" aria-hidden="true" />
        <h3 className="text-sm font-semibold text-slate-800">Price Movement</h3>
      </div>
      {loading ? (
        <div className="space-y-2"><Skeleton className="h-8" /><Skeleton className="h-8" /><Skeleton className="h-8" /></div>
      ) : rows.length === 0 ? (
        <p className="text-xs text-slate-400" data-testid="price-movement-empty">No notable movement in this period.</p>
      ) : (
        <div className="space-y-1.5">
          {rows.map((r, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onItemClick?.(r.item)}
              className="w-full flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-slate-50 transition-colors text-left"
              data-testid={`price-movement-row-${i}`}
            >
              <span className="text-xs text-slate-700 truncate flex-1">{r.item}</span>
              <span className="text-[11px] text-slate-500 tabular-nums flex-shrink-0">
                ${r.previous.toFixed(2)} → ${r.current.toFixed(2)}
              </span>
              <DeltaPill pct={r.pct} positiveIsGood={false} testId={`price-movement-delta-${i}`} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ────────────────────── Insights: Best Vendor ────────────────────── */
function BestVendor({ comparison, loading, onItemClick }) {
  const rows = useMemo(() => {
    return (comparison || [])
      .filter(c => c.best_vendor && c.vendor_count > 1 && c.savings_pct > 0)
      .slice(0, 4);
  }, [comparison]);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5" data-testid="best-vendor-card">
      <div className="flex items-center gap-2 mb-3">
        <Award className="w-4 h-4 text-amber-400" aria-hidden="true" />
        <h3 className="text-sm font-semibold text-slate-800">Best Vendor</h3>
      </div>
      {loading ? (
        <div className="space-y-2"><Skeleton className="h-8" /><Skeleton className="h-8" /><Skeleton className="h-8" /></div>
      ) : rows.length === 0 ? (
        <p className="text-xs text-slate-400" data-testid="best-vendor-empty">Not enough data to compare vendors yet.</p>
      ) : (
        <div className="space-y-1.5">
          {rows.map((r, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onItemClick?.(r.item)}
              className="w-full flex items-center justify-between gap-3 px-2 py-1.5 rounded-md hover:bg-slate-50 transition-colors text-left"
              data-testid={`best-vendor-row-${i}`}
            >
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-slate-800 truncate">{r.item}</p>
                <p className="text-[11px] text-slate-500 truncate">{r.best_vendor}</p>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-xs font-semibold text-slate-900 tabular-nums">${r.best_price?.toFixed(2)}</p>
                <p className="text-[10px] text-slate-400">{r.vendor_count} vendors</p>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ────────────────────── Insights: Alerts ────────────────────── */
function AlertsCard({ alerts, loading, onItemClick }) {
  const severe = useMemo(() => {
    return (alerts || [])
      .filter(a => a.severity === 'high' || Math.abs(a.change_pct) >= 10)
      .sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct))
      .slice(0, 5);
  }, [alerts]);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5" data-testid="alerts-card">
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="w-4 h-4 text-rose-400" aria-hidden="true" />
        <h3 className="text-sm font-semibold text-slate-800">Alerts</h3>
      </div>
      {loading ? (
        <div className="space-y-2"><Skeleton className="h-8" /><Skeleton className="h-8" /></div>
      ) : severe.length === 0 ? (
        <p className="text-xs text-slate-400" data-testid="alerts-empty">No active alerts. Everything looks calm.</p>
      ) : (
        <div className="space-y-1.5">
          {severe.map((a, i) => {
            const high = a.severity === 'high' || Math.abs(a.change_pct) >= 20;
            const cls = high
              ? 'bg-rose-50 border-rose-200 text-rose-800'
              : 'bg-amber-50 border-amber-200 text-amber-800';
            return (
              <button
                key={i}
                type="button"
                onClick={() => onItemClick?.(a.item)}
                className={`w-full flex items-center justify-between gap-3 px-3 py-1.5 rounded-md border text-left transition-opacity hover:opacity-90 ${cls}`}
                data-testid={`alert-row-${i}`}
                data-severity={a.severity}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="w-1.5 h-1.5 rounded-full bg-current flex-shrink-0" aria-hidden="true" />
                  <span className="text-xs font-medium truncate">{a.item}</span>
                </div>
                <span className="text-[11px] font-bold tabular-nums flex-shrink-0">
                  {a.change_pct > 0 ? '+' : ''}{a.change_pct.toFixed(1)}%
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ────────────────────── Data Freshness ────────────────────── */
function DataFreshness({ lastUpdate, purchaseCount }) {
  const ago = useMemo(() => {
    if (!lastUpdate) return null;
    try {
      const d = new Date(lastUpdate);
      const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
      if (diffMin < 1) return 'just now';
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffHr = Math.floor(diffMin / 60);
      if (diffHr < 24) return `${diffHr}h ago`;
      return `${Math.floor(diffHr / 24)}d ago`;
    } catch { return null; }
  }, [lastUpdate]);
  if (!ago) return null;
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-slate-400" data-testid="data-freshness">
      <Clock className="w-3 h-3" aria-hidden="true" />
      <span>Updated {ago}</span>
      <span className="text-slate-300">·</span>
      <span>Based on {purchaseCount || 0} purchase records</span>
    </div>
  );
}

/* ═══════════════════════ MAIN PAGE ═══════════════════════ */
export default function DashboardPage() {
  const { api } = useAuth();
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [intel, setIntel] = useState({ alerts: [], comparison: [] });
  const [loading, setLoading] = useState(true);
  const [intelLoading, setIntelLoading] = useState(true);

  const now = new Date();
  const [filterYear, setFilterYear] = useState(now.getFullYear());
  const [filterMonth, setFilterMonth] = useState(0);

  const load = useCallback(async (yr, mo) => {
    try {
      const params = {};
      if (yr) params.year = yr;
      if (mo !== undefined) params.month = mo;
      const res = await api.get('/dashboard/summary', { params });
      setData(res.data);
    } catch { toast.error('Failed to load dashboard'); }
    finally { setLoading(false); }
  }, [api]);

  const loadIntel = useCallback(async () => {
    try {
      const [intelRes, cmpRes] = await Promise.all([
        api.get('/prices/intelligence'),
        api.get('/prices/vendor-comparison'),
      ]);
      setIntel({
        alerts: intelRes.data?.price_alerts || [],
        comparison: cmpRes.data?.items || [],
      });
    } catch {
      // Silent — insights are optional; the main stat cards still show.
      setIntel({ alerts: [], comparison: [] });
    } finally { setIntelLoading(false); }
  }, [api]);

  useEffect(() => { load(filterYear, filterMonth); }, [load, filterYear, filterMonth]);
  useEffect(() => { loadIntel(); }, [loadIntel]);
  useEffect(() => dataEvents.subscribe(() => {
    load(filterYear, filterMonth);
    loadIntel();
  }), [load, loadIntel, filterYear, filterMonth]);

  const periodLabel = useMemo(() => {
    if (filterMonth > 0) return `${MONTH_NAMES[filterMonth - 1]} ${filterYear}`;
    return `Full Year ${filterYear}`;
  }, [filterYear, filterMonth]);

  const prevLabel = useMemo(() => {
    if (filterMonth > 0) {
      const pm = filterMonth === 1 ? 12 : filterMonth - 1;
      const py = filterMonth === 1 ? filterYear - 1 : filterYear;
      return `${MONTH_NAMES[pm - 1]} ${py}`;
    }
    return `${filterYear - 1}`;
  }, [filterYear, filterMonth]);

  if (loading) {
    return (
      <div className="space-y-5 max-w-[1100px]" data-testid="dashboard-loading">
        <div><Skeleton className="h-8 w-48 mb-2" /><Skeleton className="h-4 w-72" /></div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Skeleton className="h-24 rounded-xl" /><Skeleton className="h-24 rounded-xl" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Skeleton className="h-20 rounded-xl" /><Skeleton className="h-20 rounded-xl" /><Skeleton className="h-20 rounded-xl" />
        </div>
      </div>
    );
  }

  const salesNow = data?.month_sales || 0;
  const salesPrev = data?.prev_month_sales || 0;
  const expensesNow = (data?.month_raw_materials || 0) + (data?.month_salaries || 0) + (data?.month_other_expenses || 0);
  const expensesPrev = (data?.prev_month_raw_materials || 0) + (data?.prev_month_salaries || 0) + (data?.prev_month_other_expenses || 0);

  return (
    <div className="space-y-6 max-w-[1100px]" data-testid="dashboard-page">
      {/* ── header ── */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">A calm, focused view of the numbers that matter.</p>
      </div>

      {/* ── Period filter ── */}
      <div className="flex items-center gap-3 flex-wrap" data-testid="dashboard-period-filters">
        <div className="flex items-center gap-1.5">
          <Calendar className="w-4 h-4 text-slate-400" aria-hidden="true" />
          <span className="text-xs font-semibold text-slate-500">Period</span>
        </div>
        <Select value={String(filterYear)} onValueChange={(v) => setFilterYear(Number(v))}>
          <SelectTrigger className="w-[100px] h-8 text-xs bg-white" data-testid="filter-year">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {YEAR_OPTIONS.map(y => <SelectItem key={y} value={String(y)} className="text-xs">{y}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={String(filterMonth)} onValueChange={(v) => setFilterMonth(Number(v))}>
          <SelectTrigger className="w-[140px] h-8 text-xs bg-white" data-testid="filter-month">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="0" className="text-xs font-semibold">All Months</SelectItem>
            {MONTH_NAMES.map((m, i) => (
              <SelectItem key={i + 1} value={String(i + 1)} className="text-xs">{m}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-[11px] text-slate-400 hidden sm:inline">{periodLabel}</span>
        <div className="flex-1" />
        <DataFreshness lastUpdate={data?.last_data_update} purchaseCount={data?.purchase_count} />
      </div>

      {/* ── Row 1: Sales + Expenses ── */}
      <Card className="border-0 shadow-none bg-transparent">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="stats-row-1">
          <StatCard
            label="Sales"
            value={fmtCurrency(salesNow)}
            pct={pctChange(salesNow, salesPrev)}
            positiveIsGood
            Icon={DollarSign}
            iconTint="text-emerald-300"
            onClick={() => navigate('/sales')}
            testId="stat-sales"
            prevLabel={prevLabel}
          />
          <StatCard
            label="Expenses"
            value={fmtCurrency(expensesNow)}
            pct={pctChange(expensesNow, expensesPrev)}
            positiveIsGood={false}
            Icon={Receipt}
            iconTint="text-rose-300"
            onClick={() => navigate('/expenses')}
            testId="stat-expenses"
            prevLabel={prevLabel}
          />
        </div>
      </Card>

      {/* ── Row 2: Orders / Procurement / Items ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4" data-testid="stats-row-2">
        <NavCard
          label="Orders" Icon={ShoppingCart} iconTint="text-sky-300"
          to="/orders" testId="nav-orders" navigate={navigate}
        />
        <NavCard
          label="Procurement" Icon={ClipboardList} iconTint="text-indigo-300"
          to="/procurement" testId="nav-procurement" navigate={navigate}
        />
        <NavCard
          label="Items" Icon={Boxes} iconTint="text-teal-300"
          to="/items" testId="nav-items" navigate={navigate}
        />
      </div>

      {/* ── Insights ── */}
      <div className="pt-2" data-testid="insights-section">
        <h2 className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-3">Insights</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <PriceMovement
            alerts={intel.alerts}
            loading={intelLoading}
            onItemClick={() => navigate('/procurement')}
          />
          <BestVendor
            comparison={intel.comparison}
            loading={intelLoading}
            onItemClick={() => navigate('/procurement')}
          />
          <AlertsCard
            alerts={intel.alerts}
            loading={intelLoading}
            onItemClick={() => navigate('/procurement')}
          />
        </div>
      </div>
    </div>
  );
}
