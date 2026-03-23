import { useState, useEffect, useCallback, useMemo, memo, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  TrendingUp, TrendingDown, ArrowRightLeft,
  Loader2, BarChart3, Search, Package, Store, Tag,
  PieChart as PieChartIcon, Lightbulb, X
} from 'lucide-react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';

function fmt(n) {
  if (n == null) return '$0';
  if (Math.abs(n) >= 1000) return `$${(n / 1000).toFixed(1)}k`;
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}
function fmtFull(n) {
  return n != null ? `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '$0.00';
}
function fmtPrice(n) { return n != null ? `$${Number(n).toFixed(2)}` : '$0.00'; }
function pctChange(curr, prev) {
  if (!prev || prev === 0) return null;
  return ((curr - prev) / prev * 100).toFixed(1);
}

const DONUT_COLORS = ['#0d9488', '#6366f1', '#64748b'];
const DONUT_BG = ['bg-teal-500', 'bg-indigo-500', 'bg-slate-500'];
const CATS = ['Raw Materials', 'Salaries', 'Other'];

// ======================== DONUT CHART ========================
const DonutChart = memo(function DonutChart({ raw, salaries, other, prevRaw, prevSalaries, prevOther }) {
  const total = raw + salaries + other;
  const prevTotal = prevRaw + prevSalaries + prevOther;

  const segments = useMemo(() => [
    { name: 'Raw Materials', value: raw, color: DONUT_COLORS[0] },
    { name: 'Salaries', value: salaries, color: DONUT_COLORS[1] },
    { name: 'Other', value: other, color: DONUT_COLORS[2] },
  ].filter(s => s.value > 0), [raw, salaries, other]);

  const pctTotal = pctChange(total, prevTotal);
  const noData = useMemo(() => [{ name: 'No data', value: 1 }], []);
  const tooltipEl = useMemo(() => <DonutTooltip total={total} />, [total]);

  const insights = useMemo(() => {
    const result = [];
    [{ name: 'Raw Materials', cur: raw, prev: prevRaw },
     { name: 'Salaries', cur: salaries, prev: prevSalaries },
     { name: 'Other', cur: other, prev: prevOther }]
      .forEach(cat => {
        const p = pctChange(cat.cur, cat.prev);
        if (p !== null && Math.abs(p) > 3) {
          result.push({ name: cat.name, pct: parseFloat(p), up: p > 0 });
        }
      });
    return result;
  }, [raw, salaries, other, prevRaw, prevSalaries, prevOther]);

  return (
    <Card className="border border-slate-100 shadow-sm" data-testid="donut-chart-card">
      <CardHeader className="pb-2 pt-5 px-6">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-navy-900 flex items-center justify-center">
            <PieChartIcon className="w-4 h-4 text-white" />
          </div>
          <div>
            <CardTitle className="font-heading text-sm font-bold text-navy-900">Monthly Spending</CardTitle>
            <p className="text-[10px] text-slate-400">Where your money goes this month</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-6 pb-5">
        <div className="flex flex-col sm:flex-row items-center gap-6">
          <div className="relative w-44 h-44 flex-shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={segments.length > 0 ? segments : noData}
                  cx="50%" cy="50%"
                  innerRadius={52} outerRadius={72}
                  paddingAngle={segments.length > 1 ? 3 : 0}
                  dataKey="value" stroke="none"
                >
                  {segments.length > 0
                    ? segments.map((s, i) => <Cell key={i} fill={s.color} />)
                    : <Cell fill="#e2e8f0" />}
                </Pie>
                <Tooltip content={tooltipEl} />
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Total</span>
              <span className="text-lg font-extrabold text-navy-900 tabular-nums">{fmt(total)}</span>
              {pctTotal !== null && (
                <span className={`text-[10px] font-semibold ${pctTotal > 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                  {pctTotal > 0 ? '+' : ''}{pctTotal}%
                </span>
              )}
            </div>
          </div>

          <div className="flex-1 space-y-3 w-full">
            <div className="space-y-2.5">
              {[
                { label: 'Raw Materials', value: raw, bg: DONUT_BG[0] },
                { label: 'Salaries', value: salaries, bg: DONUT_BG[1] },
                { label: 'Other', value: other, bg: DONUT_BG[2] },
              ].map(cat => {
                const pctVal = total > 0 ? ((cat.value / total) * 100).toFixed(1) : 0;
                return (
                  <div key={cat.label} className="flex items-center justify-between" data-testid={`donut-legend-${cat.label.toLowerCase().replace(/\s/g, '-')}`}>
                    <div className="flex items-center gap-2">
                      <div className={`w-2.5 h-2.5 rounded-sm ${cat.bg}`} />
                      <span className="text-xs text-slate-600">{cat.label}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-navy-900 tabular-nums">{fmtFull(cat.value)}</span>
                      <Badge variant="secondary" className="text-[9px] h-4 px-1.5 tabular-nums">{pctVal}%</Badge>
                    </div>
                  </div>
                );
              })}
            </div>
            {insights.length > 0 && (
              <div className="border-t border-slate-100 pt-2.5 space-y-1" data-testid="category-insights">
                {insights.map((ins, i) => (
                  <div key={i} className={`flex items-center gap-2 px-2.5 py-1.5 rounded-md text-xs ${ins.up ? 'bg-red-50/70 text-red-700' : 'bg-emerald-50/70 text-emerald-700'}`} data-testid={`category-insight-${i}`}>
                    {ins.up ? <TrendingUp className="w-3 h-3 flex-shrink-0" /> : <TrendingDown className="w-3 h-3 flex-shrink-0" />}
                    <span>
                      <span className="font-bold">{ins.name}</span> {ins.up ? 'increased' : 'decreased'} by <span className="font-bold">{Math.abs(ins.pct)}%</span> this month
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
});

function DonutTooltip({ active, payload, total }) {
  if (!active || !payload?.length) return null;
  const d = payload[0];
  const pct = total > 0 ? ((d.value / total) * 100).toFixed(1) : 0;
  return (
    <div className="bg-white border border-slate-200 rounded-lg px-3 py-2 shadow-lg">
      <p className="text-xs font-semibold" style={{ color: d.payload.color }}>{d.name}</p>
      <p className="text-sm font-bold text-navy-900">{fmtFull(d.value)} ({pct}%)</p>
    </div>
  );
}

// ======================== MARKET INSIGHTS ========================
const MarketInsights = memo(function MarketInsights({ alerts }) {
  if (!alerts.length) return (
    <Card className="border border-slate-100 shadow-sm" data-testid="market-insights-card">
      <CardContent className="py-10 text-center">
        <Lightbulb className="w-8 h-8 text-slate-300 mx-auto mb-3" />
        <p className="text-sm text-slate-400">No market insights yet. Add more purchase data to see recommendations.</p>
      </CardContent>
    </Card>
  );

  return (
    <Card className="border border-slate-100 shadow-sm" data-testid="market-insights-card">
      <CardHeader className="pb-2 pt-5 px-6">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-amber-500 flex items-center justify-center">
            <Lightbulb className="w-4 h-4 text-white" />
          </div>
          <div>
            <CardTitle className="font-heading text-sm font-bold text-navy-900">Market Insights</CardTitle>
            <p className="text-[10px] text-slate-400">Actionable tips from your purchase data</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-6 pb-5">
        <div className="space-y-2" data-testid="insights-list">
          {alerts.map((a, i) => <InsightRow key={i} alert={a} index={i} />)}
        </div>
      </CardContent>
    </Card>
  );
});

function InsightRow({ alert, index }) {
  const isPrice = alert.type === 'price_increase';
  const isCheaper = alert.type === 'cheaper_vendor';

  if (isPrice) {
    return (
      <div className="flex items-start gap-3 p-3 rounded-lg border border-red-100 bg-red-50/40" data-testid={`insight-${index}`}>
        <TrendingUp className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
        <div className="min-w-0">
          <p className="text-xs text-slate-700">
            <span className="font-bold text-navy-900">{alert.item_name}</span> price up <span className="font-bold text-red-600">+{alert.change_pct}%</span>
          </p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            {fmtPrice(alert.old_price)} &rarr; {fmtPrice(alert.new_price)} at {alert.vendor}
          </p>
        </div>
      </div>
    );
  }

  if (isCheaper) {
    return (
      <div className="flex items-start gap-3 p-3 rounded-lg border border-teal-100 bg-teal-50/40" data-testid={`insight-${index}`}>
        <ArrowRightLeft className="w-4 h-4 text-teal-600 mt-0.5 flex-shrink-0" />
        <div className="min-w-0">
          <p className="text-xs text-slate-700">
            Save <span className="font-bold text-teal-600">{alert.savings_pct}%</span> on <span className="font-bold text-navy-900">{alert.item_name}</span>
          </p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            Switch from {alert.vendor} ({fmtPrice(alert.current_price)}) to <span className="font-semibold text-teal-700">{alert.cheaper_vendor}</span> ({fmtPrice(alert.cheaper_price)})
          </p>
        </div>
      </div>
    );
  }

  // not_ordered
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg border border-amber-100 bg-amber-50/40" data-testid={`insight-${index}`}>
      <Package className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
      <div className="min-w-0">
        <p className="text-xs text-slate-700">
          <span className="font-bold text-navy-900">{alert.item_name}</span> not ordered in <span className="font-bold text-amber-700">{alert.days_since} days</span>
        </p>
        {alert.vendor && (
          <p className="text-[11px] text-slate-400 mt-0.5">
            Last from {alert.vendor}{alert.last_price > 0 ? ` at ${fmtPrice(alert.last_price)}` : ''}
          </p>
        )}
      </div>
    </div>
  );
}

// ======================== ITEM SEARCH ========================
function ItemSearch({ api }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef(null);

  const search = useCallback(async (q) => {
    if (!q || q.trim().length < 2) { setResults(null); return; }
    setSearching(true);
    try {
      const res = await api.get('/dashboard/item-search', { params: { q: q.trim() } });
      setResults(res.data.results);
    } catch {
      toast.error('Search failed');
    } finally {
      setSearching(false);
    }
  }, [api]);

  const handleChange = useCallback((e) => {
    const val = e.target.value;
    setQuery(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(val), 350);
  }, [search]);

  const clear = useCallback(() => {
    setQuery('');
    setResults(null);
    if (debounceRef.current) clearTimeout(debounceRef.current);
  }, []);

  return (
    <Card className="border border-slate-100 shadow-sm" data-testid="item-search-card">
      <CardHeader className="pb-2 pt-5 px-6">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-teal-600 flex items-center justify-center">
            <Search className="w-4 h-4 text-white" />
          </div>
          <div>
            <CardTitle className="font-heading text-sm font-bold text-navy-900">Where Should I Buy?</CardTitle>
            <p className="text-[10px] text-slate-400">Search any item to compare vendors and prices</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-6 pb-5">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            value={query}
            onChange={handleChange}
            placeholder="Search item... e.g. Salmon, Olive Oil, Tomatoes"
            className="pl-9 pr-9 h-10 text-sm border-slate-200 focus:border-teal-500 focus:ring-teal-500/20"
            data-testid="item-search-input"
          />
          {query && (
            <button onClick={clear} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600" data-testid="item-search-clear">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {searching && (
          <div className="flex items-center justify-center py-8" data-testid="item-search-loading">
            <Loader2 className="w-5 h-5 animate-spin text-teal-600" />
          </div>
        )}

        {!searching && results !== null && results.length === 0 && query.length >= 2 && (
          <div className="text-center py-8" data-testid="item-search-empty">
            <Package className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <p className="text-sm text-slate-400">No items found for "{query}"</p>
          </div>
        )}

        {!searching && results && results.length > 0 && (
          <div className="mt-4 space-y-4" data-testid="item-search-results">
            {results.map((item, idx) => (
              <div key={idx} className="border border-slate-100 rounded-lg overflow-hidden" data-testid={`search-result-${idx}`}>
                <div className="flex items-center justify-between px-4 py-3 bg-slate-50/60">
                  <div className="flex items-center gap-2">
                    <Tag className="w-3.5 h-3.5 text-teal-600" />
                    <span className="text-sm font-bold text-navy-900">{item.item_name}</span>
                  </div>
                  <span className="text-[10px] text-slate-400 font-semibold">{item.vendor_count} vendor{item.vendor_count !== 1 ? 's' : ''}</span>
                </div>
                <div className="divide-y divide-slate-100">
                  {item.vendors.map((v, vi) => {
                    const isCheapest = v.vendor === item.cheapest_vendor;
                    return (
                      <div key={vi} className={`flex items-center justify-between px-4 py-2.5 ${isCheapest ? 'bg-teal-50/40' : ''}`} data-testid={`vendor-row-${idx}-${vi}`}>
                        <div className="flex items-center gap-2 min-w-0">
                          <Store className={`w-3.5 h-3.5 flex-shrink-0 ${isCheapest ? 'text-teal-600' : 'text-slate-400'}`} />
                          <span className={`text-xs truncate ${isCheapest ? 'font-bold text-teal-700' : 'text-slate-600'}`}>{v.vendor}</span>
                          {isCheapest && <Badge className="bg-teal-600 text-white text-[8px] h-4 px-1.5 font-bold">BEST</Badge>}
                        </div>
                        <div className="flex items-center gap-3 flex-shrink-0">
                          <div className="text-right">
                            <span className={`text-xs font-bold tabular-nums ${isCheapest ? 'text-teal-700' : 'text-navy-900'}`}>{fmtPrice(v.latest_price)}</span>
                            {v.unit && <span className="text-[10px] text-slate-400">/{v.unit}</span>}
                          </div>
                          <span className="text-[10px] text-slate-400 tabular-nums w-8 text-right">{v.purchase_count}x</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ======================== HELPERS ========================
function LoadingSkeleton() {
  return (
    <div className="space-y-6" data-testid="dashboard-loading">
      <div><Skeleton className="h-8 w-48 mb-2" /><Skeleton className="h-4 w-72" /></div>
      <Skeleton className="h-64 rounded-xl" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6"><Skeleton className="h-48 rounded-xl" /><Skeleton className="h-48 rounded-xl" /></div>
    </div>
  );
}

function EmptyDashboard({ onSeed, seeding }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center" data-testid="empty-dashboard">
      <div className="w-20 h-20 rounded-2xl bg-slate-100 flex items-center justify-center mb-6"><BarChart3 className="w-10 h-10 text-slate-300" /></div>
      <h2 className="font-heading text-xl font-bold text-navy-900 mb-2">No financial data yet</h2>
      <p className="text-sm text-slate-500 max-w-sm mb-8">Upload your first invoice or load demo data to see your dashboard come to life.</p>
      <Button onClick={onSeed} disabled={seeding} className="bg-teal-600 hover:bg-teal-700 text-white h-11 px-6 text-sm font-semibold" data-testid="seed-data-btn">
        {seeding ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null} Load Demo Data
      </Button>
    </div>
  );
}

// ======================== MAIN PAGE ========================
const EMPTY_ALERTS = [];

export default function DashboardPage() {
  const { api } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);

  const load = useCallback(async () => {
    try { const res = await api.get('/dashboard/summary'); setData(res.data); }
    catch { toast.error('Failed to load dashboard'); }
    finally { setLoading(false); }
  }, [api]);

  const seedData = useCallback(async () => {
    setSeeding(true);
    try { await api.post('/seed'); toast.success('Demo data loaded!'); await load(); }
    catch { toast.error('Failed to seed data'); }
    finally { setSeeding(false); }
  }, [api, load]);

  useEffect(() => { load(); }, [load]);
  const smartAlerts = useMemo(() => data?.smart_alerts || EMPTY_ALERTS, [data]);

  if (loading) return <LoadingSkeleton />;

  const isEmpty = !data || (
    (data.month_raw_materials || 0) === 0 &&
    (data.month_salaries || 0) === 0 &&
    (data.month_other_expenses || 0) === 0
  );
  if (isEmpty) return <EmptyDashboard onSeed={seedData} seeding={seeding} />;

  return (
    <div className="space-y-6 max-w-[1100px]" data-testid="dashboard-page">
      <div>
        <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-navy-900 tracking-tight">Dashboard</h1>
        <p className="text-sm text-slate-400 mt-1">Where am I spending? Where should I buy?</p>
      </div>

      {/* Item Search */}
      <ItemSearch api={api} />

      {/* Donut + Insights side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6" data-testid="dashboard-main-row">
        <DonutChart
          raw={data.month_raw_materials || 0}
          salaries={data.month_salaries || 0}
          other={data.month_other_expenses || 0}
          prevRaw={data.prev_month_raw_materials || 0}
          prevSalaries={data.prev_month_salaries || 0}
          prevOther={data.prev_month_other_expenses || 0}
        />
        <MarketInsights alerts={smartAlerts} />
      </div>
    </div>
  );
}
