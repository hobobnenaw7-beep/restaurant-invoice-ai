import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { toast } from 'sonner';
import {
  Download, FileSpreadsheet, DollarSign, ShoppingCart,
  TrendingUp, TrendingDown, Users2, Wrench, Truck, PieChart,
  Loader2, CalendarDays, ArrowUpRight, ArrowDownRight
} from 'lucide-react';

function fmt(n) { return n != null ? `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '$0.00'; }

const now = new Date();
const DEF_FROM = now.toISOString().slice(0, 8) + '01';
const DEF_TO = now.toISOString().slice(0, 10);

const TABS = [
  { id: 'sales', label: 'Sales', icon: DollarSign },
  { id: 'raw_materials', label: 'Raw Materials', icon: ShoppingCart },
  { id: 'salaries', label: 'Salaries', icon: Users2 },
  { id: 'other_expenses', label: 'Other Expenses', icon: Wrench },
  { id: 'vendor', label: 'Vendors', icon: Truck },
  { id: 'profit', label: 'Profit', icon: PieChart },
];

// ======================== DATE FILTER BAR ========================
function DateFilter({ from, to, onFromChange, onToChange, extra }) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div>
        <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">From Date</Label>
        <Input type="date" className="mt-1 h-9 text-xs w-40" value={from} onChange={(e) => onFromChange(e.target.value)} data-testid="report-date-from" />
      </div>
      <div>
        <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">To Date</Label>
        <Input type="date" className="mt-1 h-9 text-xs w-40" value={to} min={from} onChange={(e) => onToChange(e.target.value)} data-testid="report-date-to" />
      </div>
      {extra}
    </div>
  );
}

// ======================== EXPORT BUTTONS ========================
function ExportButtons({ category, from, to, api, vendor, disabled }) {
  const [dl, setDl] = useState('');
  const doExport = async (format) => {
    setDl(format);
    try {
      const params = { date_from: from, date_to: to, fmt: format };
      if (vendor) params.vendor = vendor;
      const res = await api.get(`/reports/category/${category}/export`, { params, responseType: 'blob' });
      const ext = format === 'pdf' ? 'pdf' : 'xlsx';
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a'); a.href = url;
      a.download = `${category}_report_${from}_${to}.${ext}`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
      toast.success(`${format.toUpperCase()} downloaded`);
    } catch { toast.error('Export failed'); }
    finally { setDl(''); }
  };
  return (
    <div className="flex gap-2">
      <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => doExport('pdf')} disabled={!!dl || disabled} data-testid="export-pdf-btn">
        {dl === 'pdf' ? <Loader2 className="w-3 h-3 animate-spin mr-1.5" /> : <Download className="w-3 h-3 mr-1.5" />} PDF
      </Button>
      <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => doExport('excel')} disabled={!!dl || disabled} data-testid="export-excel-btn">
        {dl === 'excel' ? <Loader2 className="w-3 h-3 animate-spin mr-1.5" /> : <FileSpreadsheet className="w-3 h-3 mr-1.5" />} Excel
      </Button>
    </div>
  );
}

// ======================== KPI BOX ========================
function KPI({ label, value, sub, color = 'bg-teal-600', icon: Icon = DollarSign, testId }) {
  return (
    <Card className="border border-slate-200/80 shadow-sm" data-testid={testId}>
      <CardContent className="p-4">
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${color} mb-3`}>
          <Icon className="w-4 h-4 text-white" />
        </div>
        <p className="font-heading text-xl font-extrabold text-navy-900 tracking-tight tabular-nums">{value}</p>
        <p className="text-[11px] text-slate-400 font-medium mt-0.5">{label}</p>
        {sub && <p className="text-[10px] text-slate-400 mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

// ======================== SALES SECTION ========================
function SalesReport({ api }) {
  const [from, setFrom] = useState(DEF_FROM);
  const [to, setTo] = useState(DEF_TO);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { const res = await api.get('/reports/category/sales', { params: { date_from: from, date_to: to } }); setData(res.data); }
    catch { toast.error('Failed'); } finally { setLoading(false); }
  }, [api, from, to]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5" data-testid="report-sales">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <DateFilter from={from} to={to} onFromChange={setFrom} onToChange={setTo} />
        <ExportButtons category="sales" from={from} to={to} api={api} disabled={!data} />
      </div>
      {loading ? <Skeleton className="h-40 rounded-xl" /> : data && (<>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <KPI label="Total Sales" value={fmt(data.total_sales)} icon={DollarSign} color="bg-teal-600" testId="kpi-total-sales" />
          <KPI label="Sales Records" value={data.record_count} icon={CalendarDays} color="bg-navy-800" testId="kpi-sales-count" sub={`${data.date_from} to ${data.date_to}`} />
          <KPI label="Avg Sales / Entry" value={fmt(data.avg_per_entry)} icon={TrendingUp} color="bg-violet-600" testId="kpi-avg-sales" />
        </div>
        <Card className="border border-slate-200/80 shadow-sm overflow-hidden">
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <Table>
              <TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80 sticky top-0">
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Date</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Total Sales</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-center">Items</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.records.map((r, i) => (
                  <TableRow key={r.id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} data-testid={`sales-report-row-${i}`}>
                    <TableCell className="text-xs tabular-nums">{r.date_from && r.date_to && r.date_from !== r.date_to ? `${r.date_from} → ${r.date_to}` : r.date_from || r.report_date}</TableCell>
                    <TableCell className="text-xs text-right font-semibold tabular-nums text-navy-900">{fmt(r.total_sales)}</TableCell>
                    <TableCell className="text-xs text-center text-slate-500">{r.items?.length || 0}</TableCell>
                  </TableRow>
                ))}
                {!data.records.length && <TableRow><TableCell colSpan={3} className="text-center text-xs text-slate-400 py-8">No sales records in this period</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </Card>
      </>)}
    </div>
  );
}

