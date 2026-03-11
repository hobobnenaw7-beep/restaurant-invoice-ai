import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import { Search, Loader2, Eye, Trash2, ChevronUp, ChevronDown, DollarSign } from 'lucide-react';

function fmt(n) { return n != null ? `$${Number(n).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : '$0.00'; }

export default function SalesPage() {
  const { api } = useAuth();
  const [sales, setSales] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sortBy, setSortBy] = useState('report_date');
  const [sortOrder, setSortOrder] = useState('desc');
  const [selected, setSelected] = useState(null);

  const load = async () => {
    setLoading(true);
    try { const res = await api.get('/sales', { params: { date_from: dateFrom, date_to: dateTo, sort_by: sortBy, sort_order: sortOrder } }); setSales(res.data); }
    catch { toast.error('Failed to load sales'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [dateFrom, dateTo, sortBy, sortOrder]); // eslint-disable-line

  const toggleSort = (field) => {
    if (sortBy === field) setSortOrder(o => o === 'desc' ? 'asc' : 'desc');
    else { setSortBy(field); setSortOrder('desc'); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this sales report?')) return;
    try { await api.delete(`/sales/${id}`); toast.success('Deleted'); load(); } catch { toast.error('Failed'); }
  };

  const SI = ({ field }) => sortBy === field ? (sortOrder === 'desc' ? <ChevronDown className="w-3 h-3 inline ml-0.5" /> : <ChevronUp className="w-3 h-3 inline ml-0.5" />) : null;

  return (
    <div className="space-y-6 max-w-[1400px]" data-testid="sales-page">
      <div>
        <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-navy-900 tracking-tight">Sales</h1>
        <p className="text-sm text-slate-400 mt-1">Daily sales reports</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1" />
        <Input type="date" className="w-40 h-10" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} placeholder="From" />
        <Input type="date" className="w-40 h-10" value={dateTo} onChange={(e) => setDateTo(e.target.value)} placeholder="To" />
      </div>

      <Card className="border border-slate-100 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-6 space-y-3">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-12 w-full rounded-lg" />)}</div>
        ) : sales.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4"><DollarSign className="w-6 h-6 text-slate-300" /></div>
            <h3 className="font-heading text-base font-bold text-navy-900 mb-1">No sales found</h3>
            <p className="text-sm text-slate-400">Upload a sales report or adjust filters.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                  <TableHead className="cursor-pointer text-[11px] font-bold text-slate-500 uppercase tracking-wider" onClick={() => toggleSort('report_date')}>Date <SI field="report_date" /></TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider text-center">Menu Items</TableHead>
                  <TableHead className="cursor-pointer text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right" onClick={() => toggleSort('total_sales')}>Total Revenue <SI field="total_sales" /></TableHead>
                  <TableHead className="w-20" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {sales.map((s, i) => (
                  <TableRow key={s.id} className={`transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} hover:bg-teal-50/30`}>
                    <TableCell className="text-sm font-medium tabular-nums text-slate-600">{s.report_date}</TableCell>
                    <TableCell className="text-sm text-center text-slate-500">{s.items?.length || 0}</TableCell>
                    <TableCell className="text-sm text-right font-bold text-teal-700 tabular-nums">{fmt(s.total_sales)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-0.5">
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setSelected(s)}><Eye className="w-3.5 h-3.5 text-slate-500" /></Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => handleDelete(s.id)}><Trash2 className="w-3.5 h-3.5 text-red-400" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="px-4 py-3 border-t border-slate-100 bg-slate-50/50">
              <p className="text-xs text-slate-400">{sales.length} report{sales.length !== 1 ? 's' : ''} &middot; Total: <span className="font-bold text-teal-700">{fmt(sales.reduce((s, r) => s + (r.total_sales || 0), 0))}</span></p>
            </div>
          </div>
        )}
      </Card>

      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="font-heading text-lg">Sales Report</DialogTitle></DialogHeader>
          {selected && (
            <div className="space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <div><p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Date</p><p className="text-sm font-semibold text-navy-900 mt-0.5">{selected.report_date}</p></div>
                <div><p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Total Revenue</p><p className="text-lg font-bold text-teal-700 mt-0.5">{fmt(selected.total_sales)}</p></div>
              </div>
              {selected.items?.length > 0 && (<>
                <Separator />
                <Table>
                  <TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80"><TableHead className="text-[11px] font-bold text-slate-500 uppercase">Menu Item</TableHead><TableHead className="text-[11px] font-bold text-slate-500 uppercase text-right">Qty</TableHead><TableHead className="text-[11px] font-bold text-slate-500 uppercase text-right">Revenue</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {selected.items.map((it, i) => (
                      <TableRow key={i} className={i % 2 === 0 ? '' : 'bg-slate-50/40'}>
                        <TableCell className="text-sm font-medium">{it.menu_item}</TableCell>
                        <TableCell className="text-sm text-right tabular-nums">{it.quantity}</TableCell>
                        <TableCell className="text-sm text-right font-semibold tabular-nums">{fmt(it.revenue)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </>)}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
