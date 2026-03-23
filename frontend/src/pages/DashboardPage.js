import { useState, useEffect, useCallback, useMemo, memo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import {
  TrendingUp, TrendingDown, DollarSign, ShoppingCart,
  ArrowUpRight, ArrowDownRight, Loader2, BarChart3,
  Wallet, AlertTriangle, Clock, ArrowRightLeft, ChevronRight,
  PieChart as PieChartIcon
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts';

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

const DONUT_COLORS = ['#0d9488', '#6366f1', '#f59e0b', '#64748b'];
const DONUT_BG = ['bg-teal-500', 'bg-indigo-500', 'bg-amber-500', 'bg-slate-500'];
const EMPTY_ARRAY = [];
const EMPTY_TRENDS = [];

// ======================== KPI CARD ========================
function KPI({ label, value, prev, accent, icon: Icon, testId }) {
  const pct = pctChange(value, prev);
  const isUp = pct > 0;
  return (
    <div className="flex flex-col justify-between h-full" data-testid={testId}>
      <div className="flex items-center justify-between mb-4">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${accent ? 'bg-teal-600' : 'bg-navy-900'}`}>
          <Icon className="w-[18px] h-[18px] text-white" strokeWidth={2} />
        </div>
        {pct !== null && (
          <span className={`inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full ${isUp ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
            {isUp ? <ArrowUpRight className="w-3 h-3 mr-0.5" /> : <ArrowDownRight className="w-3 h-3 mr-0.5" />}
            {Math.abs(pct)}%
          </span>
        )}
      </div>
      <p className="font-heading text-3xl font-extrabold tracking-tight text-navy-900">{fmt(value)}</p>
      <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-[0.15em] mt-1">{label}</p>
    </div>
  );
}

// ======================== DONUT CHART ========================
const DonutChart = memo(function DonutChart({ raw, salaries, utilities, other, prevRaw, prevSalaries, prevUtilities, prevOther }) {
  const total = raw + salaries + utilities + other;
  const prevTotal = prevRaw + prevSalaries + prevUtilities + prevOther;

  const segments = useMemo(() => [
    { name: 'Raw Materials', value: raw, prev: prevRaw, color: DONUT_COLORS[0] },
    { name: 'Salaries', value: salaries, prev: prevSalaries, color: DONUT_COLORS[1] },
    { name: 'Utilities', value: utilities, prev: prevUtilities, color: DONUT_COLORS[2] },
    { name: 'Other', value: other, prev: prevOther, color: DONUT_COLORS[3] },
  ].filter(s => s.value > 0), [raw, salaries, utilities, other, prevRaw, prevSalaries, prevUtilities, prevOther]);

  const pctTotal = pctChange(total, prevTotal);

  const insights = useMemo(() => {
    const result = [];
    [{ name: 'Raw Materials', cur: raw, prev: prevRaw },
     { name: 'Salaries', cur: salaries, prev: prevSalaries },
     { name: 'Utilities', cur: utilities, prev: prevUtilities },
     { name: 'Other', cur: other, prev: prevOther }]
      .forEach(cat => {
        const pct = pctChange(cat.cur, cat.prev);
        if (pct !== null && Math.abs(pct) > 3) {
          result.push({ name: cat.name, pct: parseFloat(pct), up: pct > 0 });
        }
      });
    return result;
  }, [raw, salaries, utilities, other, prevRaw, prevSalaries, prevUtilities, prevOther]);

  const noDataSegments = useMemo(() => [{ name: 'No data', value: 1 }], []);
  const donutTooltip = useMemo(() => <DonutTooltip total={total} />, [total]);

  return (
    <Card className="border border-slate-100 shadow-sm" data-testid="donut-chart-card">
      <CardHeader className="pb-2 pt-5 px-6">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-navy-900 flex items-center justify-center">
            <PieChartIcon className="w-4 h-4 text-white" />
          </div>
          <div>
            <CardTitle className="font-heading text-sm font-bold text-navy-900">Monthly Spending</CardTitle>
            <p className="text-[10px] text-slate-400">Expense breakdown by category</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-6 pb-5">
        <div className="flex flex-col sm:flex-row items-center gap-6">
          {/* Donut */}
          <div className="relative w-44 h-44 flex-shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={segments.length > 0 ? segments : noDataSegments}
                  cx="50%"
                  cy="50%"
                  innerRadius={52}
                  outerRadius={72}
                  paddingAngle={segments.length > 1 ? 3 : 0}
                  dataKey="value"
                  stroke="none"
                >
                  {segments.length > 0
                    ? segments.map((s, i) => <Cell key={i} fill={s.color} />)
                    : <Cell fill="#e2e8f0" />
                  }
                </Pie>
                <Tooltip content={donutTooltip} />
              </PieChart>
            </ResponsiveContainer>
            {/* Center label */}
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

          {/* Legend + insights */}
          <div className="flex-1 space-y-3 w-full">
            {/* Legend */}
            <div className="space-y-2">
              {[
                { label: 'Raw Materials', value: raw, bg: DONUT_BG[0] },
                { label: 'Salaries', value: salaries, bg: DONUT_BG[1] },
                { label: 'Utilities', value: utilities, bg: DONUT_BG[2] },
                { label: 'Other', value: other, bg: DONUT_BG[3] },
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

            {/* Category insights */}
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

// ======================== EXPENSE TREND CHART ========================
const ExpenseTrendChart = memo(function ExpenseTrendChart({ trends }) {
  const [mode, setMode] = useState('weekly');

  const chartData = useMemo(() => {
    if (mode === 'weekly') return trends;
    const months = [];
    for (let i = 0; i < trends.length; i += 4) {
      const slice = trends.slice(i, i + 4);
      months.push({
        week: `M${Math.floor(i / 4) + 1}`,
        purchases: slice.reduce((s, w) => s + (w.purchases || 0), 0),
        salaries: slice.reduce((s, w) => s + (w.salaries || 0), 0),
        utilities: slice.reduce((s, w) => s + (w.utilities || 0), 0),
        other_expenses: slice.reduce((s, w) => s + (w.other_expenses || 0), 0),
      });
    }
    return months;
  }, [trends, mode]);

  const trendTooltip = useMemo(() => <TrendTooltip />, []);

  return (
    <Card className="border border-slate-100 shadow-sm" data-testid="expense-trend-card">
      <CardHeader className="pb-2 pt-5 px-6">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center">
              <TrendingUp className="w-4 h-4 text-white" />
            </div>
            <div>
              <CardTitle className="font-heading text-sm font-bold text-navy-900">Expense Trends</CardTitle>
              <p className="text-[10px] text-slate-400">All expense categories over time</p>
            </div>
          </div>
          <Tabs value={mode} onValueChange={setMode}>
            <TabsList className="h-7 bg-slate-100">
              <TabsTrigger value="weekly" className="text-[10px] font-semibold h-6 px-3" data-testid="trend-tab-weekly">Weekly</TabsTrigger>
              <TabsTrigger value="monthly" className="text-[10px] font-semibold h-6 px-3" data-testid="trend-tab-monthly">Monthly</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </CardHeader>
      <CardContent className="px-2 pb-4 pt-2">
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <XAxis dataKey="week" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: '#94a3b8' }} dy={8} />
              <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={v => fmt(v)} width={55} />
              <Tooltip content={trendTooltip} />
              <Line type="monotone" dataKey="purchases" stroke="#0d9488" strokeWidth={2.5} dot={{ r: 3, fill: '#0d9488', stroke: '#fff', strokeWidth: 2 }} name="Raw Materials" />
              <Line type="monotone" dataKey="salaries" stroke="#6366f1" strokeWidth={2} dot={{ r: 3, fill: '#6366f1', stroke: '#fff', strokeWidth: 2 }} name="Salaries" />
              <Line type="monotone" dataKey="utilities" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3, fill: '#f59e0b', stroke: '#fff', strokeWidth: 2 }} name="Utilities" />
              <Line type="monotone" dataKey="other_expenses" stroke="#64748b" strokeWidth={2} dot={{ r: 3, fill: '#64748b', stroke: '#fff', strokeWidth: 2 }} name="Other" />
            </LineChart>
          </ResponsiveContainer>
        </div>
        {/* Legend */}
        <div className="flex items-center justify-center gap-5 mt-2">
          {[{ label: 'Raw Materials', color: '#0d9488' }, { label: 'Salaries', color: '#6366f1' }, { label: 'Utilities', color: '#f59e0b' }, { label: 'Other', color: '#64748b' }].map(l => (
            <div key={l.label} className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: l.color }} />
              <span className="text-[10px] font-semibold text-slate-500">{l.label}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
});

function TrendTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg px-3 py-2 shadow-lg">
      <p className="text-[11px] font-semibold text-slate-500 mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} className="text-xs"><span className="font-semibold" style={{ color: p.color }}>{p.name}:</span> {fmtFull(p.value)}</p>
      ))}
    </div>
  );
}