// ======================== RAW MATERIALS SECTION ========================
function RawMaterialsReport({ api }) {
  const [from, setFrom] = useState(DEF_FROM);
  const [to, setTo] = useState(DEF_TO);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { const res = await api.get('/reports/category/raw_materials', { params: { date_from: from, date_to: to } }); setData(res.data); }
    catch { toast.error('Failed'); } finally { setLoading(false); }
  }, [api, from, to]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5" data-testid="report-raw-materials">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <DateFilter from={from} to={to} onFromChange={setFrom} onToChange={setTo} />
        <ExportButtons category="raw_materials" from={from} to={to} api={api} disabled={!data} />
      </div>
      {loading ? <Skeleton className="h-40 rounded-xl" /> : data && (<>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <KPI label="Total Raw Material Expenses" value={fmt(data.total)} icon={ShoppingCart} color="bg-navy-800" testId="kpi-raw-total" />
          <KPI label="Invoices" value={data.invoice_count} icon={CalendarDays} color="bg-slate-600" testId="kpi-raw-invoices" sub={`${data.items.length} line items`} />
        </div>
        <Card className="border border-slate-200/80 shadow-sm overflow-hidden">
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <Table>
              <TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80 sticky top-0">
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Vendor</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Item</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Date</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Qty</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Price</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Total</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.items.map((it, i) => (
                  <TableRow key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} data-testid={`raw-report-row-${i}`}>
                    <TableCell className="text-xs font-medium text-navy-900">{it.vendor}</TableCell>
                    <TableCell className="text-xs text-slate-600">{it.item}</TableCell>
                    <TableCell className="text-xs tabular-nums text-slate-500">{it.date}</TableCell>
                    <TableCell className="text-xs text-right tabular-nums">{it.quantity} {it.unit}</TableCell>
                    <TableCell className="text-xs text-right tabular-nums">{fmt(it.unit_price)}</TableCell>
                    <TableCell className="text-xs text-right font-semibold tabular-nums text-navy-900">{fmt(it.line_total)}</TableCell>
                  </TableRow>
                ))}
                {!data.items.length && <TableRow><TableCell colSpan={6} className="text-center text-xs text-slate-400 py-8">No raw material purchases in this period</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </Card>
      </>)}
    </div>
  );
}

