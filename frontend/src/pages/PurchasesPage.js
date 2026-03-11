import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import { Search, Loader2, Eye, Trash2, ChevronUp, ChevronDown, ShoppingCart } from 'lucide-react';

function fmt(n) { return n != null ? `$${Number(n).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : '$0.00'; }

function TableSkeleton() {
  return <div className="p-6 space-y-3">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-12 w-full rounded-lg" />)}</div>;
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4"><ShoppingCart className="w-6 h-6 text-slate-300" /></div>
      <h3 className="font-heading text-base font-bold text-navy-900 mb-1">No purchases found</h3>
      <p className="text-sm text-slate-400 max-w-xs">Upload an invoice or adjust your filters to see purchases here.</p>
    </div>
  );
}

export default function PurchasesPage() {
  const { api } = useAuth();
  const [purchases, setPurchases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sortBy, setSortBy] = useState('invoice_date');
  const [sortOrder, setSortOrder] = useState('desc');
  const [selected, setSelected] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get('/purchases', { params: { search, date_from: dateFrom, date_to: dateTo, sort_by: sortBy, sort_order: sortOrder } });
      setPurchases(res.data);
    } catch { toast.error('Failed to load'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [search, dateFrom, dateTo, sortBy, sortOrder]); // eslint-disable-line

  const toggleSort = (field) => {
    if (sortBy === field) setSortOrder(o => o === 'desc' ? 'asc' : 'desc');
    else { setSortBy(field); setSortOrder('desc'); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this purchase?')) return;
    try { await api.delete(`/purchases/${id}`); toast.success('Deleted'); load(); } catch { toast.error('Failed'); }
  };

  const SI = ({ field }) => sortBy === field ? (sortOrder === 'desc' ? <ChevronDown className="w-3 h-3 inline ml-0.5" /> : <ChevronUp className="w-3 h-3 inline ml-0.5" />) : null;

  return (
    <div className="space-y-6 max-w-[1400px]" data-testid="purchases-page">
      <div>
        <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-navy-900 tracking-tight">Purchases</h1>
        <p className="text-sm text-slate-400 mt-1">All purchase invoices</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input className="pl-9 h-10" placeholder="Search supplier or invoice #..." value={search} onChange={(e) => setSearch(e.target.value)} data-testid="search-purchases" />
        </div>
        <Input type="date" className="w-40 h-10" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} data-testid="date-from" />
        <Input type="date" className="w-40 h-10" value={dateTo} onChange={(e) => setDateTo(e.target.value)} data-testid="date-to" />
      </div>

      <Card className="border border-slate-100 shadow-sm overflow-hidden">
        {loading ? <TableSkeleton /> : purchases.length === 0 ? <EmptyState /> : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                  <TableHead className="cursor-pointer text-[11px] font-bold text-slate-500 uppercase tracking-wider" onClick={() => toggleSort('invoice_date')}>Date <SI field="invoice_date" /></TableHead>
                  <TableHead className="cursor-pointer text-[11px] font-bold text-slate-500 uppercase tracking-wider" onClick={() => toggleSort('supplier_name')}>Supplier <SI field="supplier_name" /></TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Invoice #</TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider text-center">Items</TableHead>
                  <TableHead className="cursor-pointer text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right" onClick={() => toggleSort('total')}>Total <SI field="total" /></TableHead>
                  <TableHead className="w-20" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {purchases.map((p, i) => (
                  <TableRow key={p.id} className={`transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} hover:bg-teal-50/30`}>
                    <TableCell className="text-sm tabular-nums text-slate-600">{p.invoice_date}</TableCell>
                    <TableCell className="text-sm font-semibold text-navy-900">{p.supplier_name}</TableCell>
                    <TableCell><Badge variant="outline" className="text-[11px] font-mono">{p.invoice_number}</Badge></TableCell>
                    <TableCell className="text-sm text-center text-slate-500">{p.items?.length || 0}</TableCell>
                    <TableCell className="text-sm text-right font-bold text-navy-900 tabular-nums">{fmt(p.total)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-0.5">
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setSelected(p)} data-testid={`view-purchase-${p.id}`}><Eye className="w-3.5 h-3.5 text-slate-500" /></Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => handleDelete(p.id)}><Trash2 className="w-3.5 h-3.5 text-red-400" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="px-4 py-3 border-t border-slate-100 bg-slate-50/50">
              <p className="text-xs text-slate-400">{purchases.length} purchase{purchases.length !== 1 ? 's' : ''} &middot; Total: <span className="font-bold text-navy-900">{fmt(purchases.reduce((s, p) => s + (p.total || 0), 0))}</span></p>
            </div>
          </div>
        )}
      </Card>

      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="font-heading text-lg">Purchase Details</DialogTitle></DialogHeader>
          {selected && (
            <div className="space-y-5">
              <div className="grid grid-cols-3 gap-4">
                {[['Supplier', selected.supplier_name], ['Invoice #', selected.invoice_number], ['Date', selected.invoice_date]].map(([l, v]) => (
                  <div key={l}><p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">{l}</p><p className="text-sm font-semibold text-navy-900 mt-0.5">{v}</p></div>
                ))}
              </div>
              <Separator />
              <Table>
                <TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80"><TableHead className="text-[11px] font-bold text-slate-500 uppercase">Item</TableHead><TableHead className="text-[11px] font-bold text-slate-500 uppercase text-right">Qty</TableHead><TableHead className="text-[11px] font-bold text-slate-500 uppercase">Unit</TableHead><TableHead className="text-[11px] font-bold text-slate-500 uppercase text-right">Price</TableHead><TableHead className="text-[11px] font-bold text-slate-500 uppercase text-right">Total</TableHead></TableRow></TableHeader>
                <TableBody>
                  {(selected.items || []).map((it, i) => (
                    <TableRow key={i} className={i % 2 === 0 ? '' : 'bg-slate-50/40'}>
                      <TableCell className="text-sm font-medium">{it.raw_name}</TableCell>
                      <TableCell className="text-sm text-right tabular-nums">{it.quantity}</TableCell>
                      <TableCell className="text-sm text-slate-500">{it.unit}</TableCell>
                      <TableCell className="text-sm text-right tabular-nums">{fmt(it.unit_price)}</TableCell>
                      <TableCell className="text-sm text-right font-semibold tabular-nums">{fmt(it.total)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="flex justify-end">
                <div className="text-right space-y-1 min-w-[200px]">
                  <div className="flex justify-between text-sm"><span className="text-slate-500">Subtotal</span><span className="tabular-nums">{fmt(selected.subtotal)}</span></div>
                  <div className="flex justify-between text-sm"><span className="text-slate-500">Tax</span><span className="tabular-nums">{fmt(selected.tax)}</span></div>
                  <Separator className="my-1" />
                  <div className="flex justify-between text-base font-bold"><span>Total</span><span className="tabular-nums">{fmt(selected.total)}</span></div>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