// ======================== SEVERITY / ALERTS ========================
function SeverityBadge({ severity }) {
  const config = { high: 'bg-red-600 text-white', medium: 'bg-amber-500 text-white', low: 'bg-slate-400 text-white' };
  return <Badge className={`text-[9px] px-1.5 py-0 h-[18px] font-bold uppercase tracking-wider ${config[severity] || config.low}`} data-testid={`severity-${severity}`}>{severity}</Badge>;
}

function NotOrderedAlert({ alert, index }) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg border border-amber-200/80 bg-amber-50/40 hover:bg-amber-50/70 transition-colors" data-testid={`alert-not-ordered-${index}`}>
      <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0"><Clock className="w-4 h-4 text-amber-600" /></div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2"><span className="text-xs font-bold text-navy-900">{alert.item_name}</span><SeverityBadge severity={alert.severity} /></div>
        <p className="text-[11px] text-slate-500 mt-0.5"><span className="font-semibold text-amber-700">{alert.days_since} days</span> since last order{alert.vendor && <span> &middot; Last from <span className="font-medium text-navy-900">{alert.vendor}</span></span>}{alert.last_price > 0 && <span> at {fmtPrice(alert.last_price)}</span>}</p>
      </div>
      <ChevronRight className="w-4 h-4 text-slate-300 flex-shrink-0" />
    </div>
  );
}

