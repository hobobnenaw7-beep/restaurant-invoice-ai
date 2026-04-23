import { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { dataEvents } from '@/lib/dataEvents';
import {
  TrendingUp, TrendingDown, Calendar, DollarSign, Receipt,
  ShoppingCart, ClipboardList, Boxes, ChevronRight, Award,
  AlertTriangle, Activity, Clock, ArrowRight,
} from 'lucide-react';

/* ─────────────────────── helpers ─────────────────────── */
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];
const YEAR_OPTIONS = (() => { const cur = new Date().getFullYear(); const y = []; for (let i = 2020; i <= cur + 1; i++) y.push(i); return y; })();

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

/* ────────────────────── Circular Nav Card ────────────────────── */
// Ring tokens tuned to match the reference: thick pastel outer band,
// lighter inner fill, strong-color icon in the middle.
const RING_TINT = {
  sales:       { outer: 'bg-emerald-100', inner: 'bg-emerald-50/70', icon: 'text-emerald-600', link: 'text-emerald-600 hover:text-emerald-700', track: '#d1fae5', arc: '#10b981' },
  expenses:    { outer: 'bg-rose-100',    inner: 'bg-rose-50/70',    icon: 'text-rose-600',    link: 'text-rose-600 hover:text-rose-700',       track: '#ffe4e6', arc: '#f43f5e' },
  orders:      { outer: 'bg-sky-100',     inner: 'bg-sky-50/70',     icon: 'text-sky-600',     link: 'text-sky-600 hover:text-sky-700' },
  procurement: { outer: 'bg-orange-100',  inner: 'bg-orange-50/70',  icon: 'text-orange-600',  link: 'text-orange-600 hover:text-orange-700' },
  items:       { outer: 'bg-purple-100',  inner: 'bg-purple-50/70',  icon: 'text-purple-600',  link: 'text-purple-600 hover:text-purple-700' },
};

/* SubtleDonut — SVG progress ring. pct is the change vs previous period;
   we plot |pct| capped at 100% as an arc. Uses the card's own pastel
   palette so no new colors enter the design. */
function SubtleDonut({ pct, tint, Icon, size = 80, testId }) {
  const stroke = 5;
  const radius = (size - stroke) / 2;
  const circ = 2 * Math.PI * radius;
  const magnitude = Math.min(100, Math.abs(pct ?? 0));
  const dash = (magnitude / 100) * circ;
  return (
    <div className="relative" style={{ width: size, height: size }} data-testid={testId}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          stroke={tint.track} strokeWidth={stroke} fill="none"
        />
        {pct !== null && pct !== undefined && (
          <circle
            cx={size / 2} cy={size / 2} r={radius}
            stroke={tint.arc} strokeWidth={stroke} fill="none"
            strokeDasharray={`${dash} ${circ}`}
            strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 0.6s ease-out' }}
          />
        )}
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <div className={`w-14 h-14 rounded-full ${tint.inner} flex items-center justify-center`}>
          <Icon className={`w-6 h-6 ${tint.icon}`} strokeWidth={2.2} />
        </div>
      </div>
    </div>
  );
}

