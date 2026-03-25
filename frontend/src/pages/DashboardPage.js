import { useState, useEffect, useCallback, useMemo, memo, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { dataEvents } from '@/lib/dataEvents';
import {
  TrendingUp, TrendingDown, ArrowRightLeft,
  Loader2, BarChart3, Search, Package, Store, Tag,
  PieChart as PieChartIcon, Lightbulb, X,
  ChevronRight, Users, Receipt, ExternalLink,
  Plus, DollarSign, GitCompare, FileBarChart, Clock, Zap, ArrowRight, ShieldAlert, Calendar
} from 'lucide-react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';

/* ─── helpers ─── */
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
const CAT_KEYS = ['raw_materials', 'salaries', 'other'];
const CAT_LABELS = ['Raw Materials', 'Salaries', 'Other'];

/* ═══════════════════ DONUT CHART ═══════════════════ */
const DonutChart = memo(function DonutChart({ raw, salaries, other, prevRaw, prevSalaries, prevOther, onCategoryClick }) {
  const total = raw + salaries + other;
  const prevTotal = prevRaw + prevSalaries + prevOther;

  const segments = useMemo(() => [
    { name: 'Raw Materials', key: 'raw_materials', value: raw, color: DONUT_COLORS[0] },
    { name: 'Salaries', key: 'salaries', value: salaries, color: DONUT_COLORS[1] },
    { name: 'Other', key: 'other', value: other, color: DONUT_COLORS[2] },
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

  const handlePieClick = useCallback((_, idx) => {
    if (segments[idx]) onCategoryClick?.(segments[idx].key);
  }, [segments, onCategoryClick]);

  return (
    <Card className="border border-slate-100 shadow-sm" data-testid="donut-chart-card">
      <CardHeader className="pb-2 pt-5 px-6">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-navy-900 flex items-center justify-center">
            <PieChartIcon className="w-4 h-4 text-white" />
          </div>
          <div>
            <CardTitle className="font-heading text-sm font-bold text-navy-900">Monthly Spending</CardTitle>
            <p className="text-[10px] text-slate-400">Click a category to see details</p>
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
                  onClick={handlePieClick}
                  className="cursor-pointer"
                >
                  {segments.length > 0
                    ? segments.map((s, i) => <Cell key={i} fill={s.color} className="cursor-pointer hover:opacity-80 transition-opacity" />)
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
            <div className="space-y-1">
              {[
                { label: 'Raw Materials', key: 'raw_materials', value: raw, bg: DONUT_BG[0], color: DONUT_COLORS[0] },
                { label: 'Salaries', key: 'salaries', value: salaries, bg: DONUT_BG[1], color: DONUT_COLORS[1] },
                { label: 'Other', key: 'other', value: other, bg: DONUT_BG[2], color: DONUT_COLORS[2] },
              ].map(cat => {
                const pctVal = total > 0 ? ((cat.value / total) * 100).toFixed(1) : 0;
                return (
                  <button
                    key={cat.label}
                    onClick={() => onCategoryClick?.(cat.key)}
                    className="w-full flex items-center justify-between p-2 rounded-lg hover:bg-slate-50 transition-colors group"
                    data-testid={`donut-legend-${cat.key}`}
                  >
                    <div className="flex items-center gap-2">
                      <div className={`w-2.5 h-2.5 rounded-sm ${cat.bg}`} />
                      <span className="text-xs text-slate-600 group-hover:text-navy-900 transition-colors">{cat.label}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-navy-900 tabular-nums">{fmtFull(cat.value)}</span>
                      <Badge variant="secondary" className="text-[9px] h-4 px-1.5 tabular-nums">{pctVal}%</Badge>
                      <ChevronRight className="w-3 h-3 text-slate-300 group-hover:text-teal-600 transition-colors" />
                    </div>
                  </button>
                );
              })}
            </div>
            {insights.length > 0 && (
              <div className="border-t border-slate-100 pt-2.5 space-y-1" data-testid="category-insights">
                {insights.map((ins, i) => (
                  <div key={i} className={`flex items-center gap-2 px-2.5 py-1.5 rounded-md text-xs ${ins.up ? 'bg-red-50/70 text-red-700' : 'bg-emerald-50/70 text-emerald-700'}`} data-testid={`category-insight-${i}`}>
                    {ins.up ? <TrendingUp className="w-3 h-3 flex-shrink-0" /> : <TrendingDown className="w-3 h-3 flex-shrink-0" />}
                    <span><span className="font-bold">{ins.name}</span> {ins.up ? 'increased' : 'decreased'} by <span className="font-bold">{Math.abs(ins.pct)}%</span> this month</span>
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

/* ═══════════════════ SALES DONUT ═══════════════════ */
const SalesDonut = memo(function SalesDonut({ sales, prevSales, onCategoryClick }) {
  const pctSales = pctChange(sales, prevSales);
  const segments = useMemo(() => sales > 0 ? [{ name: 'Sales', value: sales, color: '#0d9488' }] : [], [sales]);
  const noData = useMemo(() => [{ name: 'No data', value: 1 }], []);
  const tooltipEl = useMemo(() => <DonutTooltip total={sales} />, [sales]);

  return (
    <Card className="border border-slate-100 shadow-sm" data-testid="sales-donut-card">
      <CardHeader className="pb-2 pt-5 px-6">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-teal-600 flex items-center justify-center">
            <DollarSign className="w-4 h-4 text-white" />
          </div>
          <div>
            <CardTitle className="font-heading text-sm font-bold text-navy-900">Monthly Sales</CardTitle>
            <p className="text-[10px] text-slate-400">Click to see sales details</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-6 pb-5">
        <div className="flex items-center gap-6">
          <div className="relative w-36 h-36 flex-shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={segments.length > 0 ? segments : noData}
                  cx="50%" cy="50%"
                  innerRadius={44} outerRadius={60}
                  dataKey="value" stroke="none"
                  onClick={() => onCategoryClick?.('sales')}
                  className="cursor-pointer"
                >
                  {segments.length > 0
                    ? segments.map((s, i) => <Cell key={i} fill={s.color} className="cursor-pointer hover:opacity-80 transition-opacity" />)
                    : <Cell fill="#e2e8f0" />}
                </Pie>
                <Tooltip content={tooltipEl} />
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Revenue</span>
              <span className="text-base font-extrabold text-navy-900 tabular-nums">{fmt(sales)}</span>
              {pctSales !== null && (
                <span className={`text-[10px] font-semibold ${pctSales > 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                  {pctSales > 0 ? '+' : ''}{pctSales}%
                </span>
              )}
            </div>
          </div>
          <div className="flex-1 space-y-3">
            <button
              onClick={() => onCategoryClick?.('sales')}
              className="w-full flex items-center justify-between p-2.5 rounded-lg hover:bg-slate-50 transition-colors group"
              data-testid="sales-donut-legend"
            >
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-sm bg-teal-500" />
                <span className="text-xs text-slate-600 group-hover:text-navy-900">Total Sales</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-navy-900 tabular-nums">{fmtFull(sales)}</span>
                <ChevronRight className="w-3 h-3 text-slate-300 group-hover:text-teal-600 transition-colors" />
              </div>
            </button>
            {pctSales !== null && (
              <div className={`flex items-center gap-2 px-2.5 py-1.5 rounded-md text-xs ${parseFloat(pctSales) > 0 ? 'bg-emerald-50/70 text-emerald-700' : 'bg-red-50/70 text-red-700'}`}>
                {parseFloat(pctSales) > 0 ? <TrendingUp className="w-3 h-3 flex-shrink-0" /> : <TrendingDown className="w-3 h-3 flex-shrink-0" />}
                <span>Sales {parseFloat(pctSales) > 0 ? 'up' : 'down'} <span className="font-bold">{Math.abs(parseFloat(pctSales))}%</span> vs last month</span>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
});

/* ═══════════════════ DRILL-DOWN SHEET ═══════════════════ */
function DrillDownSheet({ open, onClose, category, api }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const catKey = useRef(null);

  const now = new Date();
  const monthStart = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
  const todayStr = now.toISOString().slice(0, 10);

  const [dateFrom, setDateFrom] = useState(monthStart);
  const [dateTo, setDateTo] = useState(todayStr);

  const fetchData = useCallback((cat, df, dt) => {
    if (!cat) return;
    setLoading(true);
    setData(null);
    const params = {};
    if (df) params.date_from = df;
    if (dt) params.date_to = dt;
    api.get(`/dashboard/drill-down/${cat}`, { params })
      .then(res => setData(res.data))
      .catch(() => toast.error('Failed to load details'))
      .finally(() => setLoading(false));
  }, [api]);

  useEffect(() => {
    if (!open || !category) return;
    if (catKey.current !== category) {
      setDateFrom(monthStart);
      setDateTo(todayStr);
    }
    catKey.current = category;
    fetchData(category, catKey.current !== category ? monthStart : dateFrom, catKey.current !== category ? todayStr : dateTo);
  }, [open, category]); // eslint-disable-line react-hooks/exhaustive-deps

  const applyDateFilter = useCallback(() => {
    fetchData(category, dateFrom, dateTo);
  }, [fetchData, category, dateFrom, dateTo]);

  const handleClose = useCallback((isOpen) => {
    if (!isOpen) {
      requestAnimationFrame(() => {
        onClose();
        catKey.current = null;
        setData(null);
      });
    }
  }, [onClose]);

  const catLabel = category === 'raw_materials' ? 'Raw Materials' : category === 'salaries' ? 'Salaries' : category === 'sales' ? 'Sales' : 'Other Expenses';
  const catColor = category === 'raw_materials' ? 'teal' : category === 'salaries' ? 'indigo' : category === 'sales' ? 'teal' : 'slate';
  const CatIcon = category === 'raw_materials' ? Package : category === 'salaries' ? Users : category === 'sales' ? DollarSign : Receipt;

  return (
    <Sheet open={open} onOpenChange={handleClose}>
      <SheetContent className="w-full sm:max-w-lg overflow-y-auto p-0" data-testid="drill-down-sheet">
        <SheetHeader className={`sticky top-0 z-10 bg-${catColor}-50 border-b border-${catColor}-100 px-6 py-5`}>
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl bg-${catColor}-600 flex items-center justify-center`}>
              <CatIcon className="w-5 h-5 text-white" />
            </div>
            <div>
              <SheetTitle className="font-heading text-lg font-bold text-navy-900" data-testid="drill-down-title">{catLabel}</SheetTitle>
              {!loading && data && (
                <p className="text-sm font-semibold text-slate-500" data-testid="drill-down-total">
                  Total: <span className={`text-${catColor}-700`}>{fmtFull(data.total)}</span>
                </p>
              )}
            </div>
          </div>
        </SheetHeader>

        <div className="px-6 py-5">
          {/* Date Filters */}
          <div className="flex items-center gap-2 mb-4 pb-4 border-b border-slate-100" data-testid="drill-down-dates">
            <Calendar className="w-4 h-4 text-slate-400 flex-shrink-0" />
            <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="h-8 text-xs flex-1" data-testid="drill-down-date-from" />
            <span className="text-xs text-slate-400">to</span>
            <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="h-8 text-xs flex-1" data-testid="drill-down-date-to" />
            <Button size="sm" onClick={applyDateFilter} className="h-8 px-3 text-xs bg-teal-600 hover:bg-teal-700 text-white" data-testid="drill-down-apply-dates">
              Apply
            </Button>
          </div>

          {loading && (
            <div className="space-y-4" data-testid="drill-down-loading">
              {[1,2,3].map(i => <Skeleton key={i} className="h-20 rounded-lg" />)}
            </div>
          )}

          {!loading && data && category === 'raw_materials' && (
            <RawMaterialsDrillDown items={data.items} navigate={navigate} />
          )}
          {!loading && data && category === 'salaries' && (
            <SalariesDrillDown employees={data.employees} total={data.total} />
          )}
          {!loading && data && category === 'other' && (
            <OtherDrillDown categories={data.categories} />
          )}
          {!loading && data && category === 'sales' && (
            <SalesDrillDown records={data.records} total={data.total} />
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

/* ─── Raw Materials Drill-Down ─── */
function RawMaterialsDrillDown({ items, navigate }) {
  const [expanded, setExpanded] = useState(null);

  if (!items.length) return (
    <div className="text-center py-10">
      <Package className="w-8 h-8 text-slate-300 mx-auto mb-2" />
      <p className="text-sm text-slate-400">No raw material purchases this month</p>
    </div>
  );

  return (
    <div className="space-y-2" data-testid="raw-materials-list">
      <p className="text-xs text-slate-400 mb-3">{items.length} items purchased this month. Tap to compare vendors.</p>
      {items.map((item, idx) => {
        const isOpen = expanded === idx;
        return (
          <div key={idx} className="border border-slate-100 rounded-lg overflow-hidden" data-testid={`raw-item-${idx}`}>
            <button
              onClick={() => setExpanded(isOpen ? null : idx)}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50/60 transition-colors"
              data-testid={`raw-item-toggle-${idx}`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <Tag className="w-3.5 h-3.5 text-teal-600 flex-shrink-0" />
                <span className="text-sm font-semibold text-navy-900 truncate">{item.item_name}</span>
                <span className="text-[10px] text-slate-400 flex-shrink-0">{item.vendor_count} vendor{item.vendor_count !== 1 ? 's' : ''}</span>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className="text-sm font-bold text-navy-900 tabular-nums">{fmtFull(item.total_spent)}</span>
                <ChevronRight className={`w-4 h-4 text-slate-300 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
              </div>
            </button>

            {isOpen && (
              <div className="border-t border-slate-100 bg-slate-50/30" data-testid={`raw-item-vendors-${idx}`}>
                {item.vendors.map((v, vi) => {
                  const isCheapest = v.vendor === item.cheapest_vendor;
                  return (
                    <div key={vi} className={`flex items-center justify-between px-4 py-2.5 border-b last:border-b-0 border-slate-100 ${isCheapest ? 'bg-teal-50/50' : ''}`} data-testid={`raw-vendor-${idx}-${vi}`}>
                      <div className="flex items-center gap-2 min-w-0">
                        <Store className={`w-3.5 h-3.5 flex-shrink-0 ${isCheapest ? 'text-teal-600' : 'text-slate-400'}`} />
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className={`text-xs truncate ${isCheapest ? 'font-bold text-teal-700' : 'text-slate-600'}`}>{v.vendor}</span>
                            {isCheapest && <Badge className="bg-teal-600 text-white text-[8px] h-4 px-1.5 font-bold">CHEAPEST</Badge>}
                          </div>
                          <span className="text-[10px] text-slate-400">
                            {v.purchase_count}x purchased · Last: {v.last_date}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 flex-shrink-0">
                        <div className="text-right">
                          <div className={`text-xs font-bold tabular-nums ${isCheapest ? 'text-teal-700' : 'text-navy-900'}`}>
                            {fmtPrice(v.latest_price)}{v.unit && <span className="text-[10px] text-slate-400 font-normal">/{v.unit}</span>}
                          </div>
                          {v.min_price !== v.max_price && (
                            <div className="text-[10px] text-slate-400 tabular-nums">
                              {fmtPrice(v.min_price)} – {fmtPrice(v.max_price)}
                            </div>
                          )}
                        </div>
                        {v.supplier_id && (
                          <button
                            onClick={() => navigate(`/vendors/${v.supplier_id}`)}
                            className="p-1 rounded hover:bg-white transition-colors"
                            title="View vendor details"
                            data-testid={`goto-vendor-${idx}-${vi}`}
                          >
                            <ExternalLink className="w-3.5 h-3.5 text-slate-400 hover:text-teal-600" />
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ─── Salaries Drill-Down ─── */
function SalariesDrillDown({ employees, total }) {
  if (!employees.length) return (
    <div className="text-center py-10">
      <Users className="w-8 h-8 text-slate-300 mx-auto mb-2" />
      <p className="text-sm text-slate-400">No salary payments this month</p>
    </div>
  );

  return (
    <div className="space-y-3" data-testid="salaries-list">
      <p className="text-xs text-slate-400 mb-3">{employees.length} employee{employees.length !== 1 ? 's' : ''} paid this month</p>
      {employees.map((emp, idx) => {
        const share = total > 0 ? ((emp.amount / total) * 100).toFixed(0) : 0;
        return (
          <div key={idx} className="flex items-center gap-4 p-3 rounded-lg border border-slate-100 hover:border-indigo-100 transition-colors" data-testid={`salary-row-${idx}`}>
            <div className="w-9 h-9 rounded-full bg-indigo-100 flex items-center justify-center flex-shrink-0">
              <span className="text-sm font-bold text-indigo-600">{emp.name.charAt(0).toUpperCase()}</span>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-navy-900 truncate">{emp.name}</span>
                <span className="text-sm font-bold text-navy-900 tabular-nums flex-shrink-0">{fmtFull(emp.amount)}</span>
              </div>
              <div className="flex items-center justify-between mt-1">
                <span className="text-[11px] text-slate-400">{emp.position || 'Staff'}</span>
                <span className="text-[10px] text-slate-400">{share}% of total</span>
              </div>
              <div className="mt-1.5 h-1 bg-slate-100 rounded-full overflow-hidden">
                <div className="h-full bg-indigo-400 rounded-full transition-all duration-500" style={{ width: `${share}%` }} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ─── Other Expenses Drill-Down ─── */
function OtherDrillDown({ categories }) {
  if (!categories.length) return (
    <div className="text-center py-10">
      <Receipt className="w-8 h-8 text-slate-300 mx-auto mb-2" />
      <p className="text-sm text-slate-400">No other expenses this month</p>
    </div>
  );

  return (
    <div className="space-y-4" data-testid="other-expenses-list">
      {categories.map((cat, ci) => (
        <div key={ci} data-testid={`other-category-${ci}`}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-navy-900 uppercase tracking-wide">{cat.category_name}</span>
            <span className="text-xs font-bold text-slate-600 tabular-nums">{fmtFull(cat.total)}</span>
          </div>
          <div className="space-y-1.5">
            {cat.items.map((item, ii) => (
              <div key={ii} className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:border-slate-200 transition-colors" data-testid={`other-item-${ci}-${ii}`}>
                <div className="min-w-0">
                  <span className="text-sm font-medium text-navy-900 truncate block">{item.title}</span>
                  <span className="text-[11px] text-slate-400">{item.expense_date}{item.vendor ? ` · ${item.vendor}` : ''}</span>
                </div>
                <span className="text-sm font-bold text-navy-900 tabular-nums flex-shrink-0 ml-3">{fmtFull(item.amount)}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─── Sales Drill-Down ─── */
function SalesDrillDown({ records, total }) {
  if (!records.length) return (
    <div className="text-center py-10">
      <DollarSign className="w-8 h-8 text-slate-300 mx-auto mb-2" />
      <p className="text-sm text-slate-400">No sales in this date range</p>
    </div>
  );

  return (
    <div className="space-y-2" data-testid="sales-drill-list">
      <p className="text-xs text-slate-400 mb-3">{records.length} sale{records.length !== 1 ? 's' : ''} in this period — Total: <span className="font-bold text-teal-700">{fmtFull(total)}</span></p>
      {records.map((rec, idx) => (
        <div key={idx} className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:border-teal-100 transition-colors" data-testid={`sale-row-${idx}`}>
          <div className="min-w-0">
            <span className="text-sm font-semibold text-navy-900">{rec.report_date}</span>
            {rec.source && <span className="text-[11px] text-slate-400 ml-2">{rec.source}</span>}
            {rec.notes && <p className="text-[11px] text-slate-400 mt-0.5 truncate">{rec.notes}</p>}
          </div>
          <div className="text-right flex-shrink-0 ml-3">
            <span className="text-sm font-bold text-teal-700 tabular-nums">{fmtFull(rec.total_sales)}</span>
            {(rec.total_tax > 0 || rec.total_tips > 0) && (
              <div className="text-[10px] text-slate-400 tabular-nums">
                {rec.total_tax > 0 && <span>Tax: {fmtPrice(rec.total_tax)}</span>}
                {rec.total_tips > 0 && <span className="ml-2">Tips: {fmtPrice(rec.total_tips)}</span>}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ═══════════════════ MARKET INSIGHTS ═══════════════════ */
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
          <p className="text-xs text-slate-700"><span className="font-bold text-navy-900">{alert.item_name}</span> price up <span className="font-bold text-red-600">+{alert.change_pct}%</span></p>
          <p className="text-[11px] text-slate-400 mt-0.5">{fmtPrice(alert.old_price)} &rarr; {fmtPrice(alert.new_price)} at {alert.vendor}</p>
        </div>
      </div>
    );
  }
  if (isCheaper) {
    return (
      <div className="flex items-start gap-3 p-3 rounded-lg border border-teal-100 bg-teal-50/40" data-testid={`insight-${index}`}>
        <ArrowRightLeft className="w-4 h-4 text-teal-600 mt-0.5 flex-shrink-0" />
        <div className="min-w-0">
          <p className="text-xs text-slate-700">Save <span className="font-bold text-teal-600">{alert.savings_pct}%</span> on <span className="font-bold text-navy-900">{alert.item_name}</span></p>
          <p className="text-[11px] text-slate-400 mt-0.5">Switch from {alert.vendor} ({fmtPrice(alert.current_price)}) to <span className="font-semibold text-teal-700">{alert.cheaper_vendor}</span> ({fmtPrice(alert.cheaper_price)})</p>
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg border border-amber-100 bg-amber-50/40" data-testid={`insight-${index}`}>
      <Package className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
      <div className="min-w-0">
        <p className="text-xs text-slate-700"><span className="font-bold text-navy-900">{alert.item_name}</span> not ordered in <span className="font-bold text-amber-700">{alert.days_since} days</span></p>
        {alert.vendor && <p className="text-[11px] text-slate-400 mt-0.5">Last from {alert.vendor}{alert.last_price > 0 ? ` at ${fmtPrice(alert.last_price)}` : ''}</p>}
      </div>
    </div>
  );
}

/* ═══════════════════ ITEM SEARCH ═══════════════════ */
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
    } catch { toast.error('Search failed'); }
    finally { setSearching(false); }
  }, [api]);

  const handleChange = useCallback((e) => {
    const val = e.target.value;
    setQuery(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(val), 350);
  }, [search]);

  const clear = useCallback(() => {
    setQuery(''); setResults(null);
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
          <Input value={query} onChange={handleChange} placeholder="Search item... e.g. Salmon, Olive Oil" className="pl-9 pr-9 h-10 text-sm border-slate-200 focus:border-teal-500 focus:ring-teal-500/20" data-testid="item-search-input" />
          {query && <button onClick={clear} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600" data-testid="item-search-clear"><X className="w-4 h-4" /></button>}
        </div>
        {searching && <div className="flex items-center justify-center py-8" data-testid="item-search-loading"><Loader2 className="w-5 h-5 animate-spin text-teal-600" /></div>}
        {!searching && results !== null && results.length === 0 && query.length >= 2 && (
          <div className="text-center py-8" data-testid="item-search-empty"><Package className="w-8 h-8 text-slate-300 mx-auto mb-2" /><p className="text-sm text-slate-400">No items found for "{query}"</p></div>
        )}
        {!searching && results && results.length > 0 && (
          <div className="mt-4 space-y-4" data-testid="item-search-results">
            {results.map((item, idx) => (
              <div key={idx} className="border border-slate-100 rounded-lg overflow-hidden" data-testid={`search-result-${idx}`}>
                <div className="flex items-center justify-between px-4 py-3 bg-slate-50/60">
                  <div className="flex items-center gap-2"><Tag className="w-3.5 h-3.5 text-teal-600" /><span className="text-sm font-bold text-navy-900">{item.item_name}</span></div>
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

/* ─── Loading / Empty ─── */
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

/* ═══════════════════ QUICK ACTIONS ═══════════════════ */
const QUICK_ACTIONS = [
  { label: 'Add Expense', icon: Plus, path: '/expenses', color: 'bg-teal-600', hoverColor: 'hover:bg-teal-700' },
  { label: 'Sales', icon: DollarSign, path: '/sales', color: 'bg-indigo-600', hoverColor: 'hover:bg-indigo-700' },
  { label: 'Compare Vendors', icon: GitCompare, path: '/purchase-decisions', color: 'bg-amber-600', hoverColor: 'hover:bg-amber-700' },
  { label: 'View Reports', icon: FileBarChart, path: '/reports', color: 'bg-slate-700', hoverColor: 'hover:bg-slate-800' },
];

function QuickActions({ navigate }) {
  return (
    <div className="flex gap-2.5 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-hide" data-testid="quick-actions">
      {QUICK_ACTIONS.map((action, i) => (
        <button
          key={i}
          onClick={() => navigate(action.path, action.state ? { state: action.state } : undefined)}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl ${action.color} ${action.hoverColor} text-white text-xs font-semibold whitespace-nowrap transition-all hover:shadow-md active:scale-[0.97] flex-shrink-0`}
          data-testid={`quick-action-${i}`}
        >
          <action.icon className="w-3.5 h-3.5" />
          {action.label}
        </button>
      ))}
    </div>
  );
}

/* ═══════════════════ DATA FRESHNESS ═══════════════════ */
function DataFreshness({ lastUpdate, purchaseCount }) {
  const label = useMemo(() => {
    if (!lastUpdate) return null;
    try {
      const d = new Date(lastUpdate);
      const now = new Date();
      const diffMs = now - d;
      const diffMin = Math.floor(diffMs / 60000);
      const diffHr = Math.floor(diffMin / 60);
      const diffDay = Math.floor(diffHr / 24);
      let ago;
      if (diffMin < 1) ago = 'just now';
      else if (diffMin < 60) ago = `${diffMin}m ago`;
      else if (diffHr < 24) ago = `${diffHr}h ago`;
      else ago = `${diffDay}d ago`;
      return ago;
    } catch { return null; }
  }, [lastUpdate]);

  if (!label) return null;

  return (
    <div className="flex items-center gap-1.5 text-[11px] text-slate-400" data-testid="data-freshness">
      <Clock className="w-3 h-3" />
      <span>Updated {label}</span>
      <span className="text-slate-300">·</span>
      <span>Based on {purchaseCount || 0} purchase records</span>
    </div>
  );
}

/* ═══════════════════ BEST OPPORTUNITY ═══════════════════ */
function BestOpportunityCard({ opportunities, navigate }) {
  if (!opportunities || !opportunities.length) return null;

  return (
    <Card className="border-2 border-dashed border-teal-200 bg-gradient-to-r from-teal-50/40 to-white shadow-sm" data-testid="best-opportunity-card">
      <CardContent className="py-4 px-5">
        <div className="flex items-center gap-2 mb-3">
          <Zap className="w-4 h-4 text-amber-500" />
          <span className="text-xs font-bold text-navy-900 uppercase tracking-wide">Today's Best Opportunities</span>
        </div>
        <div className="space-y-2.5">
          {opportunities.map((opp, i) => (
            <OpportunityRow key={i} opp={opp} index={i} navigate={navigate} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function OpportunityRow({ opp, index, navigate }) {
  if (opp.type === 'saving') {
    return (
      <button
        onClick={() => navigate('/purchase-decisions')}
        className="w-full flex items-center justify-between p-3 rounded-xl bg-teal-50 border border-teal-100 hover:border-teal-300 hover:shadow-sm transition-all group text-left"
        data-testid={`opportunity-${index}`}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-teal-600 flex items-center justify-center flex-shrink-0">
            <ArrowRightLeft className="w-4 h-4 text-white" />
          </div>
          <div className="min-w-0">
            <p className="text-sm text-slate-700">
              Buy <span className="font-bold text-navy-900">{opp.item_name}</span> from <span className="font-bold text-teal-700">{opp.vendor}</span>
            </p>
            <p className="text-xs text-teal-600 font-semibold mt-0.5">
              Save {opp.savings_pct}% · {fmtPrice(opp.cheaper_price)} vs {fmtPrice(opp.current_price)}
            </p>
          </div>
        </div>
        <ArrowRight className="w-4 h-4 text-slate-300 group-hover:text-teal-600 transition-colors flex-shrink-0" />
      </button>
    );
  }

  // risk / price_increase
  return (
    <button
      onClick={() => navigate('/expenses')}
      className="w-full flex items-center justify-between p-3 rounded-xl bg-red-50 border border-red-100 hover:border-red-300 hover:shadow-sm transition-all group text-left"
      data-testid={`opportunity-${index}`}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-8 h-8 rounded-lg bg-red-500 flex items-center justify-center flex-shrink-0">
          <ShieldAlert className="w-4 h-4 text-white" />
        </div>
        <div className="min-w-0">
          <p className="text-sm text-slate-700">
            <span className="font-bold text-navy-900">{opp.item_name}</span> price increased at <span className="font-bold text-red-600">{opp.vendor}</span>
          </p>
          <p className="text-xs text-red-600 font-semibold mt-0.5">
            +{opp.change_pct}% · {fmtPrice(opp.old_price)} → {fmtPrice(opp.new_price)}
          </p>
        </div>
      </div>
      <ArrowRight className="w-4 h-4 text-slate-300 group-hover:text-red-500 transition-colors flex-shrink-0" />
    </button>
  );
}

/* ═══════════════════ MAIN PAGE ═══════════════════ */
const EMPTY_ALERTS = [];

export default function DashboardPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [drillDown, setDrillDown] = useState(null);

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

  // Re-fetch dashboard when any page mutates data (create/update/delete)
  useEffect(() => {
    return dataEvents.subscribe(() => load());
  }, [load]);
  const smartAlerts = useMemo(() => data?.smart_alerts || EMPTY_ALERTS, [data]);
  const bestOpps = useMemo(() => data?.best_opportunities || EMPTY_ALERTS, [data]);

  const openDrillDown = useCallback((category) => {
    // Spending categories → full-page navigate to Expenses with tab pre-selected
    if (category === 'raw_materials' || category === 'salaries' || category === 'other') {
      navigate('/expenses', { state: { tab: category } });
      return;
    }
    // Sales → drill-down sheet
    setDrillDown(category);
  }, [navigate]);
  const closeDrillDown = useCallback(() => setDrillDown(null), []);

  if (loading) return <LoadingSkeleton />;

  const hasData = data && (
    (data.month_raw_materials || 0) > 0 ||
    (data.month_salaries || 0) > 0 ||
    (data.month_other_expenses || 0) > 0 ||
    (data.month_sales || 0) > 0
  );

  return (
    <div className="space-y-5 max-w-[1100px]" data-testid="dashboard-page">
      <div>
        <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-navy-900 tracking-tight">Dashboard</h1>
        <p className="text-sm text-slate-400 mt-1">Where am I spending? Where should I buy?</p>
      </div>

      <ItemSearch api={api} />

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <QuickActions navigate={navigate} />
        {hasData && <DataFreshness lastUpdate={data.last_data_update} purchaseCount={data.purchase_count} />}
      </div>

      {!hasData && (
        <Card className="border-2 border-dashed border-slate-200 shadow-sm" data-testid="empty-data-banner">
          <CardContent className="py-8 text-center">
            <BarChart3 className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <h2 className="font-heading text-base font-bold text-navy-900 mb-1">No financial data yet</h2>
            <p className="text-xs text-slate-400 mb-4 max-w-sm mx-auto">Upload your first invoice or add an expense to see your charts come to life.</p>
            <Button onClick={seedData} disabled={seeding} variant="outline" size="sm" className="text-xs" data-testid="seed-data-btn">
              {seeding ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : null} Load Demo Data
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="dashboard-main-row">
        <DonutChart
          raw={data?.month_raw_materials || 0}
          salaries={data?.month_salaries || 0}
          other={data?.month_other_expenses || 0}
          prevRaw={data?.prev_month_raw_materials || 0}
          prevSalaries={data?.prev_month_salaries || 0}
          prevOther={data?.prev_month_other_expenses || 0}
          onCategoryClick={openDrillDown}
        />
        <SalesDonut
          sales={data?.month_sales || 0}
          prevSales={data?.prev_month_sales || 0}
          onCategoryClick={openDrillDown}
        />
        <MarketInsights alerts={smartAlerts} />
      </div>

      <BestOpportunityCard opportunities={bestOpps} navigate={navigate} />

      <DrillDownSheet
        open={!!drillDown}
        onClose={closeDrillDown}
        category={drillDown}
        api={api}
      />
    </div>
  );
}