function PriceIncreaseAlert({ alert, index }) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg border border-red-200/80 bg-red-50/40 hover:bg-red-50/70 transition-colors" data-testid={`alert-price-increase-${index}`}>
      <div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center flex-shrink-0"><TrendingUp className="w-4 h-4 text-red-600" /></div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2"><span className="text-xs font-bold text-navy-900">{alert.item_name}</span><SeverityBadge severity={alert.severity} /><span className="text-[10px] font-bold text-red-600">+{alert.change_pct}%</span></div>
        <p className="text-[11px] text-slate-500 mt-0.5"><span className="text-slate-600">{fmtPrice(alert.old_price)}</span><span className="mx-1 text-red-400">&rarr;</span><span className="font-semibold text-red-600">{fmtPrice(alert.new_price)}</span>{alert.vendor && <span> &middot; <span className="font-medium text-navy-900">{alert.vendor}</span></span>}</p>
      </div>
      <ChevronRight className="w-4 h-4 text-slate-300 flex-shrink-0" />
    </div>
  );
}

function CheaperVendorAlert({ alert, index }) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg border border-teal-200/80 bg-teal-50/40 hover:bg-teal-50/70 transition-colors" data-testid={`alert-cheaper-vendor-${index}`}>
      <div className="w-8 h-8 rounded-lg bg-teal-100 flex items-center justify-center flex-shrink-0"><ArrowRightLeft className="w-4 h-4 text-teal-600" /></div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2"><span className="text-xs font-bold text-navy-900">{alert.item_name}</span><SeverityBadge severity={alert.severity} /><span className="text-[10px] font-bold text-teal-600">Save {alert.savings_pct}%</span></div>
        <p className="text-[11px] text-slate-500 mt-0.5">{fmtPrice(alert.current_price)} at <span className="font-medium text-navy-900">{alert.vendor}</span><span className="mx-1 text-teal-500">&rarr;</span><span className="font-semibold text-teal-600">{fmtPrice(alert.cheaper_price)}</span> at <span className="font-medium text-teal-700">{alert.cheaper_vendor}</span></p>
      </div>
      <ChevronRight className="w-4 h-4 text-slate-300 flex-shrink-0" />
    </div>
  );
}