function CircleNavCard({ tintKey, label, linkLabel, Icon, to, testId, navigate, pct }) {
  const t = RING_TINT[tintKey];
  const hasDonut = pct !== undefined;
  const direction = pct > 0 ? 'up' : pct < 0 ? 'down' : 'flat';

  return (
    <button
      type="button"
      onClick={() => navigate(to)}
      className="group w-full bg-white border border-slate-200 rounded-2xl px-6 py-8 flex flex-col items-center gap-3 transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 hover:border-slate-300 active:translate-y-0"
      data-testid={testId}
      data-tint={tintKey}
    >
      {hasDonut ? (
        <div className="transition-transform duration-200 group-hover:scale-105">
          <SubtleDonut pct={pct} tint={t} Icon={Icon} size={84} testId={`${testId}-donut`} />
        </div>
      ) : (
        /* Annular ring: outer pastel band + lighter inner disc + strong icon */
        <div className={`relative w-20 h-20 rounded-full ${t.outer} flex items-center justify-center transition-transform duration-200 group-hover:scale-105`} aria-hidden="true">
          <div className={`w-14 h-14 rounded-full ${t.inner} flex items-center justify-center`}>
            <Icon className={`w-6 h-6 ${t.icon}`} strokeWidth={2.2} />
          </div>
        </div>
      )}

      <span className="text-base font-semibold text-slate-900 mt-1">{label}</span>

      {hasDonut && pct !== null && (
        <span
          className={`inline-flex items-center gap-1 text-[11px] font-semibold tabular-nums ${t.icon}`}
          data-testid={`${testId}-pct`}
          data-direction={direction}
        >
          {pct > 0 ? <TrendingUp className="w-3 h-3" /> : pct < 0 ? <TrendingDown className="w-3 h-3" /> : null}
          {pct > 0 ? '+' : ''}{Number(pct).toFixed(1)}%
        </span>
      )}

      <span className={`inline-flex items-center gap-1.5 text-[12px] font-medium ${t.link} transition-colors`}>
        {linkLabel}
        <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
      </span>
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

  const prevLabel = useMemo(() => {  // eslint-disable-line no-unused-vars
    if (filterMonth > 0) {
      const pm = filterMonth === 1 ? 12 : filterMonth - 1;
      const py = filterMonth === 1 ? filterYear - 1 : filterYear;
      return `${MONTH_NAMES[pm - 1]} ${py}`;
    }
    return `${filterYear - 1}`;
  }, [filterYear, filterMonth]);

  // % change values for the Sales + Expenses donuts.
  const salesPct = useMemo(() => pctChange(
    data?.month_sales || 0,
    data?.prev_month_sales || 0,
  ), [data]);
  const expensesPct = useMemo(() => {
    const now = (data?.month_raw_materials || 0) + (data?.month_salaries || 0) + (data?.month_other_expenses || 0);
    const prev = (data?.prev_month_raw_materials || 0) + (data?.prev_month_salaries || 0) + (data?.prev_month_other_expenses || 0);
    return pctChange(now, prev);
  }, [data]);

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

  return (
    <div className="space-y-6 max-w-[1100px]" data-testid="dashboard-page">
      {/* ── header ── */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">A calm, focused view of the numbers that matter.</p>
      </div>

      {/* ── Row 1: Sales + Expenses circular navigation ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="stats-row-1">
        <CircleNavCard
          tintKey="sales"
          label="Sales"
          linkLabel="View sales dashboard"
          Icon={DollarSign}
          to="/sales"
          testId="stat-sales"
          navigate={navigate}
          pct={salesPct}
        />
        <CircleNavCard
          tintKey="expenses"
          label="Expenses"
          linkLabel="View expenses dashboard"
          Icon={Receipt}
          to="/expenses"
          testId="stat-expenses"
          navigate={navigate}
          pct={expensesPct}
        />
      </div>

      {/* ── Row 2: Orders / Procurement / Items circular navigation ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4" data-testid="stats-row-2">
        <CircleNavCard
          tintKey="orders"
          label="Orders"
          linkLabel="View orders"
          Icon={ShoppingCart}
          to="/orders"
          testId="nav-orders"
          navigate={navigate}
        />
        <CircleNavCard
          tintKey="procurement"
          label="Procurement"
          linkLabel="View procurement"
          Icon={ClipboardList}
          to="/procurement"
          testId="nav-procurement"
          navigate={navigate}
        />
        <CircleNavCard
          tintKey="items"
          label="Items"
          linkLabel="View items"
          Icon={Boxes}
          to="/items"
          testId="nav-items"
          navigate={navigate}
        />
      </div>

      {/* ── Period filter (now BELOW the nav, above insights) ── */}
      <div className="flex items-center gap-3 flex-wrap pt-2" data-testid="dashboard-period-filters">
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
