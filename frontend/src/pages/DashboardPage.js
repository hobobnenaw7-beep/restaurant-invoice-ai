import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  TrendingUp, TrendingDown, DollarSign, ShoppingCart,
  ArrowUpRight, ArrowDownRight, Loader2, BarChart3,
  PackageOpen, CircleDollarSign, ChartNoAxesCombined, Zap,
  AlertTriangle, X, Wallet
} from 'lucide-react';
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

function fmt(n) {
  if (n == null) return '$0';
  if (Math.abs(n) >= 1000) return `$${(n / 1000).toFixed(1)}k`;
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function pctChange(curr, prev) {
  if (!prev || prev === 0) return null;
  return ((curr - prev) / prev * 100).toFixed(1);
}

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

const alertConfig = {
  low_stock: {
    icon: PackageOpen,
    label: 'Low Stock',
    borderColor: 'border-l-amber-500',
    bgColor: 'bg-amber-50/60',
    iconBg: 'bg-amber-100',
    iconColor: 'text-amber-600',
    badgeBg: 'bg-amber-100 text-amber-700',
  },
  cost_increase: {
    icon: CircleDollarSign,
    label: 'Cost Increase',
    borderColor: 'border-l-red-500',
    bgColor: 'bg-red-50/60',
    iconBg: 'bg-red-100',
    iconColor: 'text-red-600',
    badgeBg: 'bg-red-100 text-red-700',
  },
  margin_drop: {
    icon: ChartNoAxesCombined,
    label: 'Margin Drop',
    borderColor: 'border-l-violet-500',
    bgColor: 'bg-violet-50/60',
    iconBg: 'bg-violet-100',
    iconColor: 'text-violet-600',
    badgeBg: 'bg-violet-100 text-violet-700',
  },
};

function SmartAlertCard({ alert, index }) {
  const config = alertConfig[alert.type] || alertConfig.cost_increase;
  const Icon = config.icon;

  return (
    <div
      className={`flex items-start gap-3 p-3.5 rounded-xl border-l-[3px] ${config.borderColor} ${config.bgColor} transition-all hover:shadow-sm`}
      data-testid={`smart-alert-${index}`}
    >
      <div className={`w-8 h-8 rounded-lg ${config.iconBg} flex items-center justify-center flex-shrink-0 mt-0.5`}>
        <Icon className={`w-4 h-4 ${config.iconColor}`} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-xs font-bold text-navy-900 leading-tight">{alert.title}</span>
          {alert.severity === 'high' && (
            <Badge className="bg-red-600 text-white text-[9px] px-1.5 py-0 h-4 font-bold">HIGH</Badge>
          )}
        </div>
        <p className="text-[11px] text-slate-500 leading-relaxed">{alert.detail}</p>
      </div>
      <Badge variant="outline" className={`text-[9px] px-1.5 py-0 h-5 font-semibold border-0 flex-shrink-0 ${config.badgeBg}`}>
        {config.label}
      </Badge>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-8" data-testid="dashboard-loading">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {[1,2,3,4,5,6].map(i => (
          <Card key={i} className="border border-slate-100"><CardContent className="p-6"><Skeleton className="h-10 w-10 rounded-xl mb-4" /><Skeleton className="h-8 w-32 mb-2" /><Skeleton className="h-3 w-20" /></CardContent></Card>
        ))}
      </div>
      <Skeleton className="h-48 rounded-xl" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6"><Skeleton className="h-72 rounded-xl" /><Skeleton className="h-72 rounded-xl" /></div>
    </div>
  );
}