// ======================== SALARIES SECTION ========================
function SalariesReport({ api }) {
  const [from, setFrom] = useState(DEF_FROM);
  const [to, setTo] = useState(DEF_TO);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { const res = await api.get('/reports/category/salaries', { params: { date_from: from, date_to: to } }); setData(res.data); }
    catch { toast.error('Failed'); } finally { setLoading(false); }
  }, [api, from, to]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5" data-testid="report-salaries">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <DateFilter from={from} to={to} onFromChange={setFrom} onToChange={setTo} />
        <ExportButtons category="salaries" from={from} to={to} api={api} disabled={!data} />
      </div>
      {loading ? <Skeleton className="h-40 rounded-xl" /> : data && (<>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <KPI label="Total Salaries" value={fmt(data.total)} icon={Users2} color="bg-indigo-600" testId="kpi-sal-total" />
          <KPI label="Payments" value={data.record_count} icon={CalendarDays} color="bg-slate-600" testId="kpi-sal-count" sub={`${data.date_from} to ${data.date_to}`} />
        </div>
        <Card className="border border-slate-200/80 shadow-sm overflow-hidden">
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <Table>
              <TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80 sticky top-0">
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Employee</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Position</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Amount</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Date</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Notes</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.records.map((r, i) => (
                  <TableRow key={r.id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} data-testid={`sal-report-row-${i}`}>
                    <TableCell className="text-xs font-medium text-navy-900">{r.employee_name}</TableCell>
                    <TableCell className="text-xs text-slate-500">{r.position || '—'}</TableCell>
                    <TableCell className="text-xs text-right font-semibold tabular-nums text-navy-900">{fmt(r.amount)}</TableCell>
                    <TableCell className="text-xs tabular-nums text-slate-500">{r.payment_date}</TableCell>
                    <TableCell className="text-xs text-slate-400 max-w-[160px] truncate">{r.notes || '—'}</TableCell>
                  </TableRow>
                ))}
                {!data.records.length && <TableRow><TableCell colSpan={5} className="text-center text-xs text-slate-400 py-8">No salary payments in this period</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </Card>
      </>)}
    </div>
  );
}

// ======================== OTHER EXPENSES SECTION ========================
function OtherExpensesReport({ api }) {
  const [from, setFrom] = useState(DEF_FROM);
  const [to, setTo] = useState(DEF_TO);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { const res = await api.get('/reports/category/other_expenses', { params: { date_from: from, date_to: to } }); setData(res.data); }
    catch { toast.error('Failed'); } finally { setLoading(false); }
  }, [api, from, to]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5" data-testid="report-other-expenses">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <DateFilter from={from} to={to} onFromChange={setFrom} onToChange={setTo} />
        <ExportButtons category="other_expenses" from={from} to={to} api={api} disabled={!data} />
      </div>
      {loading ? <Skeleton className="h-40 rounded-xl" /> : data && (<>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <KPI label="Total Other Expenses" value={fmt(data.total)} icon={Wrench} color="bg-amber-600" testId="kpi-oe-total" />
          <KPI label="Records" value={data.record_count} icon={CalendarDays} color="bg-slate-600" testId="kpi-oe-count" sub={data.breakdown?.map(b => `${b.category}: ${fmt(b.total)}`).join(' · ')} />
        </div>
        <Card className="border border-slate-200/80 shadow-sm overflow-hidden">
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <Table>
              <TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80 sticky top-0">
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Title</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Category</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Amount</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Date</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Notes</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.records.map((r, i) => (
                  <TableRow key={r.id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} data-testid={`oe-report-row-${i}`}>
                    <TableCell className="text-xs font-medium text-navy-900">{r.title}</TableCell>
                    <TableCell><Badge variant="outline" className="text-[9px]">{r.category}</Badge></TableCell>
                    <TableCell className="text-xs text-right font-semibold tabular-nums text-navy-900">{fmt(r.amount)}</TableCell>
                    <TableCell className="text-xs tabular-nums text-slate-500">{r.expense_date}</TableCell>
                    <TableCell className="text-xs text-slate-400 max-w-[160px] truncate">{r.notes || '—'}</TableCell>
                  </TableRow>
                ))}
                {!data.records.length && <TableRow><TableCell colSpan={5} className="text-center text-xs text-slate-400 py-8">No other expenses in this period</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </Card>
      </>)}
    </div>
  );
}

