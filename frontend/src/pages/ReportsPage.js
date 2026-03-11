import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  TrendingUp, TrendingDown, DollarSign, ShoppingCart, Percent,
  FileText, Download, FileSpreadsheet, ArrowUpRight, ArrowDownRight, Minus
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer
} from 'recharts';

function fmt(n) {
  if (n == null) return '$0';
  const abs = Math.abs(Number(n));
  if (abs >= 1000) return `$${(Number(n) / 1000).toFixed(1)}k`;
  return `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}
function fmtFull(n) {
  return n != null ? `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '$0.00';
}
function pctChange(cur, prev) {
  if (!prev || prev === 0) return null;
  return ((cur - prev) / prev * 100);
}

const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg px-3 py-2 shadow-lg">
      <p className="text-[10px] font-bold text-slate-400 mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} className="text-xs">
          <span className="font-semibold" style={{ color: p.color }}>{p.name}:</span> {fmtFull(p.value)}
        </p>
      ))}
    </div>
  );
};

function KPICard({ label, value, prevValue, icon: Icon, color, invertColor = false }) {
  const change = pctChange(value, prevValue);
  const isUp = change !== null && change >= 0;
  // For Revenue/Profit: up=good(green), down=bad(red). For Purchases: up=bad(red), down=good(green)
  const isGood = invertColor ? !isUp : isUp;
  const displayVal = fmtFull(value);

  return (
    <Card className="border border-slate-200/80 shadow-sm" data-testid={`kpi-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${color}`}>
            <Icon className="w-4 h-4 text-white" />
          </div>
          {change !== null && (
            <div className={`flex items-center gap-0.5 text-[11px] font-semibold rounded-full px-2 py-0.5 ${
              isGood ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'
            }`}>
              {isUp ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
              {Math.abs(change).toFixed(1)}%
            </div>
          )}
        </div>
        <p className="font-heading text-xl font-extrabold text-navy-900 tracking-tight">{displayVal}</p>
        <p className="text-[11px] text-slate-400 font-medium mt-0.5">{label}</p>
        {prevValue != null && prevValue !== 0 && (
          <p className="text-[10px] text-slate-400 mt-1">Prev: {fmtFull(prevValue)}</p>
        )}
      </CardContent>
    </Card>
  );
}

function MarginCard({ margin }) {
  return (
    <Card className="border border-slate-200/80 shadow-sm" data-testid="kpi-margin">
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-violet-600">
            <Percent className="w-4 h-4 text-white" />
          </div>
        </div>
        <p className="font-heading text-xl font-extrabold text-navy-900 tracking-tight">{margin}%</p>
        <p className="text-[11px] text-slate-400 font-medium mt-0.5">Gross Margin</p>
      </CardContent>
    </Card>
  );
}

export default function ReportsPage() {
  const { api } = useAuth();
  const [reportType, setReportType] = useState('weekly');
  const [date, setDate] = useState('');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { report_type: reportType };
      if (date) params.date = date;
      const res = await api.get('/reports', { params });
      setReport(res.data);
    } catch { toast.error('Failed to load report'); }
    finally { setLoading(false); }
  }, [reportType, date, api]);

  useEffect(() => { load(); }, [load]);

  const handleDownload = async (format) => {
    setDownloading(format);
    try {
      const params = { report_type: reportType, fmt: format };
      if (date) params.date = date;
      const res = await api.get('/reports/download', { params, responseType: 'blob' });
      const ext = format === 'pdf' ? 'pdf' : 'xlsx';
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${reportType}_${report?.date_range?.start || 'latest'}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success(`${format.toUpperCase()} downloaded`);
    } catch { toast.error(`Failed to download ${format.toUpperCase()}`); }
    finally { setDownloading(''); }
  };

  const periodLabel = reportType === 'weekly' ? 'week' : reportType === 'monthly' ? 'month' : 'year';

  return (
    <div className="space-y-6 max-w-[1400px]" data-testid="reports-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight">Financial Reports</h1>
          <p className="text-xs text-slate-400 mt-0.5">Performance snapshot with period-over-period comparison</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs border-slate-200"
            onClick={() => handleDownload('pdf')}
            disabled={!!downloading || !report}
            data-testid="download-pdf-btn"
          >
            {downloading === 'pdf' ? <span className="animate-spin mr-1.5">...</span> : <Download className="w-3.5 h-3.5 mr-1.5" />}
            PDF
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs border-slate-200"
            onClick={() => handleDownload('excel')}
            disabled={!!downloading || !report}
            data-testid="download-excel-btn"
          >
            {downloading === 'excel' ? <span className="animate-spin mr-1.5">...</span> : <FileSpreadsheet className="w-3.5 h-3.5 mr-1.5" />}
            Excel
          </Button>
        </div>
      </div>

      {/* Tabs + Date */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <Tabs value={reportType} onValueChange={(v) => { setReportType(v); setDate(''); }}>
          <TabsList className="bg-slate-100 h-9" data-testid="report-type-tabs">
            <TabsTrigger value="weekly" className="text-xs font-semibold px-5" data-testid="tab-weekly">Weekly</TabsTrigger>
            <TabsTrigger value="monthly" className="text-xs font-semibold px-5" data-testid="tab-monthly">Monthly</TabsTrigger>
            <TabsTrigger value="yearly" className="text-xs font-semibold px-5" data-testid="tab-yearly">Yearly</TabsTrigger>
          </TabsList>
        </Tabs>
        <Input
          type={reportType === 'yearly' ? 'number' : 'date'}
          className="w-44 h-9 text-xs"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          placeholder={reportType === 'yearly' ? new Date().getFullYear().toString() : ''}
          data-testid="report-date-input"
        />
        {report?.date_range && (
          <span className="text-[11px] text-slate-400 font-medium" data-testid="report-date-range">
            {report.date_range.start} to {report.date_range.end}
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[1,2,3,4].map(i => <Skeleton key={i} className="h-28 rounded-xl" />)}
          </div>
          <Skeleton className="h-64 rounded-xl" />
        </div>
      ) : !report ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
            <FileText className="w-6 h-6 text-slate-300" />
          </div>
          <h3 className="font-heading text-base font-bold text-navy-900 mb-1">No report data</h3>
          <p className="text-sm text-slate-400">Select a date range to generate a report.</p>
        </div>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="kpi-cards">
            <KPICard label="Revenue" value={report.total_sales} prevValue={report.prev_sales} icon={DollarSign} color="bg-teal-600" />
            <KPICard label="Purchases" value={report.total_purchases} prevValue={report.prev_purchases} icon={ShoppingCart} color="bg-navy-800" invertColor />
            <KPICard label="Profit" value={report.profit} prevValue={report.prev_profit} icon={report.profit >= 0 ? TrendingUp : TrendingDown} color={report.profit >= 0 ? 'bg-emerald-600' : 'bg-red-500'} />
            <MarginCard margin={report.margin_pct} />
          </div>

          {/* Trend Chart */}
          {report.daily_breakdown?.length > 0 && (
            <Card className="border border-slate-200/80 shadow-sm" data-testid="trend-chart">
              <CardHeader className="pb-0 pt-4 px-5">
                <CardTitle className="font-heading text-sm font-bold text-navy-900">
                  Revenue vs Purchases
                  <span className="text-[10px] font-normal text-slate-400 ml-2">Daily trend this {periodLabel}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="px-2 pb-3 pt-2">
                <div className="h-52">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={report.daily_breakdown} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                      <defs>
                        <linearGradient id="gSales" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#0d9488" stopOpacity={0.2} />
                          <stop offset="100%" stopColor="#0d9488" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="gPurch" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#0f172a" stopOpacity={0.08} />
                          <stop offset="100%" stopColor="#0f172a" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }}
                        tickFormatter={(v) => { const d = new Date(v + 'T00:00:00'); return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); }} />
                      <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }}
                        tickFormatter={v => `$${(v/1000).toFixed(0)}k`} width={45} />
                      <Tooltip content={<ChartTooltip />} />
                      <Area type="monotone" dataKey="sales" stroke="#0d9488" fill="url(#gSales)" strokeWidth={2} name="Sales" dot={false} />
                      <Area type="monotone" dataKey="purchases" stroke="#0f172a" fill="url(#gPurch)" strokeWidth={1.5} name="Purchases" dot={false} strokeDasharray="4 4" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Tables Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Supplier Spending Table */}
            <Card className="border border-slate-200/80 shadow-sm" data-testid="supplier-table">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="font-heading text-sm font-bold text-navy-900">Supplier Spending</CardTitle>
              </CardHeader>
              <CardContent className="px-0 pb-2">
                {report.spending_by_supplier?.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-100">
                          <th className="text-left font-semibold text-slate-400 uppercase tracking-wider px-5 py-2 text-[10px]">Supplier</th>
                          <th className="text-right font-semibold text-slate-400 uppercase tracking-wider px-5 py-2 text-[10px]">Total</th>
                          <th className="text-right font-semibold text-slate-400 uppercase tracking-wider px-5 py-2 text-[10px]">Invoices</th>
                          <th className="text-right font-semibold text-slate-400 uppercase tracking-wider px-5 py-2 text-[10px]">Avg/Invoice</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.spending_by_supplier.map((s, i) => (
                          <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors" data-testid={`supplier-row-${i}`}>
                            <td className="px-5 py-2.5 font-medium text-navy-900">{s.name}</td>
                            <td className="px-5 py-2.5 text-right font-semibold text-navy-900">{fmtFull(s.total)}</td>
                            <td className="px-5 py-2.5 text-right text-slate-500">{s.invoices}</td>
                            <td className="px-5 py-2.5 text-right text-slate-500">{s.invoices > 0 ? fmtFull(s.total / s.invoices) : '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 px-5 py-4">No supplier data for this period.</p>
                )}
              </CardContent>
            </Card>

            {/* Price Changes Table */}
            <Card className="border border-slate-200/80 shadow-sm" data-testid="price-changes-table">
              <CardHeader className="pb-2 pt-4 px-5">
                <CardTitle className="font-heading text-sm font-bold text-navy-900">
                  Price Changes
                  <span className="text-[10px] font-normal text-slate-400 ml-2">vs previous {periodLabel}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="px-0 pb-2">
                {report.price_changes?.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-100">
                          <th className="text-left font-semibold text-slate-400 uppercase tracking-wider px-5 py-2 text-[10px]">Item</th>
                          <th className="text-right font-semibold text-slate-400 uppercase tracking-wider px-5 py-2 text-[10px]">Previous</th>
                          <th className="text-right font-semibold text-slate-400 uppercase tracking-wider px-5 py-2 text-[10px]">Current</th>
                          <th className="text-right font-semibold text-slate-400 uppercase tracking-wider px-5 py-2 text-[10px]">Change</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.price_changes.map((p, i) => (
                          <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors" data-testid={`price-row-${i}`}>
                            <td className="px-5 py-2.5 font-medium text-navy-900">{p.item}</td>
                            <td className="px-5 py-2.5 text-right text-slate-500">{fmtFull(p.previous_price)}</td>
                            <td className="px-5 py-2.5 text-right font-semibold text-navy-900">{fmtFull(p.current_price)}</td>
                            <td className="px-5 py-2.5 text-right">
                              <span className={`inline-flex items-center gap-0.5 font-semibold ${
                                p.change_pct > 0 ? 'text-red-600' : p.change_pct < 0 ? 'text-emerald-600' : 'text-slate-400'
                              }`}>
                                {p.change_pct > 0 ? <ArrowUpRight className="w-3 h-3" /> : p.change_pct < 0 ? <ArrowDownRight className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
                                {Math.abs(p.change_pct).toFixed(1)}%
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 px-5 py-4">No price changes detected for this period.</p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Top Items Chart */}
          {report.top_items?.length > 0 && (
            <Card className="border border-slate-200/80 shadow-sm" data-testid="top-items-chart">
              <CardHeader className="pb-0 pt-4 px-5">
                <CardTitle className="font-heading text-sm font-bold text-navy-900">Top Purchased Items</CardTitle>
              </CardHeader>
              <CardContent className="px-2 pb-3 pt-2">
                <div className="h-44">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={report.top_items} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                      <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 9, fill: '#64748b' }} interval={0} angle={-20} textAnchor="end" height={40} />
                      <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} width={45} />
                      <Tooltip content={<ChartTooltip />} />
                      <Bar dataKey="total" fill="#0f172a" radius={[4, 4, 0, 0]} barSize={20} name="Spent" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