function EmptyDashboard({ onSeed, seeding }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center" data-testid="empty-dashboard">
      <div className="w-20 h-20 rounded-2xl bg-slate-100 flex items-center justify-center mb-6">
        <BarChart3 className="w-10 h-10 text-slate-300" />
      </div>
      <h2 className="font-heading text-xl font-bold text-navy-900 mb-2">No financial data yet</h2>
      <p className="text-sm text-slate-500 max-w-sm mb-8">Upload your first invoice or load demo data to see your dashboard come to life.</p>
      <Button onClick={onSeed} disabled={seeding} className="bg-teal-600 hover:bg-teal-700 text-white h-11 px-6 text-sm font-semibold" data-testid="seed-data-btn">
        {seeding ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
        Load Demo Data
      </Button>
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg px-3 py-2 shadow-lg">
      <p className="text-[11px] font-semibold text-slate-500 mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} className="text-xs"><span className="font-semibold" style={{ color: p.color }}>{p.name}:</span> {fmt(p.value)}</p>
      ))}
    </div>
  );
};

export default function DashboardPage() {
  const { api } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);

  const load = async () => {
    try { const res = await api.get('/dashboard/summary'); setData(res.data); }
    catch { toast.error('Failed to load dashboard'); }
    finally { setLoading(false); }
  };

  const seedData = async () => {
    setSeeding(true);
    try { await api.post('/seed'); toast.success('Demo data loaded!'); await load(); }
    catch { toast.error('Failed to seed data'); }
    finally { setSeeding(false); }
  };

  useEffect(() => { load(); }, []); // eslint-disable-line

  if (loading) return <LoadingSkeleton />;

  const isEmpty = !data || (data.month_sales === 0 && data.month_purchases === 0);
  if (isEmpty) return <EmptyDashboard onSeed={seedData} seeding={seeding} />;

  const smartAlerts = data.smart_alerts || [];
  const priceAlerts = data.price_alerts || [];
  const alertCounts = {
    low_stock: smartAlerts.filter(a => a.type === 'low_stock').length,
    cost_increase: smartAlerts.filter(a => a.type === 'cost_increase').length,
    margin_drop: smartAlerts.filter(a => a.type === 'margin_drop').length,
  };

  return (
    <div className="space-y-8 max-w-[1400px]" data-testid="dashboard-page">
      <div>
        <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-navy-900 tracking-tight">Dashboard</h1>
        <p className="text-sm text-slate-400 mt-1">Your restaurant's financial pulse</p>
      </div>

      {/* Primary KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        <Card className="border border-slate-100 shadow-sm"><CardContent className="p-6">
          <KPI label="Today Sales" value={data.today_sales} prev={null} accent icon={DollarSign} testId="stat-today-sales" />
        </CardContent></Card>
        <Card className="border border-slate-100 shadow-sm"><CardContent className="p-6">
          <KPI label="Today Purchases" value={data.today_purchases} prev={null} icon={ShoppingCart} testId="stat-today-purchases" />
        </CardContent></Card>
        <Card className="border border-slate-100 shadow-sm"><CardContent className="p-6">
          <KPI label="This Week Sales" value={data.week_sales} prev={data.prev_week_sales} accent icon={TrendingUp} testId="stat-week-sales" />
        </CardContent></Card>
        <Card className="border border-slate-100 shadow-sm"><CardContent className="p-6">
          <KPI label="This Week Purchases" value={data.week_purchases} prev={data.prev_week_purchases} icon={ShoppingCart} testId="stat-week-purchases" />
        </CardContent></Card>
        <Card className="border border-slate-100 shadow-sm"><CardContent className="p-6">
          <KPI label="This Month Sales" value={data.month_sales} prev={data.prev_month_sales} accent icon={TrendingUp} testId="stat-month-sales" />
        </CardContent></Card>
        <Card className="border border-slate-100 shadow-sm"><CardContent className="p-6">
          <KPI label="This Month Purchases" value={data.month_purchases} prev={data.prev_month_purchases} icon={ShoppingCart} testId="stat-month-purchases" />
        </CardContent></Card>
      </div>

      {/* Profit Overview */}
      <div data-testid="profit-overview-section">
        <div className="flex items-center gap-2.5 mb-4">
          <div className="w-8 h-8 rounded-lg bg-teal-600 flex items-center justify-center">
            <Wallet className="w-4 h-4 text-white" />
          </div>
          <div>
            <h2 className="font-heading text-sm font-bold text-navy-900">Net Profit</h2>
            <p className="text-[10px] text-slate-400">Total Sales minus all Expenses (Raw Materials + Salaries + Other)</p>
          </div>
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
                    {pct !== null && (
                      <span className={`inline-flex items-center text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${pctUp ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
                        {pctUp ? <ArrowUpRight className="w-2.5 h-2.5 mr-0.5" /> : <ArrowDownRight className="w-2.5 h-2.5 mr-0.5" />}
                        {Math.abs(pct)}%
                      </span>
                    )}
                  </div>
                  <div className="flex items-baseline gap-1">
                    {!isPositive && <span className="text-lg font-bold text-red-500">-</span>}
                    <span className={`text-2xl font-extrabold tabular-nums tracking-tight ${isPositive ? 'text-emerald-600' : 'text-red-500'}`}>
                      {fmt(Math.abs(val))}
                    </span>
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

      {/* Smart Alerts Section */}
      {smartAlerts.length > 0 && (
        <Card className="border border-slate-200/80 shadow-sm" data-testid="smart-alerts-section">
          <CardHeader className="pb-3 pt-5 px-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-navy-900 flex items-center justify-center">
                  <Zap className="w-4 h-4 text-white" />
                </div>
                <div>
                  <CardTitle className="font-heading text-sm font-bold text-navy-900">Smart Alerts</CardTitle>
                  <p className="text-[10px] text-slate-400 mt-0.5">Auto-detected from your financial data</p>
                </div>
              </div>
              <div className="flex gap-1.5" data-testid="alert-type-counts">
                {alertCounts.low_stock > 0 && (
                  <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 text-[10px] px-2 py-0.5">
                    <PackageOpen className="w-3 h-3 mr-1" />{alertCounts.low_stock} Stock
                  </Badge>
                )}
                {alertCounts.cost_increase > 0 && (
                  <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200 text-[10px] px-2 py-0.5">
                    <CircleDollarSign className="w-3 h-3 mr-1" />{alertCounts.cost_increase} Cost
                  </Badge>
                )}
                {alertCounts.margin_drop > 0 && (
                  <Badge variant="outline" className="bg-violet-50 text-violet-700 border-violet-200 text-[10px] px-2 py-0.5">
                    <ChartNoAxesCombined className="w-3 h-3 mr-1" />{alertCounts.margin_drop} Margin
                  </Badge>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent className="px-6 pb-5">
            <div className="space-y-2">
              {smartAlerts.map((alert, i) => (
                <SmartAlertCard key={i} alert={alert} index={i} />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Price Alerts Section */}
      {priceAlerts.length > 0 && (
        <Card className="border border-slate-200/80 shadow-sm" data-testid="price-alerts-section">
          <CardHeader className="pb-3 pt-5 px-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-red-600 flex items-center justify-center">
                  <AlertTriangle className="w-4 h-4 text-white" />
                </div>
                <div>
                  <CardTitle className="font-heading text-sm font-bold text-navy-900">Price Alerts</CardTitle>
                  <p className="text-[10px] text-slate-400 mt-0.5">Price increases detected when recording purchases</p>
                </div>
              </div>
              <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200 text-[10px] px-2 py-0.5 font-bold">
                {priceAlerts.length} alert{priceAlerts.length !== 1 ? 's' : ''}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="px-6 pb-5">
            <div className="space-y-2">
              {priceAlerts.map((alert, i) => (
                <div
                  key={alert.id}
                  className="flex items-start gap-3 p-3.5 rounded-xl border-l-[3px] border-l-red-500 bg-red-50/60 transition-all hover:shadow-sm"
                  data-testid={`price-alert-${i}`}
                >
                  <div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <CircleDollarSign className="w-4 h-4 text-red-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-xs font-bold text-navy-900 leading-tight">
                        Price increase detected for {alert.item_name}
                      </span>
                      {alert.change_pct > 15 && (
                        <Badge className="bg-red-600 text-white text-[9px] px-1.5 py-0 h-4 font-bold">HIGH</Badge>
                      )}
                    </div>
                    <p className="text-[11px] text-slate-600 leading-relaxed">
                      Previous price: <span className="font-semibold text-navy-900">${alert.previous_price?.toFixed(2)}</span>
                      <span className="mx-1.5 text-slate-300">&rarr;</span>
                      New price: <span className="font-semibold text-red-600">${alert.new_price?.toFixed(2)}</span>
                      <span className="ml-1.5 font-bold text-red-600">(+{alert.change_pct}%)</span>
                    </p>
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      Vendor: {alert.vendor} &middot; {alert.invoice_date}
                    </p>
                  </div>
                  <Button
                    size="sm" variant="ghost"
                    className="h-6 w-6 p-0 flex-shrink-0 text-slate-400 hover:text-red-500"
                    onClick={async () => {
                      try {
                        await api.delete(`/alerts/prices/${alert.id}`);
                        setData(prev => ({ ...prev, price_alerts: prev.price_alerts.filter(a => a.id !== alert.id) }));
                      } catch { toast.error('Failed to dismiss'); }
                    }}
                    data-testid={`dismiss-alert-${i}`}
                  >
                    <X className="w-3.5 h-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 border border-slate-100 shadow-sm" data-testid="weekly-trends-chart">
          <CardHeader className="pb-0 pt-5 px-6">
            <CardTitle className="font-heading text-sm font-bold text-navy-900 uppercase tracking-wide">Weekly Sales vs Purchases</CardTitle>
          </CardHeader>
          <CardContent className="px-2 pb-4 pt-2">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.weekly_trends || []} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
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
          <CardHeader className="pb-0 pt-5 px-6">
            <CardTitle className="font-heading text-sm font-bold text-navy-900 uppercase tracking-wide">Top Items</CardTitle>
          </CardHeader>
          <CardContent className="px-2 pb-4 pt-2">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.top_items || []} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
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
          <CardHeader className="pb-3 pt-5 px-6">
            <CardTitle className="font-heading text-sm font-bold text-navy-900 uppercase tracking-wide">Top Vendors</CardTitle>
          </CardHeader>
          <CardContent className="px-6 pb-5">
            <div className="space-y-2.5">
              {(data.top_suppliers || []).map((s, i) => {
                const maxVal = data.top_suppliers[0]?.total || 1;
                return (
                  <div key={i} className="group">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-navy-900">{s.name}</span>
                      <span className="text-sm font-bold text-navy-900 tabular-nums">{fmt(s.total)}</span>
                    </div>
                    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full bg-teal-500 rounded-full transition-all duration-500" style={{ width: `${(s.total / maxVal * 100)}%` }} />
                    </div>
                  </div>
                );
              })}
              {!data.top_suppliers?.length && <p className="text-sm text-slate-400 py-6 text-center">No vendor data yet</p>}
            </div>
          </CardContent>
        </Card>

        <Card className="border border-slate-100 shadow-sm" data-testid="recent-alerts">
          <CardHeader className="pb-3 pt-5 px-6">
            <CardTitle className="font-heading text-sm font-bold text-navy-900 uppercase tracking-wide">Recent Alerts</CardTitle>
          </CardHeader>
          <CardContent className="px-6 pb-5">
            <div className="space-y-2">
              {(data.alerts || []).slice(0, 5).map((a, i) => (
                <div key={i} className={`flex items-start gap-3 p-3 rounded-lg ${a.severity === 'high' ? 'bg-red-50/60' : a.severity === 'medium' ? 'bg-amber-50/60' : 'bg-slate-50'}`}>
                  <div className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${a.severity === 'high' ? 'bg-red-500' : a.severity === 'medium' ? 'bg-amber-500' : 'bg-slate-400'}`} />
                  <p className="text-xs text-slate-600 leading-relaxed">{a.message}</p>
                </div>
              ))}
              {!data.alerts?.length && <p className="text-sm text-slate-400 py-6 text-center">No alerts</p>}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