// ======================== SMART ALERTS ========================
const SmartAlertsSection = memo(function SmartAlertsSection({ alerts }) {
  const [tab, setTab] = useState('all');
  const { notOrdered, priceUp, cheaper, highCount } = useMemo(() => ({
    notOrdered: alerts.filter(a => a.type === 'not_ordered'),
    priceUp: alerts.filter(a => a.type === 'price_increase'),
    cheaper: alerts.filter(a => a.type === 'cheaper_vendor'),
    highCount: alerts.filter(a => a.severity === 'high').length,
  }), [alerts]);
  const filtered = useMemo(() => {
    if (tab === 'all') return alerts;
    if (tab === 'not_ordered') return notOrdered;
    if (tab === 'price_increase') return priceUp;
    return cheaper;
  }, [tab, alerts, notOrdered, priceUp, cheaper]);

  if (!alerts.length) return null;

  return (
    <Card className="border border-slate-200/80 shadow-sm" data-testid="smart-alerts-section">
      <CardHeader className="pb-3 pt-5 px-6">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-navy-900 flex items-center justify-center"><AlertTriangle className="w-4 h-4 text-white" /></div>
          <div>
            <CardTitle className="font-heading text-sm font-bold text-navy-900">Smart Alerts</CardTitle>
            <p className="text-[10px] text-slate-400 mt-0.5">{alerts.length} alert{alerts.length !== 1 ? 's' : ''} from real purchase data{highCount > 0 && <span> &middot; <span className="text-red-500 font-semibold">{highCount} high priority</span></span>}</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-6 pb-5">
        <Tabs value={tab} onValueChange={setTab} className="mb-4">
          <TabsList className="bg-slate-100/80 h-8" data-testid="alert-filter-tabs">
            <TabsTrigger value="all" className="text-[11px] font-semibold px-3 h-7" data-testid="alert-tab-all">All ({alerts.length})</TabsTrigger>
            {priceUp.length > 0 && <TabsTrigger value="price_increase" className="text-[11px] font-semibold px-3 h-7 gap-1" data-testid="alert-tab-price">Price ({priceUp.length})</TabsTrigger>}
            {cheaper.length > 0 && <TabsTrigger value="cheaper_vendor" className="text-[11px] font-semibold px-3 h-7 gap-1" data-testid="alert-tab-cheaper">Cheaper ({cheaper.length})</TabsTrigger>}
            {notOrdered.length > 0 && <TabsTrigger value="not_ordered" className="text-[11px] font-semibold px-3 h-7 gap-1" data-testid="alert-tab-not-ordered">Not Ordered ({notOrdered.length})</TabsTrigger>}
          </TabsList>
        </Tabs>
        <div className="space-y-2 max-h-[400px] overflow-y-auto" data-testid="alerts-list">
          {filtered.map((alert, i) => {
            if (alert.type === 'not_ordered') return <NotOrderedAlert key={`no-${i}`} alert={alert} index={i} />;
            if (alert.type === 'price_increase') return <PriceIncreaseAlert key={`pi-${i}`} alert={alert} index={i} />;
            if (alert.type === 'cheaper_vendor') return <CheaperVendorAlert key={`cv-${i}`} alert={alert} index={i} />;
            return null;
          })}
          {filtered.length === 0 && <div className="text-center py-6 text-xs text-slate-400">No alerts in this category</div>}
        </div>
      </CardContent>
    </Card>
  );
});

