import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { toast } from 'sonner';
import {
  TrendingUp, TrendingDown, DollarSign, Search, ShoppingCart,
  ArrowRightLeft, AlertTriangle, CheckCircle2, Package, Minus
} from 'lucide-react';

function fmt(n) { return `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }

export default function PurchaseDecisionsPage() {
  const { api } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await api.get('/purchase-decisions');
      setData(res.data);
    } catch { toast.error('Failed to load purchase data'); }
    finally { setLoading(false); }
  }, [api]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="max-w-[1400px] space-y-6" data-testid="purchase-decisions-loading">
        <Skeleton className="h-8 w-60" />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">{[1,2,3].map(i => <Skeleton key={i} className="h-28 rounded-xl" />)}</div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  if (!data || data.total_items === 0) {
    return (
      <div className="max-w-[1400px] space-y-6" data-testid="purchase-decisions-empty">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight">Smart Purchase Decisions</h1>
          <p className="text-xs text-slate-400 mt-0.5">Data-driven vendor recommendations</p>
        </div>
        <Card className="border border-slate-100 shadow-sm">
          <CardContent className="flex flex-col items-center py-16 text-center">
            <ShoppingCart className="w-12 h-12 text-slate-200 mb-4" />
            <h3 className="text-base font-heading font-bold text-navy-900 mb-1">No purchase data yet</h3>
            <p className="text-sm text-slate-400 max-w-xs">Add purchase records from the Expenses page. The system will compare vendor prices and give you smart recommendations.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const insights = data.insights || [];
  const weeklyChanges = data.weekly_changes || [];
  const items = data.items || [];

  const q = search.toLowerCase().trim();
  const filtered = q ? items.filter(it => it.item.toLowerCase().includes(q) || it.best_vendor.toLowerCase().includes(q)) : items;

  const bestVendorInsights = insights.filter(i => i.type === 'best_vendor');
  const priceIncreaseInsights = insights.filter(i => i.type === 'price_increase');

  return (
    <div className="max-w-[1400px] space-y-6" data-testid="purchase-decisions-page">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight">Smart Purchase Decisions</h1>
        <p className="text-xs text-slate-400 mt-0.5">Data-driven vendor recommendations based on {data.total_items} tracked items</p>
      </div>

      {/* ==================== SUMMARY CARDS ==================== */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SummaryCard
          icon={DollarSign}
          iconBg="bg-emerald-600"
          label="Potential Weekly Savings"
          value={fmt(data.potential_savings)}
          sub={data.potential_savings > 0 ? 'by switching to cheapest vendors' : 'already using best prices'}
          testId="potential-savings-card"
        />
        <SummaryCard
          icon={ArrowRightLeft}
          iconBg="bg-indigo-600"
          label="Vendor Switch Opportunities"
          value={bestVendorInsights.length}
          sub={`item${bestVendorInsights.length !== 1 ? 's' : ''} with cheaper alternatives`}
          testId="switch-opportunities-card"
        />
        <SummaryCard
          icon={TrendingUp}
          iconBg="bg-red-500"
          label="Weekly Price Changes"
          value={weeklyChanges.length}
          sub={`item${weeklyChanges.length !== 1 ? 's' : ''} with price movement this week`}
          testId="weekly-changes-card"
        />
      </div>

      {/* ==================== INSIGHTS ==================== */}
      {(bestVendorInsights.length > 0 || priceIncreaseInsights.length > 0) && (
        <Card className="border border-slate-100 shadow-sm" data-testid="insights-section">
          <CardHeader className="pb-3">
            <CardTitle className="font-heading text-base font-bold flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center"><AlertTriangle className="w-4 h-4 text-amber-600" /></div>
              Smart Insights
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {bestVendorInsights.slice(0, 8).map((ins, i) => (
              <InsightCard key={`bv-${i}`} type="best_vendor" insight={ins} index={i} />
            ))}
            {priceIncreaseInsights.slice(0, 8).map((ins, i) => (
              <InsightCard key={`pi-${i}`} type="price_increase" insight={ins} index={i} />
            ))}
          </CardContent>
        </Card>
      )}

      {/* ==================== WEEKLY CHANGES ==================== */}
      {weeklyChanges.length > 0 && (
        <Card className="border border-slate-100 shadow-sm" data-testid="weekly-changes-section">
          <CardHeader className="pb-3">
            <CardTitle className="font-heading text-base font-bold flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-violet-100 flex items-center justify-center"><TrendingUp className="w-4 h-4 text-violet-600" /></div>
              Weekly Price Changes
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
              {weeklyChanges.slice(0, 12).map((wc, i) => (
                <WeeklyChangeCard key={i} change={wc} index={i} />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ==================== ITEM COMPARISON TABLE ==================== */}
      <Card className="border border-slate-100 shadow-sm overflow-hidden" data-testid="item-comparison-section">
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <CardTitle className="font-heading text-base font-bold flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-teal-100 flex items-center justify-center"><Package className="w-4 h-4 text-teal-600" /></div>
              Item Price Comparison
              <Badge variant="secondary" className="text-[10px] ml-1">{filtered.length}</Badge>
            </CardTitle>
            <div className="relative w-full sm:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input className="pl-9 h-9 text-sm" placeholder="Search item or vendor..." value={search} onChange={(e) => setSearch(e.target.value)} data-testid="pd-search" />
            </div>
          </div>
        </CardHeader>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Item</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Best Vendor</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Best Price</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-center">Vendors</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Saving/Unit</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-center">Week Trend</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 ? (
                <TableRow><TableCell colSpan={6} className="text-center py-10 text-sm text-slate-400">No items match your search</TableCell></TableRow>
              ) : filtered.map((item, i) => (
                <TableRow key={item.item} className={`transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/30'} hover:bg-teal-50/20`} data-testid={`pd-item-row-${i}`}>
                  <TableCell>
                    <div>
                      <p className="text-sm font-semibold text-navy-900">{item.item}</p>
                      {item.unit && <p className="text-[10px] text-slate-400">per {item.unit}</p>}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                      <span className="text-sm text-navy-900">{item.best_vendor}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-right text-sm font-bold text-navy-900 tabular-nums">{fmt(item.best_price)}</TableCell>
                  <TableCell className="text-center">
                    <Badge variant="secondary" className="text-[10px]">{item.vendor_count}</Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {item.saving_per_unit > 0 ? (
                      <Badge className="bg-emerald-100 text-emerald-700 border-0 text-[11px] font-bold tabular-nums">
                        {fmt(item.saving_per_unit)}
                      </Badge>
                    ) : (
                      <span className="text-xs text-slate-300"><Minus className="w-3 h-3 inline" /></span>
                    )}
                  </TableCell>
                  <TableCell className="text-center">
                    {item.week_change ? (
                      <Badge className={`border-0 text-[10px] font-bold ${item.week_change.direction === 'up' ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'}`}>
                        {item.week_change.direction === 'up' ? '+' : ''}{item.week_change.change_pct}%
                      </Badge>
                    ) : (
                      <span className="text-xs text-slate-300"><Minus className="w-3 h-3 inline" /></span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}

// ======================== SUB-COMPONENTS ========================

function SummaryCard({ icon: Icon, iconBg, label, value, sub, testId }) {
  return (
    <Card className="border border-slate-100 shadow-sm" data-testid={testId}>
      <CardContent className="p-5">
        <div className="flex items-center gap-3 mb-3">
          <div className={`w-10 h-10 rounded-xl ${iconBg} flex items-center justify-center`}>
            <Icon className="w-5 h-5 text-white" />
          </div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{label}</span>
        </div>
        <p className="text-2xl font-bold text-navy-900 tabular-nums">{value}</p>
        <p className="text-[11px] text-slate-400 mt-0.5">{sub}</p>
      </CardContent>
    </Card>
  );
}

function InsightCard({ type, insight, index }) {
  if (type === 'best_vendor') {
    return (
      <div className="flex items-start gap-3 p-3 rounded-lg bg-emerald-50/70 border border-emerald-100" data-testid={`insight-best-vendor-${index}`}>
        <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center flex-shrink-0 mt-0.5">
          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
        </div>
        <div>
          <p className="text-sm text-navy-900">
            <span className="font-bold">Best vendor for {insight.item}:</span>{' '}
            <span className="font-bold text-emerald-700">{insight.best_vendor}</span>{' '}
            at {fmt(insight.best_price)}/{insight.unit}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">
            Saving {fmt(insight.saving_per_unit)}/{insight.unit} vs {insight.worst_vendor} ({insight.pct}% cheaper)
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3 p-3 rounded-lg bg-red-50/70 border border-red-100" data-testid={`insight-price-increase-${index}`}>
      <div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center flex-shrink-0 mt-0.5">
        <TrendingUp className="w-4 h-4 text-red-600" />
      </div>
      <div>
        <p className="text-sm text-navy-900">
          <span className="font-bold">{insight.item}</span> price increased by{' '}
          <span className="font-bold text-red-600">{insight.change_pct}%</span> this week
        </p>
        <p className="text-xs text-slate-500 mt-0.5">
          Was {fmt(insight.last_week)}/{insight.unit} → now {fmt(insight.this_week)}/{insight.unit}
        </p>
      </div>
    </div>
  );
}

function WeeklyChangeCard({ change, index }) {
  const isUp = change.direction === 'up';
  return (
    <div className={`flex items-center gap-3 p-3 rounded-lg border ${isUp ? 'bg-red-50/50 border-red-100' : 'bg-emerald-50/50 border-emerald-100'}`} data-testid={`weekly-change-${index}`}>
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${isUp ? 'bg-red-100' : 'bg-emerald-100'}`}>
        {isUp ? <TrendingUp className="w-4 h-4 text-red-600" /> : <TrendingDown className="w-4 h-4 text-emerald-600" />}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-navy-900 truncate">{change.item}</p>
        <p className="text-[11px] text-slate-500">
          {fmt(change.last_week_avg)} → {fmt(change.this_week_avg)}
          {change.unit && <span className="text-slate-400">/{change.unit}</span>}
        </p>
      </div>
      <Badge className={`border-0 text-xs font-bold tabular-nums ${isUp ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'}`}>
        {isUp ? '+' : ''}{change.change_pct}%
      </Badge>
    </div>
  );
}
