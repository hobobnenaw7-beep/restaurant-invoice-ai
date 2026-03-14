import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import {
  Loader2, Eye, Trash2, ChevronUp, ChevronDown,
  DollarSign, Plus, Upload, Sparkles, FileText, X,
  Camera, Image as ImageIcon, FileUp, Sheet
} from 'lucide-react';
import { useDuplicateCheck, DuplicateWarningDialog } from '@/components/DuplicateCheck';

function fmt(n) { return n != null ? `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '$0.00'; }

const emptySale = () => ({
  report_date: new Date().toISOString().split('T')[0],
  total_sales: 0,
  items: [{ menu_item: '', quantity: 1, revenue: 0 }],
});

export default function SalesPage() {
  const { api } = useAuth();
  const [sales, setSales] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sortBy, setSortBy] = useState('report_date');
  const [sortOrder, setSortOrder] = useState('desc');
  const [selected, setSelected] = useState(null);

  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState(emptySale());
  const [saving, setSaving] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadPreview, setUploadPreview] = useState(null);
  const fileImageRef = useRef(null);
  const filePdfRef = useRef(null);
  const fileCameraRef = useRef(null);
  const fileExcelRef = useRef(null);
  const { checking, duplicates, showWarning, confirmSave, cancelSave, checkDuplicates } = useDuplicateCheck();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/sales', { params: { date_from: dateFrom, date_to: dateTo, sort_by: sortBy, sort_order: sortOrder } });
      setSales(res.data);
    } catch { toast.error('Failed to load sales'); }
    finally { setLoading(false); }
  }, [api, dateFrom, dateTo, sortBy, sortOrder]);

  useEffect(() => { load(); }, [load]);

  const toggleSort = (field) => {
    if (sortBy === field) setSortOrder(o => o === 'desc' ? 'asc' : 'desc');
    else { setSortBy(field); setSortOrder('desc'); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this sales report?')) return;
    try { await api.delete(`/sales/${id}`); toast.success('Deleted'); load(); } catch { toast.error('Failed'); }
  };

  const updateField = (key, val) => setForm(f => ({ ...f, [key]: val }));
  const updateItem = (idx, key, val) => {
    setForm(f => {
      const items = [...f.items];
      items[idx] = { ...items[idx], [key]: val };
      return { ...f, items };
    });
  };
  const removeItem = (idx) => setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) }));
  const addItem = () => setForm(f => ({ ...f, items: [...f.items, { menu_item: '', quantity: 1, revenue: 0 }] }));

  const openAddForm = () => {
    setForm(emptySale());
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

  const isExcelFile = (f) => {
    const name = (f?.name || '').toLowerCase();
    return name.endsWith('.xlsx') || name.endsWith('.xls') || name.endsWith('.csv');
  };

  const handleExtract = async () => {
    if (!uploadFile) return;
    setExtracting(true);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('document_type', 'sales_report');
      const endpoint = isExcelFile(uploadFile) ? '/upload/parse-excel' : '/upload/extract';
      const res = await api.post(endpoint, formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 });
      const d = res.data.extracted_data;
      setForm({
        report_date: d.report_date || new Date().toISOString().split('T')[0],
        total_sales: parseFloat(d.total_sales) || 0,
        items: (d.items || []).map(it => ({ menu_item: it.menu_item || '', quantity: parseFloat(it.quantity) || 0, revenue: parseFloat(it.revenue) || 0 })),
      });
      const msg = res.data.message || `Extracted ${res.data.row_count || 'all'} items. Review and save.`;
      toast.success(msg);
    } catch (err) {
      toast.error('Extraction failed: ' + (err.response?.data?.detail || 'Try again.'));
    } finally { setExtracting(false); }
  };

  const handleSave = async () => {
    if (!form.total_sales && form.total_sales !== 0) { toast.error('Total sales is required'); return; }
    const doSave = async () => {
      setSaving(true);
      try {
        await api.post('/sales', form);
        toast.success('Sale saved');
        setShowAdd(false);
        load();
      } catch (err) {
        toast.error('Save failed: ' + (err.response?.data?.detail || ''));
      } finally { setSaving(false); }
    };
    await checkDuplicates('sale', form, api, doSave);
  };

  const SI = ({ field }) => sortBy === field ? (sortOrder === 'desc' ? <ChevronDown className="w-3 h-3 inline ml-0.5" /> : <ChevronUp className="w-3 h-3 inline ml-0.5" />) : null;

  return (
    <div className="space-y-6 max-w-[1400px]" data-testid="sales-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight">Sales</h1>
          <p className="text-xs text-slate-400 mt-0.5">Daily sales reports</p>
        </div>
        <Button onClick={openAddForm} className="bg-teal-600 hover:bg-teal-700 text-white h-9 text-xs" data-testid="add-sale-btn">
          <Plus className="w-3.5 h-3.5 mr-1.5" /> Add Sale
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 justify-end">
        <Input type="date" className="w-40 h-9 text-xs" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} data-testid="date-from" />
        <Input type="date" className="w-40 h-9 text-xs" value={dateTo} onChange={(e) => setDateTo(e.target.value)} data-testid="date-to" />
      </div>

      {/* Table */}
      <Card className="border border-slate-200/80 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-5 space-y-3">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-11 w-full rounded-lg" />)}</div>
        ) : sales.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4"><DollarSign className="w-6 h-6 text-slate-300" /></div>
            <h3 className="font-heading text-base font-bold text-navy-900 mb-1">No sales found</h3>
            <p className="text-sm text-slate-400 max-w-xs mb-4">Add a sale or upload a sales report to get started.</p>
            <Button onClick={openAddForm} variant="outline" size="sm" className="text-xs" data-testid="empty-add-sale-btn">
              <Plus className="w-3.5 h-3.5 mr-1" /> Add Sale
            </Button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                  <TableHead className="cursor-pointer text-[10px] font-bold text-slate-500 uppercase tracking-wider" onClick={() => toggleSort('report_date')}>Date <SI field="report_date" /></TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-center">Menu Items</TableHead>
                  <TableHead className="cursor-pointer text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right" onClick={() => toggleSort('total_sales')}>Total Revenue <SI field="total_sales" /></TableHead>
                  <TableHead className="w-20" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {sales.map((s, i) => (
                  <TableRow key={s.id} className={`transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} hover:bg-teal-50/30`} data-testid={`sale-row-${i}`}>
                    <TableCell className="text-xs font-medium tabular-nums text-slate-600">{s.report_date}</TableCell>
                    <TableCell className="text-xs text-center text-slate-500">{s.items?.length || 0}</TableCell>
                    <TableCell className="text-xs text-right font-bold text-teal-700 tabular-nums">{fmt(s.total_sales)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-0.5">
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setSelected(s)} data-testid={`view-sale-${i}`}><Eye className="w-3.5 h-3.5 text-slate-500" /></Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => handleDelete(s.id)} data-testid={`delete-sale-${i}`}><Trash2 className="w-3.5 h-3.5 text-red-400" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="px-4 py-2.5 border-t border-slate-100 bg-slate-50/50">
              <p className="text-[11px] text-slate-400">{sales.length} report{sales.length !== 1 ? 's' : ''} &middot; Total: <span className="font-bold text-teal-700">{fmt(sales.reduce((s, r) => s + (r.total_sales || 0), 0))}</span></p>
            </div>
          </div>
        )}
      </Card>

      {/* View Detail Dialog */}
      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="font-heading text-lg">Sales Report</DialogTitle></DialogHeader>
          {selected && (
            <div className="space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <div><p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Date</p><p className="text-sm font-semibold text-navy-900 mt-0.5">{selected.report_date}</p></div>
                <div><p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Total Revenue</p><p className="text-lg font-bold text-teal-700 mt-0.5">{fmt(selected.total_sales)}</p></div>
              </div>
              {selected.items?.length > 0 && (<>
                <Separator />
                <Table>
                  <TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                    <TableHead className="text-[10px] font-bold text-slate-500 uppercase">Menu Item</TableHead>
                    <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right">Qty</TableHead>
                    <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right">Revenue</TableHead>
                  </TableRow></TableHeader>
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

      {/* Add Sale Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading text-lg">Add Sale</DialogTitle>
          </DialogHeader>

          {/* Upload section — multi-option */}
          <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/50 p-4" data-testid="sale-upload-zone">
            {uploadFile ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-9 h-9 rounded-lg bg-teal-50 border border-teal-200 flex items-center justify-center flex-shrink-0">
                      {uploadFile.type.startsWith('image/') ? <ImageIcon className="w-4 h-4 text-teal-600" /> : isExcelFile(uploadFile) ? <Sheet className="w-4 h-4 text-teal-600" /> : <FileText className="w-4 h-4 text-teal-600" />}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-navy-900 truncate">{uploadFile.name}</p>
                      <p className="text-[10px] text-slate-400">{(uploadFile.size / 1024).toFixed(0)} KB &middot; {isExcelFile(uploadFile) ? uploadFile.name.split('.').pop().toUpperCase() : uploadFile.type.split('/')[1]?.toUpperCase()}</p>
                    </div>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    <Button size="sm" variant="outline" className="h-8 text-xs" onClick={clearFile} data-testid="sale-clear-file-btn">
                      <X className="w-3 h-3 mr-1" /> Remove
                    </Button>
                    <Button size="sm" className="h-8 text-xs bg-teal-600 hover:bg-teal-700 text-white" onClick={handleExtract} disabled={extracting} data-testid="sale-extract-btn">
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
                    <p className="text-xs font-semibold text-navy-900">Upload a sales invoice</p>
                    <p className="text-[10px] text-slate-400">AI will extract date, items, and totals automatically</p>
                  </div>
                </div>
                <div className="grid grid-cols-4 gap-2" data-testid="sale-upload-options">
                  <button
                    onClick={() => fileCameraRef.current?.click()}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-slate-200 bg-white hover:border-teal-300 hover:bg-teal-50/50 transition-all group"
                    data-testid="sale-take-photo-btn"
                  >
                    <Camera className="w-5 h-5 text-slate-400 group-hover:text-teal-600 transition-colors" />
                    <span className="text-[10px] font-semibold text-slate-500 group-hover:text-teal-700">Take Photo</span>
                  </button>
                  <button
                    onClick={() => fileImageRef.current?.click()}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-slate-200 bg-white hover:border-teal-300 hover:bg-teal-50/50 transition-all group"
                    data-testid="sale-upload-image-btn"
                  >
                    <ImageIcon className="w-5 h-5 text-slate-400 group-hover:text-teal-600 transition-colors" />
                    <span className="text-[10px] font-semibold text-slate-500 group-hover:text-teal-700">Upload Image</span>
                  </button>
                  <button
                    onClick={() => filePdfRef.current?.click()}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-slate-200 bg-white hover:border-teal-300 hover:bg-teal-50/50 transition-all group"
                    data-testid="sale-upload-pdf-btn"
                  >
                    <FileUp className="w-5 h-5 text-slate-400 group-hover:text-teal-600 transition-colors" />
                    <span className="text-[10px] font-semibold text-slate-500 group-hover:text-teal-700">Upload PDF</span>
                  </button>
                  <button
                    onClick={() => fileExcelRef.current?.click()}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-slate-200 bg-white hover:border-teal-300 hover:bg-teal-50/50 transition-all group"
                    data-testid="sale-upload-excel-btn"
                  >
                    <Sheet className="w-5 h-5 text-slate-400 group-hover:text-teal-600 transition-colors" />
                    <span className="text-[10px] font-semibold text-slate-500 group-hover:text-teal-700">Upload Excel</span>
                  </button>
                </div>
              </div>
            )}
            <input ref={fileCameraRef} type="file" className="hidden" accept="image/*" capture="environment" onChange={(e) => handleFileSelect(e.target.files?.[0])} />
            <input ref={fileImageRef} type="file" className="hidden" accept="image/png,image/jpeg,image/jpg,image/webp" onChange={(e) => handleFileSelect(e.target.files?.[0])} />
            <input ref={filePdfRef} type="file" className="hidden" accept=".pdf,application/pdf" onChange={(e) => handleFileSelect(e.target.files?.[0])} />
            <input ref={fileExcelRef} type="file" className="hidden" accept=".xlsx,.xls,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv" onChange={(e) => handleFileSelect(e.target.files?.[0])} data-testid="sale-excel-input" />
          </div>

          <Separator />

          {/* Form fields */}
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Report Date</Label>
                <Input className="mt-1 h-9 text-sm" type="date" value={form.report_date} onChange={(e) => updateField('report_date', e.target.value)} data-testid="form-report-date" />
              </div>
              <div>
                <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Total Sales *</Label>
                <Input className="mt-1 h-9 text-sm font-semibold" type="number" step="0.01" value={form.total_sales || ''} onChange={(e) => updateField('total_sales', parseFloat(e.target.value) || 0)} placeholder="0.00" data-testid="form-total-sales" />
              </div>
            </div>

            {/* Menu items */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Menu Items (optional)</Label>
                <Button size="sm" variant="outline" className="h-7 text-[10px]" onClick={addItem} data-testid="add-menu-item-btn">
                  <Plus className="w-3 h-3 mr-1" /> Add Item
                </Button>
              </div>
              <div className="space-y-1.5">
                {form.items.map((item, i) => (
                  <div key={i} className="grid grid-cols-12 gap-1.5 items-center bg-slate-50 rounded-lg p-2" data-testid={`menu-item-${i}`}>
                    <Input className="col-span-5 text-xs h-8" placeholder="Menu item name" value={item.menu_item} onChange={(e) => updateItem(i, 'menu_item', e.target.value)} />
                    <Input className="col-span-3 text-xs h-8" type="number" placeholder="Qty" value={item.quantity || ''} onChange={(e) => updateItem(i, 'quantity', parseFloat(e.target.value) || 0)} />
                    <div className="col-span-4 flex items-center gap-1">
                      <Input className="text-xs h-8" type="number" step="0.01" placeholder="Revenue" value={item.revenue || ''} onChange={(e) => updateItem(i, 'revenue', parseFloat(e.target.value) || 0)} />
                      <Button size="sm" variant="ghost" className="h-6 w-6 p-0 flex-shrink-0" onClick={() => removeItem(i)} data-testid={`remove-menu-item-${i}`}>
                        <Trash2 className="w-3 h-3 text-red-400" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <Button variant="outline" className="h-9 text-xs" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving} className="bg-teal-600 hover:bg-teal-700 text-white h-9 text-xs flex-1" data-testid="save-sale-btn">
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Plus className="w-3.5 h-3.5 mr-1.5" />}
              Save Sale
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <DuplicateWarningDialog open={showWarning} onClose={cancelSave} onConfirm={confirmSave} duplicates={duplicates} saving={saving} />
    </div>
  );
}