// ======================== HELPERS ========================
function LoadingSkeleton() {
  return (
    <div className="space-y-8" data-testid="dashboard-loading">
      <Skeleton className="h-48 rounded-xl" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">{[1,2,3,4,5,6].map(i => <Card key={i} className="border border-slate-100"><CardContent className="p-6"><Skeleton className="h-10 w-10 rounded-xl mb-4" /><Skeleton className="h-8 w-32 mb-2" /><Skeleton className="h-3 w-20" /></CardContent></Card>)}</div>
    </div>
  );
}

function EmptyDashboard({ onSeed, seeding }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center" data-testid="empty-dashboard">
      <div className="w-20 h-20 rounded-2xl bg-slate-100 flex items-center justify-center mb-6"><BarChart3 className="w-10 h-10 text-slate-300" /></div>
      <h2 className="font-heading text-xl font-bold text-navy-900 mb-2">No financial data yet</h2>
      <p className="text-sm text-slate-500 max-w-sm mb-8">Upload your first invoice or load demo data to see your dashboard come to life.</p>
      <Button onClick={onSeed} disabled={seeding} className="bg-teal-600 hover:bg-teal-700 text-white h-11 px-6 text-sm font-semibold" data-testid="seed-data-btn">{seeding ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null} Load Demo Data</Button>
    </div>
  );
}

const CustomTooltip = memo(function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg px-3 py-2 shadow-lg">
      <p className="text-[11px] font-semibold text-slate-500 mb-1">{label}</p>
      {payload.map((p, i) => <p key={i} className="text-xs"><span className="font-semibold" style={{ color: p.color }}>{p.name}:</span> {fmt(p.value)}</p>)}
    </div>
  );
});

