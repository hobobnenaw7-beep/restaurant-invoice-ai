import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import { Loader2, TrendingUp, TrendingDown, DollarSign, ShoppingCart, AlertTriangle, FileText } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';

function fmt(n) { return n != null ? `$${Number(n).toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}` : '$0'; }

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg px-3 py-2 shadow-lg">
      <p className="text-[10px] font-bold text-slate-400 mb-1">{label}</p>
      {payload.map((p, i) => <p key={i} className="text-xs"><span className="font-semibold" style={{ color: p.color }}>{p.name}:</span> {fmt(p.value)}</p>)}
    </div>
  );
};

function BigKPI({ label, value, icon: Icon, color, sub }) {
  return (
    <div className="text-center">
      <div className={`w-11 h-11 rounded-xl flex items-center justify-center mx-auto mb-2 ${color}`}>
        <Icon className="w-5 h-5 text-white" />
      </div>
      <p className="font-heading text-2xl font-extrabold text-navy-900 tracking-tight">{fmt(value)}</p>
      <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">{label}</p>
      {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function ReportsPage() {
  const { api } = useAuth();
  const [reportType, setReportType] = useState('weekly');
  const [date, setDate] = useState('');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const params = { report_type: reportType };
      if (date) params.date = date;
      const res = await api.get('/reports', { params });
      setReport(res.data);
    } catch { toast.error('Failed to load report'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [reportType, date]); // eslint-disable-line

  return (
    <div className="space-y-8 max-w-[1400px]" data-testid="reports-page">
      <div>
        <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-navy-900 tracking-tight">Reports</h1>
        <p className="text-sm text-slate-400 mt-1">Financial performance at a glance</p>
      </div>

      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
        <Tabs value={reportType} onValueChange={setReportType}>
          <TabsList className="bg-slate-100 h-10" data-testid="report-type-tabs">
            <TabsTrigger value="weekly" className="text-xs font-semibold px-5">Weekly</TabsTrigger>
            <TabsTrigger value="monthly" className="text-xs font-semibold px-5">Monthly</TabsTrigger>
            <TabsTrigger value="yearly" className="text-xs font-semibold px-5">Yearly</TabsTrigger>
          </TabsList>
        </Tabs>
        <Input
          type={reportType === 'yearly' ? 'number' : 'date'}
          className="w-48 h-10"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          placeholder={reportType === 'yearly' ? '2025' : ''}
          data-testid="report-date-input"
        />
      </div>

      {loading ? (
        <div className="space-y-6"><Skeleton className="h-32 rounded-xl" /><div className="grid grid-cols-1 lg:grid-cols-2 gap-6"><Skeleton className="h-64 rounded-xl" /><Skeleton className="h-64 rounded-xl" /></div></div>
      ) : !report ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4"><FileText className="w-6 h-6 text-slate-300" /></div>
          <h3 className="font-heading text-base font-bold text-navy-900 mb-1">No report data</h3>
          <p className="text-sm text-slate-400">Select a date range to generate a report.</p>
        </div>
      ) : (
        <>
          {/* Date range banner */}
          <div className="text-xs font-semibold text-slate-400 tracking-wide">
            {report.date_range?.start} &mdash; {report.date_range?.end} &middot; {report.purchase_count} purchases &middot; {report.sales_count} sales reports
          </div>

          {/* Hero KPIs — understandable in 5 seconds */}
          <Card className="border border-slate-100 shadow-sm">
            <CardContent className="py-8 px-6">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-8">
                <BigKPI label="Revenue" value={report.total_sales} icon={DollarSign} color="bg-teal-600" />
                <BigKPI label="Purchases" value={report.total_purchases} icon={ShoppingCart} color="bg-navy-900" />
                <BigKPI label="Profit" value={report.profit} icon={report.profit >= 0 ? TrendingUp : TrendingDown} color={report.profit >= 0 ? 'bg-emerald-600' : 'bg-red-500'} />
                <BigKPI label="Alerts" value={null} icon={AlertTriangle} color="bg-amber-500" sub={`${report.alerts?.length || 0} active`} />
              </div>
            </CardContent>
          </Card>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="border border-slate-100 shadow-sm">
              <CardHeader className="pb-0 pt-5 px-6"><CardTitle className="font-heading text-sm font-bold text-navy-900 uppercase tracking-wide">Daily Breakdown</CardTitle></CardHeader>
              <CardContent className="px-2 pb-4 pt-2">
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={report.daily_breakdown || []} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                      <defs>
                        <linearGradient id="rs" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#0d9488" stopOpacity={0.18} /><stop offset="100%" stopColor="#0d9488" stopOpacity={0} /></linearGradient>
                        <linearGradient id="rp" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#0f172a" stopOpacity={0.1} /><stop offset="100%" stopColor="#0f172a" stopOpacity={0} /></linearGradient>
                      </defs>
                      <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} />
                      <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} width={45} />
                      <Tooltip content={<CustomTooltip />} />
                      <Area type="monotone" dataKey="sales" stroke="#0d9488" fill="url(#rs)" strokeWidth={2} name="Sales" dot={false} />
                      <Area type="monotone" dataKey="purchases" stroke="#0f172a" fill="url(#rp)" strokeWidth={1.5} name="Purchases" dot={false} strokeDasharray="4 4" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            <Card className="border border-slate-100 shadow-sm">
              <CardHeader className="pb-0 pt-5 px-6"><CardTitle className="font-heading text-sm font-bold text-navy-900 uppercase tracking-wide">Spending by Supplier</CardTitle></CardHeader>
              <CardContent className="px-2 pb-4 pt-2">
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={report.spending_by_supplier || []} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
                      <XAxis type="number" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} />
                      <YAxis dataKey="name" type="category" width={130} axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#475569' }} />
                      <Tooltip content={<CustomTooltip />} />
                      <Bar dataKey="total" fill="#0d9488" radius={[0, 6, 6, 0]} barSize={14} name="Spent" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Top items */}
          <Card className="border border-slate-100 shadow-sm">
            <CardHeader className="pb-0 pt-5 px-6"><CardTitle className="font-heading text-sm font-bold text-navy-900 uppercase tracking-wide">Top Purchased Items</CardTitle></CardHeader>
            <CardContent className="px-2 pb-4 pt-2">
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={report.top_items || []} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} width={45} />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="total" fill="#0f172a" radius={[6, 6, 0, 0]} barSize={24} name="Spent" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
