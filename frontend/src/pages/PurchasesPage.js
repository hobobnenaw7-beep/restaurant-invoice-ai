import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import {
  Search, Loader2, Eye, Trash2, ChevronUp, ChevronDown,
  ShoppingCart, Plus, Upload, Sparkles, FileText, X,
  Camera, Image as ImageIcon, FileUp
} from 'lucide-react';

function fmt(n) { return n != null ? `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '$0.00'; }

const emptyPurchase = () => ({
  supplier_name: '', invoice_number: '', invoice_date: new Date().toISOString().split('T')[0],
  items: [{ raw_name: '', quantity: 1, unit: 'kg', unit_price: 0, total: 0 }],
  subtotal: 0, tax: 0, total: 0,
});

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

  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState(emptyPurchase());
  const [saving, setSaving] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadPreview, setUploadPreview] = useState(null);
  const fileImageRef = useRef(null);
  const filePdfRef = useRef(null);
  const fileCameraRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/purchases', { params: { search, date_from: dateFrom, date_to: dateTo, sort_by: sortBy, sort_order: sortOrder } });
      setPurchases(res.data);
    } catch { toast.error('Failed to load'); }
    finally { setLoading(false); }
  }, [api, search, dateFrom, dateTo, sortBy, sortOrder]);

  useEffect(() => { load(); }, [load]);

  const toggleSort = (field) => {
    if (sortBy === field) setSortOrder(o => o === 'desc' ? 'asc' : 'desc');
    else { setSortBy(field); setSortOrder('desc'); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this purchase?')) return;
    try { await api.delete(`/purchases/${id}`); toast.success('Deleted'); load(); } catch { toast.error('Failed'); }
  };

  const updateField = (key, val) => setForm(f => ({ ...f, [key]: val }));
  const updateItem = (idx, key, val) => {
    setForm(f => {
      const items = [...f.items];
      items[idx] = { ...items[idx], [key]: val };
      if (key === 'quantity' || key === 'unit_price') {
        items[idx].total = parseFloat(items[idx].quantity || 0) * parseFloat(items[idx].unit_price || 0);
      }
      return { ...f, items };
    });
  };
  const removeItem = (idx) => setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) }));
  const addItem = () => setForm(f => ({ ...f, items: [...f.items, { raw_name: '', quantity: 1, unit: 'kg', unit_price: 0, total: 0 }] }));

  const openAddForm = () => {
    setForm(emptyPurchase());
    setUploadFile(null);
    setUploadPreview(null);
    setShowAdd(true);
  };

  const handleFileSelect = (file) => {
    if (!file) return;
    setUploadFile(file);
    if (file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = (e) => setUploadPreview(e.target.result);
      reader.readAsDataURL(file);
    } else {
      setUploadPreview(null);
    }
  };

  const clearFile = () => {
    setUploadFile(null);
    setUploadPreview(null);
  };

  const handleExtract = async () => {
    if (!uploadFile) return;
    setExtracting(true);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('document_type', 'purchase_invoice');
      const res = await api.post('/upload/extract', formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 });
      const d = res.data.extracted_data;
      setForm({
        supplier_name: d.supplier_name || '', invoice_number: d.invoice_number || '',
        invoice_date: d.invoice_date || new Date().toISOString().split('T')[0],
        items: (d.items || []).map(it => ({ raw_name: it.raw_name || '', quantity: parseFloat(it.quantity) || 0, unit: it.unit || '', unit_price: parseFloat(it.unit_price) || 0, total: parseFloat(it.total) || 0 })),
        subtotal: parseFloat(d.subtotal) || 0, tax: parseFloat(d.tax) || 0, total: parseFloat(d.total) || 0,
      });
      toast.success('Invoice data extracted! Review the fields below and save.');
    } catch (err) {
      toast.error('Extraction failed: ' + (err.response?.data?.detail || 'Try again.'));
    } finally { setExtracting(false); }
  };

  const handleSave = async () => {
    if (!form.supplier_name.trim()) { toast.error('Supplier name is required'); return; }
    setSaving(true);
    try {
      await api.post('/purchases', form);
      toast.success('Purchase saved');
      setShowAdd(false);
      load();
    } catch (err) {
      toast.error('Save failed: ' + (err.response?.data?.detail || ''));
    } finally { setSaving(false); }
  };

  const SI = ({ field }) => sortBy === field ? (sortOrder === 'desc' ? <ChevronDown className="w-3 h-3 inline ml-0.5" /> : <ChevronUp className="w-3 h-3 inline ml-0.5" />) : null;

  return (
    <div className="space-y-6 max-w-[1400px]" data-testid="purchases-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight">Purchases</h1>
          <p className="text-xs text-slate-400 mt-0.5">All purchase invoices</p>
        </div>
        <Button onClick={openAddForm} className="bg-navy-900 hover:bg-navy-800 text-white h-9 text-xs" data-testid="add-purchase-btn">
          <Plus className="w-3.5 h-3.5 mr-1.5" /> Add Purchase
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input className="pl-9 h-9 text-sm" placeholder="Search supplier or invoice #..." value={search} onChange={(e) => setSearch(e.target.value)} data-testid="search-purchases" />
        </div>
        <Input type="date" className="w-40 h-9 text-xs" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} data-testid="date-from" />
        <Input type="date" className="w-40 h-9 text-xs" value={dateTo} onChange={(e) => setDateTo(e.target.value)} data-testid="date-to" />
      </div>

      {/* Table */}
      <Card className="border border-slate-200/80 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-5 space-y-3">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-11 w-full rounded-lg" />)}</div>
        ) : purchases.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4"><ShoppingCart className="w-6 h-6 text-slate-300" /></div>
            <h3 className="font-heading text-base font-bold text-navy-900 mb-1">No purchases found</h3>
            <p className="text-sm text-slate-400 max-w-xs mb-4">Add a purchase or upload an invoice to get started.</p>
            <Button onClick={openAddForm} variant="outline" size="sm" className="text-xs" data-testid="empty-add-purchase-btn">
              <Plus className="w-3.5 h-3.5 mr-1" /> Add Purchase
            </Button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                  <TableHead className="cursor-pointer text-[10px] font-bold text-slate-500 uppercase tracking-wider" onClick={() => toggleSort('invoice_date')}>Date <SI field="invoice_date" /></TableHead>
                  <TableHead className="cursor-pointer text-[10px] font-bold text-slate-500 uppercase tracking-wider" onClick={() => toggleSort('supplier_name')}>Supplier <SI field="supplier_name" /></TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Invoice #</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-center">Items</TableHead>
                  <TableHead className="cursor-pointer text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right" onClick={() => toggleSort('total')}>Total <SI field="total" /></TableHead>
                  <TableHead className="w-20" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {purchases.map((p, i) => (
                  <TableRow key={p.id} className={`transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} hover:bg-teal-50/30`} data-testid={`purchase-row-${i}`}>
                    <TableCell className="text-xs tabular-nums text-slate-600">{p.invoice_date}</TableCell>
                    <TableCell className="text-xs font-semibold text-navy-900">{p.supplier_name}</TableCell>
                    <TableCell><Badge variant="outline" className="text-[10px] font-mono">{p.invoice_number}</Badge></TableCell>
                    <TableCell className="text-xs text-center text-slate-500">{p.items?.length || 0}</TableCell>
                    <TableCell className="text-xs text-right font-bold text-navy-900 tabular-nums">{fmt(p.total)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-0.5">
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setSelected(p)} data-testid={`view-purchase-${i}`}><Eye className="w-3.5 h-3.5 text-slate-500" /></Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => handleDelete(p.id)} data-testid={`delete-purchase-${i}`}><Trash2 className="w-3.5 h-3.5 text-red-400" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="px-4 py-2.5 border-t border-slate-100 bg-slate-50/50">
              <p className="text-[11px] text-slate-400">{purchases.length} purchase{purchases.length !== 1 ? 's' : ''} &middot; Total: <span className="font-bold text-navy-900">{fmt(purchases.reduce((s, p) => s + (p.total || 0), 0))}</span></p>
            </div>
          </div>
        )}
      </Card>

      {/* View Detail Dialog */}
      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="font-heading text-lg">Purchase Details</DialogTitle></DialogHeader>
          {selected && (
            <div className="space-y-5">
              <div className="grid grid-cols-3 gap-4">
                {[['Supplier', selected.supplier_name], ['Invoice #', selected.invoice_number], ['Date', selected.invoice_date]].map(([l, v]) => (
                  <div key={l}><p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{l}</p><p className="text-sm font-semibold text-navy-900 mt-0.5">{v}</p></div>
                ))}
              </div>
              <Separator />
              <Table>
                <TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase">Item</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right">Qty</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase">Unit</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right">Price</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right">Total</TableHead>
                </TableRow></TableHeader>
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

      {/* Add Purchase Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading text-lg">Add Purchase</DialogTitle>
          </DialogHeader>

          {/* Upload section — multi-option */}
          <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/50 p-4" data-testid="purchase-upload-zone">
            {uploadFile ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-9 h-9 rounded-lg bg-teal-50 border border-teal-200 flex items-center justify-center flex-shrink-0">
                      {uploadFile.type.startsWith('image/') ? <ImageIcon className="w-4 h-4 text-teal-600" /> : <FileText className="w-4 h-4 text-teal-600" />}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-navy-900 truncate">{uploadFile.name}</p>
                      <p className="text-[10px] text-slate-400">{(uploadFile.size / 1024).toFixed(0)} KB &middot; {uploadFile.type.split('/')[1]?.toUpperCase()}</p>
                    </div>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    <Button size="sm" variant="outline" className="h-8 text-xs" onClick={clearFile} data-testid="purchase-clear-file-btn">
                      <X className="w-3 h-3 mr-1" /> Remove
                    </Button>
                    <Button size="sm" className="h-8 text-xs bg-teal-600 hover:bg-teal-700 text-white" onClick={handleExtract} disabled={extracting} data-testid="purchase-extract-btn">
                      {extracting ? <><Loader2 className="w-3 h-3 animate-spin mr-1" /> Extracting...</> : <><Sparkles className="w-3 h-3 mr-1" /> Extract Data</>}
                    </Button>
                  </div>
                </div>
                {uploadPreview && (
                  <div className="rounded-lg overflow-hidden border border-slate-200 max-h-40">
                    <img src={uploadPreview} alt="Preview" className="w-full h-full object-contain max-h-40 bg-white" />
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-lg bg-teal-50 border border-teal-200 flex items-center justify-center flex-shrink-0">
                    <Upload className="w-4 h-4 text-teal-600" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-navy-900">Upload a purchase invoice</p>
                    <p className="text-[10px] text-slate-400">AI will extract supplier, items, and totals automatically</p>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2" data-testid="purchase-upload-options">
                  <button
                    onClick={() => fileCameraRef.current?.click()}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-slate-200 bg-white hover:border-teal-300 hover:bg-teal-50/50 transition-all group"
                    data-testid="purchase-take-photo-btn"
                  >
                    <Camera className="w-5 h-5 text-slate-400 group-hover:text-teal-600 transition-colors" />
                    <span className="text-[10px] font-semibold text-slate-500 group-hover:text-teal-700">Take Photo</span>
                  </button>
                  <button
                    onClick={() => fileImageRef.current?.click()}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-slate-200 bg-white hover:border-teal-300 hover:bg-teal-50/50 transition-all group"
                    data-testid="purchase-upload-image-btn"
                  >
                    <ImageIcon className="w-5 h-5 text-slate-400 group-hover:text-teal-600 transition-colors" />
                    <span className="text-[10px] font-semibold text-slate-500 group-hover:text-teal-700">Upload Image</span>
                  </button>
                  <button
                    onClick={() => filePdfRef.current?.click()}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-slate-200 bg-white hover:border-teal-300 hover:bg-teal-50/50 transition-all group"
                    data-testid="purchase-upload-pdf-btn"
                  >
                    <FileUp className="w-5 h-5 text-slate-400 group-hover:text-teal-600 transition-colors" />
                    <span className="text-[10px] font-semibold text-slate-500 group-hover:text-teal-700">Upload PDF</span>
                  </button>
                </div>
              </div>
            )}
            <input ref={fileCameraRef} type="file" className="hidden" accept="image/*" capture="environment" onChange={(e) => handleFileSelect(e.target.files?.[0])} />
            <input ref={fileImageRef} type="file" className="hidden" accept="image/png,image/jpeg,image/jpg,image/webp" onChange={(e) => handleFileSelect(e.target.files?.[0])} />
            <input ref={filePdfRef} type="file" className="hidden" accept=".pdf,application/pdf" onChange={(e) => handleFileSelect(e.target.files?.[0])} />
          </div>

          <Separator />

          {/* Form fields */}
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Supplier *</Label>
                <Input className="mt-1 h-9 text-sm" value={form.supplier_name} onChange={(e) => updateField('supplier_name', e.target.value)} placeholder="Supplier name" data-testid="form-supplier" />
              </div>
              <div>
                <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Invoice #</Label>
                <Input className="mt-1 h-9 text-sm" value={form.invoice_number} onChange={(e) => updateField('invoice_number', e.target.value)} placeholder="INV-001" data-testid="form-invoice-number" />
              </div>
              <div>
                <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Date</Label>
                <Input className="mt-1 h-9 text-sm" type="date" value={form.invoice_date} onChange={(e) => updateField('invoice_date', e.target.value)} data-testid="form-invoice-date" />
              </div>
            </div>

            {/* Line items */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Line Items</Label>
                <Button size="sm" variant="outline" className="h-7 text-[10px]" onClick={addItem} data-testid="add-line-item-btn">
                  <Plus className="w-3 h-3 mr-1" /> Add Item
                </Button>
              </div>
              <div className="space-y-1.5">
                {form.items.map((item, i) => (
                  <div key={i} className="grid grid-cols-12 gap-1.5 items-center bg-slate-50 rounded-lg p-2" data-testid={`line-item-${i}`}>
                    <Input className="col-span-4 text-xs h-8" placeholder="Item name" value={item.raw_name} onChange={(e) => updateItem(i, 'raw_name', e.target.value)} />
                    <Input className="col-span-2 text-xs h-8" type="number" placeholder="Qty" value={item.quantity || ''} onChange={(e) => updateItem(i, 'quantity', parseFloat(e.target.value) || 0)} />
                    <Input className="col-span-1 text-xs h-8" placeholder="Unit" value={item.unit} onChange={(e) => updateItem(i, 'unit', e.target.value)} />
                    <Input className="col-span-2 text-xs h-8" type="number" step="0.01" placeholder="Price" value={item.unit_price || ''} onChange={(e) => updateItem(i, 'unit_price', parseFloat(e.target.value) || 0)} />
                    <div className="col-span-3 flex items-center gap-1">
                      <span className="text-xs font-semibold text-navy-900 tabular-nums flex-1 text-right">{fmt(item.total || (item.quantity * item.unit_price) || 0)}</span>
                      <Button size="sm" variant="ghost" className="h-6 w-6 p-0 flex-shrink-0" onClick={() => removeItem(i)} data-testid={`remove-item-${i}`}>
                        <Trash2 className="w-3 h-3 text-red-400" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Totals */}
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Subtotal</Label>
                <Input className="mt-1 h-9 text-sm" type="number" step="0.01" value={form.subtotal || ''} onChange={(e) => updateField('subtotal', parseFloat(e.target.value) || 0)} data-testid="form-subtotal" />
              </div>
              <div>
                <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Tax</Label>
                <Input className="mt-1 h-9 text-sm" type="number" step="0.01" value={form.tax || ''} onChange={(e) => updateField('tax', parseFloat(e.target.value) || 0)} data-testid="form-tax" />
              </div>
              <div>
                <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Total</Label>
                <Input className="mt-1 h-9 text-sm font-bold" type="number" step="0.01" value={form.total || ''} onChange={(e) => updateField('total', parseFloat(e.target.value) || 0)} data-testid="form-total" />
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <Button variant="outline" className="h-9 text-xs" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving} className="bg-navy-900 hover:bg-navy-800 text-white h-9 text-xs flex-1" data-testid="save-purchase-btn">
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Plus className="w-3.5 h-3.5 mr-1.5" />}
              Save Purchase
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