// ======================== MAIN PAGE ========================
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
  const smartAlerts = useMemo(() => data?.smart_alerts || EMPTY_ARRAY, [data]);
  const weeklyTrends = useMemo(() => data?.weekly_trends || EMPTY_TRENDS, [data]);
  const topItems = useMemo(() => data?.top_items || EMPTY_ARRAY, [data]);
  const topSuppliers = useMemo(() => data?.top_suppliers || EMPTY_ARRAY, [data]);
  const recentAlerts = useMemo(() => data?.alerts || EMPTY_ARRAY, [data]);

  if (loading) return <LoadingSkeleton />;
  const isEmpty = !data || (data.month_sales === 0 && data.month_purchases === 0);
  if (isEmpty) return <EmptyDashboard onSeed={seedData} seeding={seeding} />;

  return (
    <div className="space-y-8 max-w-[1400px]" data-testid="dashboard-page">
      <div>
        <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-navy-900 tracking-tight">Dashboard</h1>
        <p className="text-sm text-slate-400 mt-1">Your restaurant's financial pulse</p>
      </div>

      {/* SMART ALERTS */}
      <SmartAlertsSection alerts={smartAlerts} />

      {/* ===== NEW: EXPENSE VISUALIZATION ROW ===== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6" data-testid="expense-charts-row">
        <DonutChart
          raw={data.month_raw_materials || 0}
          salaries={data.month_salaries || 0}
          utilities={data.month_utilities || 0}
          other={data.month_other_expenses || 0}
          prevRaw={data.prev_month_raw_materials || 0}
          prevSalaries={data.prev_month_salaries || 0}
          prevUtilities={data.prev_month_utilities || 0}
          prevOther={data.prev_month_other_expenses || 0}
        />
        <ExpenseTrendChart trends={weeklyTrends} />
      </div>

      {/* Primary KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        <Card className="border border-slate-100 shadow-sm"><CardContent className="p-6"><KPI label="Today Sales" value={data.today_sales} prev={null} accent icon={DollarSign} testId="stat-today-sales" /></CardContent></Card>
        <Card className="border border-slate-100 shadow-sm"><CardContent className="p-6"><KPI label="Today Purchases" value={data.today_purchases} prev={null} icon={ShoppingCart} testId="stat-today-purchases" /></CardContent></Card>
        <Card className="border border-slate-100 shadow-sm"><CardContent className="p-6"><KPI label="This Week Sales" value={data.week_sales} prev={data.prev_week_sales} accent icon={TrendingUp} testId="stat-week-sales" /></CardContent></Card>
        <Card className="border border-slate-100 shadow-sm"><CardContent className="p-6"><KPI label="This Week Purchases" value={data.week_purchases} prev={data.prev_week_purchases} icon={ShoppingCart} testId="stat-week-purchases" /></CardContent></Card>
        <Card className="border border-slate-100 shadow-sm"><CardContent className="p-6"><KPI label="This Month Sales" value={data.month_sales} prev={data.prev_month_sales} accent icon={TrendingUp} testId="stat-month-sales" /></CardContent></Card>
        <Card className="border border-slate-100 shadow-sm"><CardContent className="p-6"><KPI label="This Month Purchases" value={data.month_purchases} prev={data.prev_month_purchases} icon={ShoppingCart} testId="stat-month-purchases" /></CardContent></Card>
      </div>

      {/* Profit Overview */}
      <div data-testid="profit-overview-section">
        <div className="flex items-center gap-2.5 mb-4">
          <div className="w-8 h-8 rounded-lg bg-teal-600 flex items-center justify-center"><Wallet className="w-4 h-4 text-white" /></div>
          <div><h2 className="font-heading text-sm font-bold text-navy-900">Net Profit</h2><p className="text-[10px] text-slate-400">Total Sales minus all Expenses</p></div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'Daily Profit', value: data.daily_profit, prev: null, testId: 'profit-daily' },
            { label: 'Weekly Profit', value: data.weekly_profit, prev: data.prev_weekly_profit, testId: 'profit-weekly' },
            { label: 'Monthly Profit', value: data.monthly_profit, prev: data.prev_monthly_profit, testId: 'profit-monthly' },
            { label: 'Yearly Profit', value: data.yearly_profit, prev: data.prev_yearly_profit, testId: 'profit-yearly' },
          ].map((p) => {
            const val = p.value || 0;
            const isPositive = val >= 0;
            const pct = pctChange(Math.abs(p.value), Math.abs(p.prev));
            const pctUp = pct > 0;
            return (
              <Card key={p.testId} className={`border shadow-sm overflow-hidden ${isPositive ? 'border-emerald-200/80' : 'border-red-200/80'}`} data-testid={p.testId}>
                <CardContent className="p-5">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">{p.label}</span>
                    {pct !== null && <span className={`inline-flex items-center text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${pctUp ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>{pctUp ? <ArrowUpRight className="w-2.5 h-2.5 mr-0.5" /> : <ArrowDownRight className="w-2.5 h-2.5 mr-0.5" />}{Math.abs(pct)}%</span>}
                  </div>
                  <div className="flex items-baseline gap-1">
                    {!isPositive && <span className="text-lg font-bold text-red-500">-</span>}
                    <span className={`text-2xl font-extrabold tabular-nums tracking-tight ${isPositive ? 'text-emerald-600' : 'text-red-500'}`}>{fmt(Math.abs(val))}</span>
                  </div>
                  <div className={`h-1 rounded-full mt-3 ${isPositive ? 'bg-emerald-100' : 'bg-red-100'}`}>
                    <div className={`h-full rounded-full transition-all ${isPositive ? 'bg-emerald-500' : 'bg-red-500'}`} style={{ width: `${Math.min(100, Math.abs(val) / Math.max(1, (data.yearly_sales || 1)) * 100 * 4)}%` }} />
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 border border-slate-100 shadow-sm" data-testid="weekly-trends-chart">
          <CardHeader className="pb-0 pt-5 px-6"><CardTitle className="font-heading text-sm font-bold text-navy-900 uppercase tracking-wide">Weekly Sales vs Purchases</CardTitle></CardHeader>
          <CardContent className="px-2 pb-4 pt-2">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={weeklyTrends} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="gSales" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#0d9488" stopOpacity={0.18} /><stop offset="100%" stopColor="#0d9488" stopOpacity={0} /></linearGradient>
                    <linearGradient id="gPurch" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#0f172a" stopOpacity={0.1} /><stop offset="100%" stopColor="#0f172a" stopOpacity={0} /></linearGradient>
                  </defs>
                  <XAxis dataKey="week" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: '#94a3b8' }} dy={8} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} width={50} />
                  <Tooltip content={<CustomTooltip />} />
                  <Area type="monotone" dataKey="sales" stroke="#0d9488" fill="url(#gSales)" strokeWidth={2.5} name="Sales" dot={false} />
                  <Area type="monotone" dataKey="purchases" stroke="#0f172a" fill="url(#gPurch)" strokeWidth={1.5} name="Purchases" dot={false} strokeDasharray="4 4" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="border border-slate-100 shadow-sm" data-testid="top-items-chart">
          <CardHeader className="pb-0 pt-5 px-6"><CardTitle className="font-heading text-sm font-bold text-navy-900 uppercase tracking-wide">Top Items</CardTitle></CardHeader>
          <CardContent className="px-2 pb-4 pt-2">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={topItems} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
                  <XAxis type="number" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} />
                  <YAxis dataKey="name" type="category" width={100} axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: '#475569' }} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="total" fill="#0d9488" radius={[0, 6, 6, 0]} barSize={14} name="Spending" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="border border-slate-100 shadow-sm" data-testid="top-vendors">
          <CardHeader className="pb-3 pt-5 px-6"><CardTitle className="font-heading text-sm font-bold text-navy-900 uppercase tracking-wide">Top Vendors</CardTitle></CardHeader>
          <CardContent className="px-6 pb-5">
            <div className="space-y-2.5">
              {topSuppliers.map((s, i) => {
                const maxVal = topSuppliers[0]?.total || 1;
                return (
                  <div key={i} className="group">
                    <div className="flex items-center justify-between mb-1"><span className="text-sm font-medium text-navy-900">{s.name}</span><span className="text-sm font-bold text-navy-900 tabular-nums">{fmt(s.total)}</span></div>
                    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden"><div className="h-full bg-teal-500 rounded-full transition-all duration-500" style={{ width: `${(s.total / maxVal * 100)}%` }} /></div>
                  </div>
                );
              })}
              {!topSuppliers.length && <p className="text-sm text-slate-400 py-6 text-center">No vendor data yet</p>}
            </div>
          </CardContent>
        </Card>

        <Card className="border border-slate-100 shadow-sm" data-testid="recent-alerts">
          <CardHeader className="pb-3 pt-5 px-6"><CardTitle className="font-heading text-sm font-bold text-navy-900 uppercase tracking-wide">Recent Activity</CardTitle></CardHeader>
          <CardContent className="px-6 pb-5">
            <div className="space-y-2">
              {recentAlerts.slice(0, 5).map((a, i) => (
                <div key={i} className={`flex items-start gap-3 p-3 rounded-lg ${a.severity === 'high' ? 'bg-red-50/60' : a.severity === 'medium' ? 'bg-amber-50/60' : 'bg-slate-50'}`}>
                  <div className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${a.severity === 'high' ? 'bg-red-500' : a.severity === 'medium' ? 'bg-amber-500' : 'bg-slate-400'}`} />
                  <p className="text-xs text-slate-600 leading-relaxed">{a.message}</p>
                </div>
              ))}
              {!recentAlerts.length && <p className="text-sm text-slate-400 py-6 text-center">No recent activity</p>}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
