import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import { ArrowLeft, Search, Eye, Trash2, Package, FileText, Phone, User, DollarSign, Calendar, Hash, MapPin } from 'lucide-react';
import { ConfirmDeleteDialog } from '@/components/ConfirmDeleteDialog';

function fmt(n) { return `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }

export default function VendorDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { api } = useAuth();
  const [vendor, setVendor] = useState(null);
  const [purchases, setPurchases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [selected, setSelected] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, id: null });

  const loadVendor = useCallback(async () => {
    try {
      const res = await api.get(`/suppliers/${id}/detail`);
      setVendor(res.data);
    } catch {
      toast.error('Vendor not found');
      navigate('/vendors');
    }
  }, [api, id, navigate]);

  const loadPurchases = useCallback(async () => {
    try {
      const params = {};
      if (search) params.search = search;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await api.get(`/suppliers/${id}/purchases`, { params });
      setPurchases(res.data);
    } catch { toast.error('Failed to load purchases'); }
  }, [api, id, search, dateFrom, dateTo]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadVendor(), loadPurchases()]);
    setLoading(false);
  }, [loadVendor, loadPurchases]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const requestDelete = (pid) => setDeleteConfirm({ open: true, id: pid });
  const handleDeleteConfirm = async () => {
    const { id: pid } = deleteConfirm;
    setDeleteConfirm({ open: false, id: null });
    try {
      await api.delete(`/purchases/${pid}`);
      toast.success('Record deleted');
      loadAll();
    } catch { toast.error('Delete failed'); }
  };
  const cancelDelete = () => setDeleteConfirm({ open: false, id: null });

  if (loading && !vendor) {
    return (
      <div className="space-y-6 max-w-[1400px]" data-testid="vendor-detail-loading">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">{[1,2,3,4].map(i => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  if (!vendor) return null;

  const summaryCards = [
    { label: 'Total Spent', value: fmt(vendor.total_spending), icon: DollarSign, color: 'bg-teal-100 text-teal-700' },
    { label: 'Invoices', value: vendor.invoice_count || 0, icon: FileText, color: 'bg-indigo-100 text-indigo-700' },
    { label: 'Contact', value: vendor.contact_person || '—', icon: User, color: 'bg-amber-100 text-amber-700' },
    { label: 'Phone', value: vendor.phone || '—', icon: Phone, color: 'bg-slate-100 text-slate-700' },
  ];

  return (
    <div className="space-y-6 max-w-[1400px]" data-testid="vendor-detail-page">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" className="h-9 w-9 rounded-lg" onClick={() => navigate('/vendors')} data-testid="back-to-vendors">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-navy-900 text-white flex items-center justify-center text-sm font-bold flex-shrink-0">
              {vendor.name?.charAt(0)?.toUpperCase()}
            </div>
            <div>
              <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight truncate" data-testid="vendor-name">{vendor.name}</h1>
              {(vendor.email || vendor.address) && (
                <p className="text-xs text-slate-400 flex items-center gap-2 mt-0.5">
                  {vendor.email && <span>{vendor.email}</span>}
                  {vendor.address && <span className="flex items-center gap-0.5"><MapPin className="w-3 h-3" />{vendor.address}</span>}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {summaryCards.map((c, i) => (
          <Card key={i} className="border border-slate-100 shadow-sm">
            <CardContent className="p-4">
              <div className="flex items-center gap-2.5 mb-2">
                <div className={`w-8 h-8 rounded-lg ${c.color} flex items-center justify-center`}>
                  <c.icon className="w-4 h-4" />
                </div>
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{c.label}</span>
              </div>
              <p className="text-lg font-bold text-navy-900 truncate" data-testid={`vendor-${c.label.toLowerCase().replace(/\s/g, '-')}`}>{c.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[180px] max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input className="pl-9 h-9 text-sm" placeholder="Search invoice #..." value={search} onChange={e => setSearch(e.target.value)} data-testid="vendor-search-invoice" />
        </div>
        <Input type="date" className="h-9 text-sm w-[150px]" value={dateFrom} onChange={e => setDateFrom(e.target.value)} data-testid="vendor-date-from" />
        <Input type="date" className="h-9 text-sm w-[150px]" value={dateTo} onChange={e => setDateTo(e.target.value)} data-testid="vendor-date-to" />
        {(search || dateFrom || dateTo) && (
          <Button variant="ghost" size="sm" className="h-9 text-xs text-slate-500" onClick={() => { setSearch(''); setDateFrom(''); setDateTo(''); }} data-testid="vendor-clear-filters">
            Clear
          </Button>
        )}
      </div>

      {/* Purchase List */}
      <Card className="border border-slate-100 shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 bg-slate-50/60">
          <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            Purchase Records <Badge variant="secondary" className="ml-2 text-[10px]">{purchases.length}</Badge>
          </h2>
        </div>
        {purchases.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-14 text-center">
            <Package className="w-8 h-8 text-slate-200 mb-3" />
            <p className="text-sm font-semibold text-navy-900">No purchase records</p>
            <p className="text-xs text-slate-400 mt-1">No invoices match your filters for this vendor.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50/40 hover:bg-slate-50/40">
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Date</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Invoice #</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-center">Items</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Total</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-center">Status</TableHead>
                  <TableHead className="w-20" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {purchases.map((p, i) => (
                  <TableRow key={p.id} className={`transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/30'} hover:bg-teal-50/30`} data-testid={`purchase-row-${i}`}>
                    <TableCell className="text-sm text-navy-900 tabular-nums">{p.invoice_date}</TableCell>
                    <TableCell>
                      {p.invoice_number ? (
                        <Badge variant="outline" className="text-[11px] font-mono px-2">{p.invoice_number}</Badge>
                      ) : <span className="text-xs text-slate-300">—</span>}
                    </TableCell>
                    <TableCell className="text-sm text-slate-500 text-center">{p.items?.length || 0}</TableCell>
                    <TableCell className="text-sm text-right font-bold text-navy-900 tabular-nums">{fmt(p.total)}</TableCell>
                    <TableCell className="text-center">
                      <Badge className={`text-[9px] ${p.approval_status === 'approved' ? 'bg-emerald-100 text-emerald-700' : p.approval_status === 'pending' ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}>
                        {p.approval_status || 'approved'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-0.5">
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setSelected(p)} data-testid={`view-purchase-${i}`}>
                          <Eye className="w-3.5 h-3.5 text-slate-500" />
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => requestDelete(p.id)} data-testid={`delete-purchase-${i}`}>
                          <Trash2 className="w-3.5 h-3.5 text-red-400" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {purchases.length > 0 && (
          <div className="px-4 py-2.5 border-t border-slate-100 bg-slate-50/40 flex justify-between items-center">
            <span className="text-xs text-slate-400">{purchases.length} record{purchases.length !== 1 ? 's' : ''}</span>
            <span className="text-sm font-bold text-navy-900">Total: {fmt(purchases.reduce((s, p) => s + (p.total || 0), 0))}</span>
          </div>
        )}
      </Card>

      {/* Purchase Detail Modal */}
      <Dialog open={!!selected} onOpenChange={(open) => { if (!open) setSelected(null); }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading text-lg flex items-center gap-2">
              <FileText className="w-5 h-5 text-teal-600" />
              Purchase Details
            </DialogTitle>
          </DialogHeader>
          {selected && (
            <div className="space-y-4 pt-2" data-testid="purchase-detail-modal">
              <div className="grid grid-cols-2 gap-3">
                <InfoBlock icon={User} label="Vendor" value={selected.supplier_name} />
                <InfoBlock icon={Calendar} label="Date" value={selected.invoice_date} />
                <InfoBlock icon={Hash} label="Invoice #" value={selected.invoice_number || '—'} />
                <InfoBlock icon={FileText} label="Status" value={selected.approval_status || 'approved'} />
              </div>

              {/* Line Items */}
              <div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Line Items</p>
                <div className="border border-slate-100 rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50/80">
                      <tr>
                        <th className="text-left px-3 py-2 text-[10px] font-bold text-slate-500 uppercase">Item</th>
                        <th className="text-right px-3 py-2 text-[10px] font-bold text-slate-500 uppercase">Qty</th>
                        <th className="text-right px-3 py-2 text-[10px] font-bold text-slate-500 uppercase">Price</th>
                        <th className="text-right px-3 py-2 text-[10px] font-bold text-slate-500 uppercase">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(selected.items || []).map((it, idx) => {
                        const nav = it.canonical_item_id
                          ? () => window.location.assign(`/items?highlight=${encodeURIComponent(it.canonical_item_id)}`)
                          : null;
                        return (
                        <tr
                          key={idx}
                          className={`${idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/30'} ${nav ? 'cursor-pointer hover:bg-teal-50/40' : ''}`}
                          onClick={nav || undefined}
                          data-testid={`invoice-item-row-${idx}`}
                          data-canonical-id={it.canonical_item_id || ''}
                        >
                          <td className="px-3 py-1.5 font-medium text-navy-900" data-testid={`invoice-item-name-${idx}`}>
                            {it.display_name || it.canonical_name || it.raw_name}
                          </td>
                          <td className="px-3 py-1.5 text-right text-slate-500 tabular-nums">{it.quantity} {it.unit}</td>
                          <td className="px-3 py-1.5 text-right text-slate-500 tabular-nums">{fmt(it.unit_price)}</td>
                          <td className="px-3 py-1.5 text-right font-semibold text-navy-900 tabular-nums">{fmt(it.total)}</td>
                        </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Totals */}
              <div className="bg-slate-50 rounded-lg p-3 space-y-1.5">
                <div className="flex justify-between text-sm"><span className="text-slate-500">Subtotal</span><span className="font-medium tabular-nums">{fmt(selected.subtotal)}</span></div>
                <div className="flex justify-between text-sm"><span className="text-slate-500">Tax</span><span className="font-medium tabular-nums">{fmt(selected.tax)}</span></div>
                <div className="flex justify-between text-sm font-bold border-t border-slate-200 pt-1.5 mt-1.5"><span className="text-navy-900">Total</span><span className="text-navy-900 tabular-nums">{fmt(selected.total)}</span></div>
              </div>

              {selected.created_by_name && (
                <p className="text-[11px] text-slate-400">Created by: {selected.created_by_name} on {selected.created_at?.split('T')[0]}</p>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
      <ConfirmDeleteDialog open={deleteConfirm.open} onClose={cancelDelete} onConfirm={handleDeleteConfirm} message="Are you sure you want to delete this purchase record?" />
    </div>
  );
}

function InfoBlock({ icon: Icon, label, value }) {
  return (
    <div className="bg-slate-50 rounded-lg p-2.5">
      <div className="flex items-center gap-1.5 mb-0.5">
        <Icon className="w-3 h-3 text-slate-400" />
        <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">{label}</span>
      </div>
      <p className="text-sm font-semibold text-navy-900 truncate">{value}</p>
    </div>
  );
}