// ======================== VENDOR PURCHASE SECTION ========================
function VendorReport({ api }) {
  const [from, setFrom] = useState(DEF_FROM);
  const [to, setTo] = useState(DEF_TO);
  const [vendor, setVendor] = useState('');
  const [vendors, setVendors] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/reports/category/vendor', { params: { date_from: from, date_to: to, vendor } });
      setData(res.data);
      if (!vendors.length && res.data.vendors) setVendors(res.data.vendors);
    } catch { toast.error('Failed'); }
    finally { setLoading(false); }
  }, [api, from, to, vendor]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5" data-testid="report-vendor">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <DateFilter from={from} to={to} onFromChange={setFrom} onToChange={setTo} extra={
          <div>
            <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Vendor</Label>
            <Select value={vendor} onValueChange={setVendor}>
              <SelectTrigger className="mt-1 h-9 w-48 text-xs" data-testid="vendor-select"><SelectValue placeholder="All Vendors" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all" className="text-xs">All Vendors</SelectItem>
                {vendors.map(v => <SelectItem key={v} value={v} className="text-xs">{v}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        } />
        <ExportButtons category="vendor" from={from} to={to} api={api} vendor={vendor === 'all' ? '' : vendor} disabled={!data} />
      </div>
      {loading ? <Skeleton className="h-40 rounded-xl" /> : data && (<>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <KPI label="Total Purchased" value={fmt(data.total)} icon={Truck} color="bg-sky-600" testId="kpi-vendor-total" />
          <KPI label="Invoices" value={data.invoice_count} icon={CalendarDays} color="bg-slate-600" testId="kpi-vendor-invoices" />
          <KPI label="Vendor" value={data.vendor} icon={Truck} color="bg-navy-800" testId="kpi-vendor-name" />
        </div>
        <Card className="border border-slate-200/80 shadow-sm overflow-hidden">
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <Table>
              <TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80 sticky top-0">
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Vendor</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Item</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Date</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Qty</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Price</TableHead>
                <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Total</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.items.map((it, i) => (
                  <TableRow key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} data-testid={`vendor-report-row-${i}`}>
                    <TableCell className="text-xs font-medium text-navy-900">{it.vendor}</TableCell>
                    <TableCell className="text-xs text-slate-600">{it.item}</TableCell>
                    <TableCell className="text-xs tabular-nums text-slate-500">{it.date}</TableCell>
                    <TableCell className="text-xs text-right tabular-nums">{it.quantity}</TableCell>
                    <TableCell className="text-xs text-right tabular-nums">{fmt(it.price)}</TableCell>
                    <TableCell className="text-xs text-right font-semibold tabular-nums text-navy-900">{fmt(it.total)}</TableCell>
                  </TableRow>
                ))}
                {!data.items.length && <TableRow><TableCell colSpan={6} className="text-center text-xs text-slate-400 py-8">No vendor purchases in this period</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </Card>
      </>)}
    </div>
  );
}

// ======================== PROFIT SECTION ========================
function ProfitReport({ api }) {
  const [from, setFrom] = useState(DEF_FROM);
  const [to, setTo] = useState(DEF_TO);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { const res = await api.get('/reports/category/profit', { params: { date_from: from, date_to: to } }); setData(res.data); }
    catch { toast.error('Failed'); } finally { setLoading(false); }
  }, [api, from, to]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5" data-testid="report-profit">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <DateFilter from={from} to={to} onFromChange={setFrom} onToChange={setTo} />
        <ExportButtons category="profit" from={from} to={to} api={api} disabled={!data} />
      </div>
      {loading ? <Skeleton className="h-40 rounded-xl" /> : data && (<>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <KPI label="Total Sales" value={fmt(data.total_sales)} icon={DollarSign} color="bg-teal-600" testId="kpi-profit-sales" />
          <KPI label="Total Expenses" value={fmt(data.total_expenses)} icon={ShoppingCart} color="bg-red-500" testId="kpi-profit-expenses" />
          <KPI label="Net Profit" value={fmt(data.net_profit)} icon={data.net_profit >= 0 ? TrendingUp : TrendingDown} color={data.net_profit >= 0 ? 'bg-emerald-600' : 'bg-red-600'} testId="kpi-net-profit" sub={`Net Margin: ${data.net_margin_pct}%`} />
        </div>

        <Card className="border border-slate-200/80 shadow-sm" data-testid="profit-breakdown-card">
          <CardHeader className="pb-3 pt-5 px-6">
            <CardTitle className="font-heading text-sm font-bold text-navy-900">Profit Breakdown</CardTitle>
          </CardHeader>
          <CardContent className="px-6 pb-5">
            <div className="rounded-xl border border-slate-200 overflow-hidden">
              <table className="w-full text-sm" data-testid="profit-breakdown-table">
                <thead>
                  <tr className="bg-slate-50/80">
                    <th className="text-left text-[10px] font-bold text-slate-500 uppercase tracking-wider px-5 py-2.5">Category</th>
                    <th className="text-right text-[10px] font-bold text-slate-500 uppercase tracking-wider px-5 py-2.5">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-100 bg-teal-50/30" data-testid="pb-row-sales">
                    <td className="px-5 py-3 font-semibold text-navy-900">Total Sales (Revenue)</td>
                    <td className="px-5 py-3 text-right font-bold text-navy-900 tabular-nums">{fmt(data.total_sales)}</td>
                  </tr>
                  <tr className="border-t border-slate-100 bg-slate-50/30">
                    <td className="px-5 py-2 font-semibold text-slate-500 text-xs uppercase tracking-wider" colSpan={2}>Expenses Breakdown</td>
                  </tr>
                  <tr className="border-t border-slate-50" data-testid="pb-row-raw">
                    <td className="px-5 py-2.5 pl-8 text-slate-600">Raw Materials</td>
                    <td className="px-5 py-2.5 text-right tabular-nums text-slate-700">{fmt(data.raw_materials)}</td>
                  </tr>
                  <tr className="border-t border-slate-50" data-testid="pb-row-salaries">
                    <td className="px-5 py-2.5 pl-8 text-slate-600">Salaries</td>
                    <td className="px-5 py-2.5 text-right tabular-nums text-slate-700">{fmt(data.salaries)}</td>
                  </tr>
                  <tr className="border-t border-slate-50" data-testid="pb-row-other">
                    <td className="px-5 py-2.5 pl-8 text-slate-600">Other Expenses</td>
                    <td className="px-5 py-2.5 text-right tabular-nums text-slate-700">{fmt(data.other_expenses)}</td>
                  </tr>
                  <tr className="border-t-2 border-slate-200 bg-slate-50/60" data-testid="pb-row-total-exp">
                    <td className="px-5 py-3 font-bold text-navy-900">Total Expenses</td>
                    <td className="px-5 py-3 text-right font-bold text-navy-900 tabular-nums">{fmt(data.total_expenses)}</td>
                  </tr>
                  <tr className={`border-t-2 border-slate-300 ${data.net_profit >= 0 ? 'bg-emerald-50/60' : 'bg-red-50/60'}`} data-testid="pb-row-net-profit">
                    <td className="px-5 py-3.5 font-bold text-navy-900 text-base">Net Profit</td>
                    <td className={`px-5 py-3.5 text-right font-extrabold text-base tabular-nums ${data.net_profit >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>{fmt(data.net_profit)}</td>
                  </tr>
                  <tr className="border-t border-slate-100" data-testid="pb-row-margin">
                    <td className="px-5 py-2.5 font-semibold text-slate-500">Net Margin</td>
                    <td className={`px-5 py-2.5 text-right font-bold tabular-nums ${data.net_margin_pct >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>{data.net_margin_pct}%</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </>)}
    </div>
  );
}

// ======================== MAIN PAGE ========================
export default function ReportsPage() {
  const { api } = useAuth();
  const [tab, setTab] = useState('sales');

  return (
    <div className="space-y-6 max-w-[1400px]" data-testid="reports-page">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight">Financial Reports</h1>
        <p className="text-xs text-slate-400 mt-0.5">Organized by category for accounting and tax preparation</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-slate-100 h-9 flex-wrap" data-testid="report-category-tabs">
          {TABS.map(t => (
            <TabsTrigger key={t.id} value={t.id} className="text-xs font-semibold px-3 gap-1.5" data-testid={`tab-${t.id}`}>
              <t.icon className="w-3.5 h-3.5" /> {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {tab === 'sales' && <SalesReport api={api} />}
      {tab === 'raw_materials' && <RawMaterialsReport api={api} />}
      {tab === 'salaries' && <SalariesReport api={api} />}
      {tab === 'other_expenses' && <OtherExpensesReport api={api} />}
      {tab === 'vendor' && <VendorReport api={api} />}
      {tab === 'profit' && <ProfitReport api={api} />}
    </div>
  );
}
