import { useState, useEffect, useRef, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { dataEvents } from '@/lib/dataEvents';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import {
  Search, Loader2, Eye, Trash2, ChevronUp, ChevronDown,
  Plus, Upload, Sparkles, FileText, X, AlertTriangle,
  Camera, Image as ImageIcon, FileUp, Sheet,
  Receipt, Beef, Users2, Wrench
} from 'lucide-react';
import { useDuplicateCheck, DuplicateWarningDialog } from '@/components/DuplicateCheck';
import { ConfirmDeleteDialog } from '@/components/ConfirmDeleteDialog';

function fmt(n) { return n != null ? `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '$0.00'; }
let _keySeq = 0;
function nextKey() { return `k${++_keySeq}_${Date.now()}`; }
function mkItem(raw_name = '', quantity = 1, unit = 'kg', unit_price = 0, total = 0, warning = false, warning_detail = '') {
  return { _key: nextKey(), raw_name, quantity, unit, unit_price, total, _warning: warning, _warning_detail: warning_detail };
}

const OTHER_CATEGORIES = ['Rent', 'Electricity', 'Water', 'Gas', 'Maintenance', 'Equipment', 'Insurance', 'Marketing', 'Other'];

// ======================== ITEM AUTOCOMPLETE ========================
// Fully controlled: parent owns the value, component owns only dropdown open state.
// No useEffect syncing — eliminates cascading re-renders on Safari after extraction.
function ItemAutocomplete({ value, onChange, knownItems, index }) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    document.addEventListener('touchstart', handler);
    return () => { document.removeEventListener('mousedown', handler); document.removeEventListener('touchstart', handler); };
  }, []);

  const q = (value || '').toLowerCase().trim();
  const safeItems = knownItems || [];
  const filtered = safeItems.filter(n => !q || n.toLowerCase().includes(q)).slice(0, 8);
  const exactMatch = safeItems.some(n => n.toLowerCase() === q);

  return (
    <div ref={wrapperRef} className="relative col-span-4">
      <Input
        className="text-xs h-8 w-full"
        placeholder="Item name"
        value={value || ''}
        onChange={(e) => { onChange(e.target.value); setOpen(true); }}
        onFocus={() => { if (safeItems.length > 0) setOpen(true); }}
        data-testid={`line-item-name-${index}`}
      />
      {open && (filtered.length > 0 || (q && !exactMatch)) && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
          {filtered.map((name) => (
            <button
              key={name}
              type="button"
              className={`w-full text-left px-3 py-1.5 text-xs hover:bg-teal-50 transition-colors ${name.toLowerCase() === q ? 'bg-teal-50 font-semibold text-teal-700' : 'text-navy-900'}`}
              onMouseDown={(e) => { e.preventDefault(); onChange(name); setOpen(false); }}
              data-testid={`item-option-${name}`}
            >
              {name}
            </button>
          ))}
          {q && !exactMatch && (
            <>
              {filtered.length > 0 && <div className="border-t border-slate-100" />}
              <div className="px-3 py-1.5 text-[10px] text-slate-400 italic">
                Use "{value}" as new item
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ======================== RAW MATERIALS TAB ========================
function RawMaterialsTab({ api }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sortBy, setSortBy] = useState('invoice_date');
  const [sortOrder, setSortOrder] = useState('desc');
  const [selected, setSelected] = useState(null);
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ supplier_name: '', invoice_number: '', invoice_date: new Date().toISOString().split('T')[0], items: [mkItem()], subtotal: 0, tax: 0, total: 0 });
  const [saving, setSaving] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadPreview, setUploadPreview] = useState(null);
  const fileImageRef = useRef(null);
  const filePdfRef = useRef(null);
  const fileCameraRef = useRef(null);
  const fileExcelRef = useRef(null);
  const [knownItems, setKnownItems] = useState([]);
  const { checking, duplicates, showWarning, confirmSave, cancelSave, checkDuplicates } = useDuplicateCheck();
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, id: null, message: '', type: null, idx: null });
  const [receiptId, setReceiptId] = useState(null);
  const [parsingMethod, setParsingMethod] = useState(null);

  const load = useCallback(async (showSkeleton = false) => {
    if (showSkeleton) setLoading(true);
    try { const res = await api.get('/purchases', { params: { search, date_from: dateFrom, date_to: dateTo, sort_by: sortBy, sort_order: sortOrder } }); setItems(res.data); }
    catch { toast.error('Failed to load'); } finally { setLoading(false); }
  }, [api, search, dateFrom, dateTo, sortBy, sortOrder]);
  useEffect(() => { load(true); }, [load]);

  const toggleSort = (f) => { if (sortBy === f) setSortOrder(o => o === 'desc' ? 'asc' : 'desc'); else { setSortBy(f); setSortOrder('desc'); } };
  const requestDeleteRecord = (id) => setDeleteConfirm({ open: true, id, message: 'Are you sure you want to delete this purchase record?', type: 'record', idx: null });
  const requestDeleteItem = (idx) => setDeleteConfirm({ open: true, id: null, message: 'Are you sure you want to delete this item?', type: 'item', idx });
  const handleDeleteConfirm = async () => {
    const { type, id, idx } = deleteConfirm;
    setDeleteConfirm({ open: false, id: null, message: '', type: null, idx: null });
    if (type === 'record') {
      const prev = items;
      setItems(cur => cur.filter(p => p.id !== id));
      dataEvents.emit();
      try { await api.delete(`/purchases/${id}`); toast.success('Deleted'); }
      catch { toast.error('Failed to delete'); setItems(prev); }
    } else if (type === 'item') {
      setForm(f => { const newItems = f.items.filter((_, i) => i !== idx); const totals = recalcTotals(newItems, f.tax); return { ...f, items: newItems, ...totals }; });
    }
  };
  const cancelDelete = () => setDeleteConfirm({ open: false, id: null, message: '', type: null, idx: null });
  const SI = ({ field }) => sortBy === field ? (sortOrder === 'desc' ? <ChevronDown className="w-3 h-3 inline ml-0.5" /> : <ChevronUp className="w-3 h-3 inline ml-0.5" />) : null;

  const updateField = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const round2 = (n) => Math.round(n * 100) / 100;
  const recalcTotals = (lineItems, tax) => {
    const subtotal = round2(lineItems.reduce((s, it) => s + (parseFloat(it.total) || 0), 0));
    return { subtotal, total: round2(subtotal + (parseFloat(tax) || 0)) };
  };
  const updateItem = (idx, k, v) => { setForm(f => { const it = [...f.items]; it[idx] = { ...it[idx], [k]: v }; if (k === 'quantity' || k === 'unit_price') { it[idx].total = round2(parseFloat(it[idx].quantity || 0) * parseFloat(it[idx].unit_price || 0)); it[idx]._warning = false; it[idx]._warning_detail = ''; } const totals = recalcTotals(it, f.tax); return { ...f, items: it, ...totals }; }); };
  const addItem = () => setForm(f => ({ ...f, items: [...f.items, mkItem()] }));

  const openAdd = () => {
    setEditingId(null);
    setForm({ supplier_name: '', invoice_number: '', invoice_date: new Date().toISOString().split('T')[0], items: [mkItem()], subtotal: 0, tax: 0, total: 0 });
    if (uploadPreview) URL.revokeObjectURL(uploadPreview);
    setUploadFile(null); setUploadPreview(null); setShowAdd(true);
    setReceiptId(null); setParsingMethod(null);
    api.get('/items').then(res => {
      const names = [];
      (res.data || []).forEach(item => {
        names.push(item.name);
        (item.aliases || []).forEach(a => names.push(a.alias_name));
      });
      setKnownItems([...new Set(names)].sort());
    }).catch(() => {});
  };
  const openEdit = (record) => {
    setEditingId(record.id);
    setForm({
      supplier_name: record.supplier_name || '',
      invoice_number: record.invoice_number || '',
      invoice_date: record.invoice_date || '',
      items: (record.items || []).map(it => mkItem(it.raw_name || '', it.quantity || 0, it.unit || '', it.unit_price || 0, it.total || 0)),
      subtotal: record.subtotal || 0,
      tax: record.tax || 0,
      total: record.total || 0,
    });
    if (uploadPreview) URL.revokeObjectURL(uploadPreview);
    setUploadFile(null); setUploadPreview(null); setShowAdd(true);
    api.get('/items').then(res => {
      const names = [];
      (res.data || []).forEach(item => { names.push(item.name); (item.aliases || []).forEach(a => names.push(a.alias_name)); });
      setKnownItems([...new Set(names)].sort());
    }).catch(() => {});
  };

  // Use object URLs instead of base64 data URLs for image preview.
  // iPhone photos can be 5-15MB; base64 inflates that by 33%.
  // React diffs this string on every re-render — on Safari's smaller stack, this overflows.
  const handleFileSelect = (f) => {
    if (!f) return;
    // Revoke previous object URL to prevent memory leaks
    if (uploadPreview) URL.revokeObjectURL(uploadPreview);
    setUploadFile(f);
    if (f.type.startsWith('image/')) {
      setUploadPreview(URL.createObjectURL(f));
    } else {
      setUploadPreview(null);
    }
  };
  const clearFile = () => {
    if (uploadPreview) URL.revokeObjectURL(uploadPreview);
    setUploadFile(null);
    setUploadPreview(null);
  };
  const isExcelFile = (f) => { const n = (f?.name || '').toLowerCase(); return n.endsWith('.xlsx') || n.endsWith('.xls') || n.endsWith('.csv'); };

  const extractingRef = useRef(false);
  const handleExtract = async () => {
    if (!uploadFile || extractingRef.current) return;
    extractingRef.current = true;
    setExtracting(true);
    try {
      const fd = new FormData(); fd.append('file', uploadFile); fd.append('document_type', 'purchase_invoice');
      const ep = isExcelFile(uploadFile) ? '/upload/parse-excel' : '/upload/extract';
      const res = await api.post(ep, fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 });
      const d = res.data?.extracted_data || {};
      const items = Array.isArray(d.items) ? d.items : [];
      const hasWarnings = d._has_warnings || false;
      setForm({
        supplier_name: d.supplier_name || '',
        invoice_number: d.invoice_number || '',
        invoice_date: d.invoice_date || new Date().toISOString().split('T')[0],
        items: items.length > 0
          ? items.map(it => mkItem(it.raw_name || '', parseFloat(it.quantity) || 0, it.unit || '', parseFloat(it.unit_price) || 0, parseFloat(it.total) || 0, !!it._warning, it._warning_detail || ''))
          : [mkItem()],
        subtotal: parseFloat(d.subtotal) || 0,
        tax: parseFloat(d.tax) || 0,
        total: parseFloat(d.total) || 0,
        _has_warnings: hasWarnings,
        _warnings: d._warnings || [],
        _subtotal_warning: d._subtotal_warning || false,
        _total_warning: d._total_warning || false,
        _date_warning: d._date_warning || false,
      });
      if (hasWarnings) {
        toast.warning('Some fields need review — highlighted in yellow');
      } else {
        toast.success(res.data.message || 'Data extracted! Review and save.');
      }
      // Store receipt tracking info
      if (res.data?.receipt_id) setReceiptId(res.data.receipt_id);
      if (res.data?.parsing_method) setParsingMethod(res.data.parsing_method);
    } catch (err) { toast.error('Extraction failed: ' + (err.response?.data?.detail || 'Try again.')); }
    finally { setExtracting(false); extractingRef.current = false; }
  };

  const handleSave = async () => {
    if (!form.supplier_name.trim()) { toast.error('Vendor name is required'); return; }
    const doSave = async () => {
      setSaving(true);
      try {
        const payload = { ...form, items: form.items.map(({ _key, _warning, _warning_detail, ...rest }) => rest) };
        delete payload._has_warnings; delete payload._warnings; delete payload._subtotal_warning; delete payload._total_warning; delete payload._date_warning;
        if (editingId) {
          await api.put(`/purchases/${editingId}`, payload);
          toast.success('Updated');
        } else {
          const res = await api.post('/purchases', payload);
          if (uploadFile && res.data?.id) {
            try {
              const fd = new FormData();
              fd.append('file', uploadFile);
              fd.append('folder', 'expenses');
              fd.append('transaction_type', 'raw_material');
              fd.append('transaction_id', res.data.id);
              fd.append('transaction_date', form.invoice_date || '');
              fd.append('transaction_amount', form.total || 0);
              fd.append('transaction_notes', `Invoice #${form.invoice_number || 'N/A'}`);
              fd.append('vendor_name', form.supplier_name || '');
              await api.post('/records/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
            } catch { /* silent */ }
          }
          toast.success('Saved');
        }
        // Learn vendor patterns from corrected data
        if (receiptId || uploadFile) {
          try {
            await api.post('/receipts/learn', {
              receipt_id: receiptId,
              vendor_name: form.supplier_name,
              vendor_id: form.supplier_id || '',
              corrected_items: form.items.map(({ _key, _warning, _warning_detail, ...rest }) => rest),
              corrected_date: form.invoice_date,
              corrected_total: form.total,
            });
          } catch { /* silent — learning failure shouldn't block save */ }
        }
        setShowAdd(false);
        setReceiptId(null); setParsingMethod(null);
        load(true);
        dataEvents.emit();
      }
      catch (err) { toast.error('Save failed: ' + (err.response?.data?.detail || '')); }
      finally { setSaving(false); }
    };
    if (editingId) { await doSave(); } else { await checkDuplicates('purchase', form, api, doSave); }
  };

  return (
    <div className="space-y-4" data-testid="raw-materials-tab">
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1"><Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" /><Input className="pl-9 h-9 text-sm" placeholder="Search vendor or invoice..." value={search} onChange={(e) => setSearch(e.target.value)} data-testid="search-raw-materials" /></div>
        <Input type="date" className="w-36 h-9 text-xs" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        <Input type="date" className="w-36 h-9 text-xs" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        <Button onClick={openAdd} className="bg-navy-900 hover:bg-navy-800 text-white h-9 text-xs" data-testid="add-raw-material-btn"><Plus className="w-3.5 h-3.5 mr-1.5" /> Add</Button>
      </div>

      <Card className="border border-slate-200/80 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <Table><TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
            <TableHead className="cursor-pointer text-[10px] font-bold text-slate-500 uppercase tracking-wider" onClick={() => toggleSort('invoice_date')}>Date <SI field="invoice_date" /></TableHead>
            <TableHead className="cursor-pointer text-[10px] font-bold text-slate-500 uppercase tracking-wider" onClick={() => toggleSort('supplier_name')}>Vendor <SI field="supplier_name" /></TableHead>
            <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Invoice #</TableHead>
            <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-center">Items</TableHead>
            <TableHead className="cursor-pointer text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right" onClick={() => toggleSort('total')}>Total <SI field="total" /></TableHead>
            <TableHead className="w-20" />
          </TableRow></TableHeader><TableBody>
            {loading ? [1,2,3,4].map(i => (
              <TableRow key={`skel-${i}`}><TableCell colSpan={6}><Skeleton className="h-8 w-full rounded" /></TableCell></TableRow>
            )) : items.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="h-40">
                <div className="flex flex-col items-center justify-center text-center py-6">
                  <Beef className="w-10 h-10 text-slate-300 mb-3" />
                  <h3 className="font-heading text-sm font-bold text-navy-900 mb-1">No raw material purchases</h3>
                  <p className="text-xs text-slate-400 mb-3">Upload an invoice or add manually</p>
                  <Button onClick={openAdd} variant="outline" size="sm" className="text-xs"><Plus className="w-3 h-3 mr-1" /> Add</Button>
                </div>
              </TableCell></TableRow>
            ) : items.map((p, i) => (
              <TableRow key={p.id} className={`transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} hover:bg-teal-50/30`} data-testid={`raw-material-row-${i}`}>
                <TableCell className="text-xs tabular-nums text-slate-600">{p.invoice_date}</TableCell>
                <TableCell className="text-xs font-semibold text-navy-900">{p.supplier_name}</TableCell>
                <TableCell><Badge variant="outline" className="text-[10px] font-mono">{p.invoice_number}</Badge></TableCell>
                <TableCell className="text-xs text-center text-slate-500">{(p.items || []).length}</TableCell>
                <TableCell className="text-xs text-right font-bold text-navy-900 tabular-nums">{fmt(p.total)}</TableCell>
                <TableCell className="text-right"><div className="flex justify-end gap-0.5">
                  <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setSelected(p)} data-testid={`view-purchase-${i}`}><Eye className="w-3.5 h-3.5 text-slate-500" /></Button>
                  <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => openEdit(p)} data-testid={`edit-purchase-${i}`}><FileText className="w-3.5 h-3.5 text-blue-500" /></Button>
                  <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => requestDeleteRecord(p.id)} data-testid={`delete-purchase-${i}`}><Trash2 className="w-3.5 h-3.5 text-red-400" /></Button>
                </div></TableCell>
              </TableRow>
            ))}
          </TableBody></Table>
          {items.length > 0 && <div className="px-4 py-2.5 border-t border-slate-100 bg-slate-50/50"><p className="text-[11px] text-slate-400">{items.length} invoice{items.length !== 1 ? 's' : ''} &middot; Total: <span className="font-bold text-navy-900">{fmt(items.reduce((s, p) => s + (p.total || 0), 0))}</span></p></div>}
        </div>
      </Card>

      {/* View Detail */}
      <Dialog open={!!selected} onOpenChange={(v) => { if (!v) setSelected(null); }}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="font-heading text-lg">Purchase Details</DialogTitle></DialogHeader>
          {selected && <div className="space-y-5">
            <div className="grid grid-cols-3 gap-4">{[['Vendor', selected.supplier_name], ['Invoice #', selected.invoice_number], ['Date', selected.invoice_date]].map(([l, v]) => <div key={l}><p className="text-[10px] font-bold text-slate-400 uppercase">{l}</p><p className="text-sm font-semibold text-navy-900 mt-0.5">{v}</p></div>)}</div>
            <Separator />
            <Table><TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80"><TableHead className="text-[10px] font-bold text-slate-500 uppercase">Item</TableHead><TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right">Qty</TableHead><TableHead className="text-[10px] font-bold text-slate-500 uppercase">Unit</TableHead><TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right">Price</TableHead><TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right">Total</TableHead></TableRow></TableHeader><TableBody>
              {(selected.items || []).map((it, i) => <TableRow key={i} className={i % 2 === 0 ? '' : 'bg-slate-50/40'}><TableCell className="text-sm font-medium">{it.raw_name}</TableCell><TableCell className="text-sm text-right tabular-nums">{it.quantity}</TableCell><TableCell className="text-sm text-slate-500">{it.unit}</TableCell><TableCell className="text-sm text-right tabular-nums">{fmt(it.unit_price)}</TableCell><TableCell className="text-sm text-right font-semibold tabular-nums">{fmt(it.total)}</TableCell></TableRow>)}
            </TableBody></Table>
            <div className="flex justify-end"><div className="text-right space-y-1 min-w-[200px]"><div className="flex justify-between text-sm"><span className="text-slate-500">Subtotal</span><span className="tabular-nums">{fmt(selected.subtotal)}</span></div><div className="flex justify-between text-sm"><span className="text-slate-500">Tax</span><span className="tabular-nums">{fmt(selected.tax)}</span></div><Separator className="my-1" /><div className="flex justify-between text-base font-bold"><span>Total</span><span className="tabular-nums">{fmt(selected.total)}</span></div></div></div>
          </div>}
        </DialogContent>
      </Dialog>

      {/* Add Dialog — prevent close during save */}
      <Dialog open={showAdd} onOpenChange={(v) => { if (!saving && !extracting) setShowAdd(v); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="font-heading text-lg">{editingId ? 'Edit Purchase' : 'Add Raw Material Purchase'}</DialogTitle></DialogHeader>
          <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/50 p-4" data-testid="raw-material-upload-zone">
            {uploadFile ? <div className="space-y-3"><div className="flex items-center justify-between"><div className="flex items-center gap-2.5 min-w-0"><div className="w-9 h-9 rounded-lg bg-teal-50 border border-teal-200 flex items-center justify-center flex-shrink-0">{uploadFile.type.startsWith('image/') ? <ImageIcon className="w-4 h-4 text-teal-600" /> : isExcelFile(uploadFile) ? <Sheet className="w-4 h-4 text-teal-600" /> : <FileText className="w-4 h-4 text-teal-600" />}</div><div className="min-w-0"><p className="text-xs font-semibold text-navy-900 truncate">{uploadFile.name}</p><p className="text-[10px] text-slate-400">{(uploadFile.size / 1024).toFixed(0)} KB</p></div></div><div className="flex gap-2 flex-shrink-0"><Button size="sm" variant="outline" className="h-8 text-xs" onClick={clearFile}><X className="w-3 h-3 mr-1" /> Remove</Button><Button size="sm" className="h-8 text-xs bg-teal-600 hover:bg-teal-700 text-white" onClick={handleExtract} disabled={extracting} data-testid="raw-material-extract-btn">{extracting ? <><Loader2 className="w-3 h-3 animate-spin mr-1" /> Extracting...</> : <><Sparkles className="w-3 h-3 mr-1" /> Extract Data</>}</Button></div></div>{uploadPreview && <div className="rounded-lg overflow-hidden border border-slate-200 max-h-40"><img src={uploadPreview} alt="Preview" className="w-full h-full object-contain max-h-40 bg-white" /></div>}</div>
            : <div className="space-y-3"><div className="flex items-center gap-2.5"><div className="w-9 h-9 rounded-lg bg-teal-50 border border-teal-200 flex items-center justify-center flex-shrink-0"><Upload className="w-4 h-4 text-teal-600" /></div><div><p className="text-xs font-semibold text-navy-900">Upload a purchase invoice</p><p className="text-[10px] text-slate-400">AI will extract vendor, items, and totals</p></div></div>
              <div className="grid grid-cols-4 gap-2" data-testid="raw-material-upload-options">
                <button onClick={() => fileCameraRef.current?.click()} className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-slate-200 bg-white hover:border-teal-300 hover:bg-teal-50/50 transition-all group" data-testid="rm-take-photo-btn"><Camera className="w-5 h-5 text-slate-400 group-hover:text-teal-600 transition-colors" /><span className="text-[10px] font-semibold text-slate-500 group-hover:text-teal-700">Take Photo</span></button>
                <button onClick={() => fileImageRef.current?.click()} className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-slate-200 bg-white hover:border-teal-300 hover:bg-teal-50/50 transition-all group" data-testid="rm-upload-image-btn"><ImageIcon className="w-5 h-5 text-slate-400 group-hover:text-teal-600 transition-colors" /><span className="text-[10px] font-semibold text-slate-500 group-hover:text-teal-700">Upload Image</span></button>
                <button onClick={() => filePdfRef.current?.click()} className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-slate-200 bg-white hover:border-teal-300 hover:bg-teal-50/50 transition-all group" data-testid="rm-upload-pdf-btn"><FileUp className="w-5 h-5 text-slate-400 group-hover:text-teal-600 transition-colors" /><span className="text-[10px] font-semibold text-slate-500 group-hover:text-teal-700">Upload PDF</span></button>
                <button onClick={() => fileExcelRef.current?.click()} className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-slate-200 bg-white hover:border-teal-300 hover:bg-teal-50/50 transition-all group" data-testid="rm-upload-excel-btn"><Sheet className="w-5 h-5 text-slate-400 group-hover:text-teal-600 transition-colors" /><span className="text-[10px] font-semibold text-slate-500 group-hover:text-teal-700">Upload Excel</span></button>
              </div></div>}
            <input ref={fileCameraRef} type="file" className="hidden" accept="image/*" capture="environment" onChange={(e) => handleFileSelect(e.target.files?.[0])} />
            <input ref={fileImageRef} type="file" className="hidden" accept="image/png,image/jpeg,image/jpg,image/webp" onChange={(e) => handleFileSelect(e.target.files?.[0])} />
            <input ref={filePdfRef} type="file" className="hidden" accept=".pdf,application/pdf" onChange={(e) => handleFileSelect(e.target.files?.[0])} />
            <input ref={fileExcelRef} type="file" className="hidden" accept=".xlsx,.xls,.csv" onChange={(e) => handleFileSelect(e.target.files?.[0])} />
          </div>
          <Separator />
          {/* Warning banner for OCR review */}
          {form._has_warnings && (
            <div className="flex items-start gap-2.5 p-3 rounded-lg bg-amber-50 border border-amber-200" data-testid="ocr-warning-banner">
              <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-amber-800">Review needed</p>
                <p className="text-[10px] text-amber-600 mt-0.5">Some extracted values may be inaccurate. Fields highlighted in yellow need your attention.</p>
              </div>
            </div>
          )}
          {parsingMethod && (
            <div className="flex items-center gap-2 text-[10px]" data-testid="parsing-method-badge">
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-semibold ${parsingMethod === 'vendor' ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-blue-700'}`}>
                <Sparkles className="w-3 h-3" />
                {parsingMethod === 'vendor' ? 'Vendor pattern matched' : 'General parsing'}
              </span>
              <span className="text-slate-400">Corrections help improve future extractions for this vendor</span>
            </div>
          )}
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Vendor *</Label><Input className="mt-1 h-9 text-sm" value={form.supplier_name} onChange={(e) => updateField('supplier_name', e.target.value)} placeholder="Vendor name" data-testid="form-vendor" /></div>
              <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Invoice #</Label><Input className="mt-1 h-9 text-sm" value={form.invoice_number} onChange={(e) => updateField('invoice_number', e.target.value)} placeholder="INV-001" data-testid="form-invoice-number" /></div>
              <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Date {form._date_warning && <AlertTriangle className="w-3 h-3 inline text-amber-500" />}</Label><Input className={`mt-1 h-9 text-sm ${form._date_warning ? 'border-amber-300 bg-amber-50/50' : ''}`} type="date" value={form.invoice_date} onChange={(e) => { updateField('invoice_date', e.target.value); setForm(f => ({ ...f, _date_warning: false })); }} data-testid="form-invoice-date" /></div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2"><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Line Items</Label><Button size="sm" variant="outline" className="h-7 text-[10px]" onClick={addItem} data-testid="add-line-item-btn"><Plus className="w-3 h-3 mr-1" /> Add Item</Button></div>
              <div className="space-y-1.5">{form.items.map((item, i) => (
                <div key={item._key} className={`grid grid-cols-12 gap-1.5 items-center rounded-lg p-2 ${item._warning ? 'bg-amber-50 border border-amber-200' : 'bg-slate-50'}`} data-testid={`line-item-${i}`}>
                  <ItemAutocomplete value={item.raw_name} onChange={(v) => updateItem(i, 'raw_name', v)} knownItems={knownItems} index={i} />
                  <Input className={`col-span-2 text-xs h-8 ${item._warning && (!item.quantity) ? 'border-amber-300' : ''}`} type="number" placeholder="Qty" value={item.quantity || ''} onChange={(e) => updateItem(i, 'quantity', parseFloat(e.target.value) || 0)} />
                  <Input className="col-span-1 text-xs h-8" placeholder="Unit" value={item.unit} onChange={(e) => updateItem(i, 'unit', e.target.value)} />
                  <Input className={`col-span-2 text-xs h-8 ${item._warning && (!item.unit_price) ? 'border-amber-300' : ''}`} type="number" step="0.01" placeholder="Price" value={item.unit_price || ''} onChange={(e) => updateItem(i, 'unit_price', parseFloat(e.target.value) || 0)} />
                  <div className="col-span-3 flex items-center gap-1">
                    <Input className={`text-xs h-8 font-semibold tabular-nums flex-1 text-right bg-slate-50 ${item._warning ? 'border-amber-300' : ''}`} type="number" step="0.01" value={item.total || ''} readOnly tabIndex={-1} data-testid={`line-item-total-${i}`} />
                    <Button size="sm" variant="ghost" className="h-6 w-6 p-0 flex-shrink-0" onClick={() => requestDeleteItem(i)}><Trash2 className="w-3 h-3 text-red-400" /></Button>
                  </div>
                  {item._warning_detail && <p className="col-span-12 text-[9px] text-amber-600 -mt-0.5 pl-1"><AlertTriangle className="w-2.5 h-2.5 inline mr-0.5" />{item._warning_detail}</p>}
                </div>
              ))}</div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Subtotal {form._subtotal_warning && <AlertTriangle className="w-3 h-3 inline text-amber-500" />}</Label><Input className={`mt-1 h-9 text-sm ${form._subtotal_warning ? 'border-amber-300 bg-amber-50/50' : 'bg-slate-50'}`} type="number" step="0.01" value={form.subtotal || ''} readOnly tabIndex={-1} data-testid="form-subtotal" /></div>
              <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Tax</Label><Input className="mt-1 h-9 text-sm" type="number" step="0.01" value={form.tax || ''} onChange={(e) => { const tax = parseFloat(e.target.value) || 0; setForm(f => ({ ...f, tax, total: round2(f.subtotal + tax) })); }} data-testid="form-tax" /></div>
              <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Total {form._total_warning && <AlertTriangle className="w-3 h-3 inline text-amber-500" />}</Label><Input className={`mt-1 h-9 text-sm font-bold ${form._total_warning ? 'border-amber-300 bg-amber-50/50' : 'bg-slate-50'}`} type="number" step="0.01" value={form.total || ''} readOnly tabIndex={-1} data-testid="form-total" /></div>
            </div>
          </div>
          <div className="flex gap-3 pt-2"><Button variant="outline" className="h-9 text-xs" onClick={() => setShowAdd(false)} disabled={saving}>Cancel</Button><Button onClick={handleSave} disabled={saving} className="bg-navy-900 hover:bg-navy-800 text-white h-9 text-xs flex-1" data-testid="save-raw-material-btn">{saving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Plus className="w-3.5 h-3.5 mr-1.5" />} {editingId ? 'Update' : 'Confirm & Save'}</Button></div>
        </DialogContent>
      </Dialog>
      <DuplicateWarningDialog open={showWarning} onClose={cancelSave} onConfirm={confirmSave} duplicates={duplicates} saving={saving} />
      <ConfirmDeleteDialog open={deleteConfirm.open} onClose={cancelDelete} onConfirm={handleDeleteConfirm} message={deleteConfirm.message} />
    </div>
  );
}

// ======================== SALARIES TAB ========================
function SalariesTab({ api }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ employee_name: '', position: '', amount: 0, payment_date: new Date().toISOString().split('T')[0], notes: '' });
  const [saving, setSaving] = useState(false);
  const { checking, duplicates, showWarning, confirmSave, cancelSave, checkDuplicates } = useDuplicateCheck();
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, id: null, message: '' });

  const load = useCallback(async (showSkeleton = false) => {
    if (showSkeleton) setLoading(true);
    try { const res = await api.get('/salaries'); setItems(res.data); }
    catch { toast.error('Failed to load salaries'); } finally { setLoading(false); }
  }, [api]);
  useEffect(() => { load(true); }, [load]);

  const requestDelete = (id) => setDeleteConfirm({ open: true, id, message: 'Are you sure you want to delete this salary record?' });
  const handleDeleteConfirm = async () => {
    const { id } = deleteConfirm;
    setDeleteConfirm({ open: false, id: null, message: '' });
    const prev = items;
    setItems(cur => cur.filter(s => s.id !== id));
    dataEvents.emit();
    try { await api.delete(`/salaries/${id}`); toast.success('Deleted'); }
    catch { toast.error('Failed to delete'); setItems(prev); }
  };
  const cancelDelete = () => setDeleteConfirm({ open: false, id: null, message: '' });
  const updateField = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const openAdd = () => { setEditingId(null); setForm({ employee_name: '', position: '', amount: 0, payment_date: new Date().toISOString().split('T')[0], notes: '' }); setShowAdd(true); };
  const openEdit = (record) => {
    setEditingId(record.id);
    setForm({ employee_name: record.employee_name || '', position: record.position || '', amount: record.amount || 0, payment_date: record.payment_date || '', notes: record.notes || '' });
    setShowAdd(true);
  };
  const handleSave = async () => {
    if (!form.employee_name.trim()) { toast.error('Employee name is required'); return; }
    if (!form.amount) { toast.error('Salary amount is required'); return; }
    const doSave = async () => {
      setSaving(true);
      try {
        if (editingId) {
          await api.put(`/salaries/${editingId}`, form);
          toast.success('Updated');
        } else {
          await api.post('/salaries', form);
          toast.success('Salary saved');
        }
        setShowAdd(false);
        load(true);
        dataEvents.emit();
      }
      catch (err) { toast.error('Save failed: ' + (err.response?.data?.detail || '')); }
      finally { setSaving(false); }
    };
    if (editingId) { await doSave(); } else { await checkDuplicates('salary', form, api, doSave); }
  };

  return (
    <div className="space-y-4" data-testid="salaries-tab">
      <div className="flex justify-end">
        <Button onClick={openAdd} className="bg-navy-900 hover:bg-navy-800 text-white h-9 text-xs" data-testid="add-salary-btn"><Plus className="w-3.5 h-3.5 mr-1.5" /> Add Salary</Button>
      </div>

      <Card className="border border-slate-200/80 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <Table><TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
            <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Employee</TableHead>
            <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Position</TableHead>
            <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Date</TableHead>
            <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Amount</TableHead>
            <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Notes</TableHead>
            <TableHead className="w-12" />
          </TableRow></TableHeader><TableBody>
            {loading ? [1,2,3].map(i => (
              <TableRow key={`skel-${i}`}><TableCell colSpan={6}><Skeleton className="h-8 w-full rounded" /></TableCell></TableRow>
            )) : items.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="h-40">
                <div className="flex flex-col items-center justify-center text-center py-6">
                  <Users2 className="w-10 h-10 text-slate-300 mb-3" />
                  <h3 className="font-heading text-sm font-bold text-navy-900 mb-1">No salary records</h3>
                  <p className="text-xs text-slate-400 mb-3">Track employee salary payments</p>
                  <Button onClick={openAdd} variant="outline" size="sm" className="text-xs"><Plus className="w-3 h-3 mr-1" /> Add Salary</Button>
                </div>
              </TableCell></TableRow>
            ) : items.map((s, i) => (
              <TableRow key={s.id} className={`transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} hover:bg-teal-50/30`} data-testid={`salary-row-${i}`}>
                <TableCell className="text-xs font-semibold text-navy-900">{s.employee_name}</TableCell>
                <TableCell className="text-xs text-slate-500">{s.position}</TableCell>
                <TableCell className="text-xs tabular-nums text-slate-600">{s.payment_date}</TableCell>
                <TableCell className="text-xs text-right font-bold text-navy-900 tabular-nums">{fmt(s.amount)}</TableCell>
                <TableCell className="text-xs text-slate-400 max-w-[150px] truncate">{s.notes}</TableCell>
                <TableCell><div className="flex gap-0.5"><Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => openEdit(s)} data-testid={`edit-salary-${i}`}><FileText className="w-3.5 h-3.5 text-blue-500" /></Button><Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => requestDelete(s.id)} data-testid={`delete-salary-${i}`}><Trash2 className="w-3.5 h-3.5 text-red-400" /></Button></div></TableCell>
              </TableRow>
            ))}
          </TableBody></Table>
          {items.length > 0 && <div className="px-4 py-2.5 border-t border-slate-100 bg-slate-50/50"><p className="text-[11px] text-slate-400">{items.length} record{items.length !== 1 ? 's' : ''} &middot; Total: <span className="font-bold text-navy-900">{fmt(items.reduce((s, r) => s + (r.amount || 0), 0))}</span></p></div>}
        </div>
      </Card>

      <Dialog open={showAdd} onOpenChange={(v) => { if (!saving) setShowAdd(v); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle className="font-heading text-lg">{editingId ? 'Edit Salary' : 'Add Salary Payment'}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Employee Name *</Label><Input className="mt-1 h-9 text-sm" value={form.employee_name} onChange={(e) => updateField('employee_name', e.target.value)} placeholder="Full name" data-testid="form-employee-name" /></div>
            <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Position</Label><Input className="mt-1 h-9 text-sm" value={form.position} onChange={(e) => updateField('position', e.target.value)} placeholder="e.g., Head Chef, Waiter" data-testid="form-position" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Amount *</Label><Input className="mt-1 h-9 text-sm font-semibold" type="number" step="0.01" value={form.amount || ''} onChange={(e) => updateField('amount', parseFloat(e.target.value) || 0)} placeholder="0.00" data-testid="form-salary-amount" /></div>
              <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Payment Date</Label><Input className="mt-1 h-9 text-sm" type="date" value={form.payment_date} onChange={(e) => updateField('payment_date', e.target.value)} data-testid="form-payment-date" /></div>
            </div>
            <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Notes</Label><Textarea className="mt-1 text-sm min-h-[60px]" value={form.notes} onChange={(e) => updateField('notes', e.target.value)} placeholder="Optional notes" data-testid="form-salary-notes" /></div>
          </div>
          <div className="flex gap-3 pt-2"><Button variant="outline" className="h-9 text-xs" onClick={() => setShowAdd(false)} disabled={saving}>Cancel</Button><Button onClick={handleSave} disabled={saving} className="bg-navy-900 hover:bg-navy-800 text-white h-9 text-xs flex-1" data-testid="save-salary-btn">{saving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Plus className="w-3.5 h-3.5 mr-1.5" />} {editingId ? 'Update' : 'Save Salary'}</Button></div>
        </DialogContent>
      </Dialog>
      <DuplicateWarningDialog open={showWarning} onClose={cancelSave} onConfirm={confirmSave} duplicates={duplicates} saving={saving} />
      <ConfirmDeleteDialog open={deleteConfirm.open} onClose={cancelDelete} onConfirm={handleDeleteConfirm} message={deleteConfirm.message} />
    </div>
  );
}

// ======================== OTHER EXPENSES TAB ========================
function OtherExpensesTab({ api }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ title: '', category: 'Rent', amount: 0, expense_date: new Date().toISOString().split('T')[0], notes: '' });
  const [saving, setSaving] = useState(false);
  const { checking, duplicates, showWarning, confirmSave, cancelSave, checkDuplicates } = useDuplicateCheck();
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, id: null, message: '' });

  const load = useCallback(async (showSkeleton = false) => {
    if (showSkeleton) setLoading(true);
    try { const res = await api.get('/other-expenses'); setItems(res.data); }
    catch { toast.error('Failed to load expenses'); } finally { setLoading(false); }
  }, [api]);
  useEffect(() => { load(true); }, [load]);

  const requestDelete = (id) => setDeleteConfirm({ open: true, id, message: 'Are you sure you want to delete this expense?' });
  const handleDeleteConfirm = async () => {
    const { id } = deleteConfirm;
    setDeleteConfirm({ open: false, id: null, message: '' });
    const prev = items;
    setItems(cur => cur.filter(e => e.id !== id));
    dataEvents.emit();
    try { await api.delete(`/other-expenses/${id}`); toast.success('Deleted'); }
    catch { toast.error('Failed to delete'); setItems(prev); }
  };
  const cancelDelete = () => setDeleteConfirm({ open: false, id: null, message: '' });
  const updateField = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const openAdd = () => { setEditingId(null); setForm({ title: '', category: 'Rent', amount: 0, expense_date: new Date().toISOString().split('T')[0], notes: '' }); setShowAdd(true); };
  const openEdit = (record) => {
    setEditingId(record.id);
    setForm({ title: record.title || '', category: record.category || 'Rent', amount: record.amount || 0, expense_date: record.expense_date || '', notes: record.notes || '' });
    setShowAdd(true);
  };
  const handleSave = async () => {
    if (!form.title.trim()) { toast.error('Expense title is required'); return; }
    if (!form.amount) { toast.error('Amount is required'); return; }
    const doSave = async () => {
      setSaving(true);
      try {
        if (editingId) {
          await api.put(`/other-expenses/${editingId}`, form);
          toast.success('Updated');
        } else {
          await api.post('/other-expenses', form);
          toast.success('Expense saved');
        }
        setShowAdd(false);
        load(true);
        dataEvents.emit();
      }
      catch (err) { toast.error('Save failed: ' + (err.response?.data?.detail || '')); }
      finally { setSaving(false); }
    };
    if (editingId) { await doSave(); } else { await checkDuplicates('other_expense', form, api, doSave); }
  };

  const catColor = (c) => {
    const map = { Rent: 'bg-blue-100 text-blue-700', Electricity: 'bg-amber-100 text-amber-700', Water: 'bg-cyan-100 text-cyan-700', Gas: 'bg-orange-100 text-orange-700', Maintenance: 'bg-slate-100 text-slate-700', Equipment: 'bg-violet-100 text-violet-700', Insurance: 'bg-emerald-100 text-emerald-700', Marketing: 'bg-pink-100 text-pink-700' };
    return map[c] || 'bg-slate-100 text-slate-600';
  };

  return (
    <div className="space-y-4" data-testid="other-expenses-tab">
      <div className="flex justify-end">
        <Button onClick={openAdd} className="bg-navy-900 hover:bg-navy-800 text-white h-9 text-xs" data-testid="add-other-expense-btn"><Plus className="w-3.5 h-3.5 mr-1.5" /> Add Expense</Button>
      </div>

      <Card className="border border-slate-200/80 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <Table><TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
            <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Date</TableHead>
            <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Title</TableHead>
            <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Category</TableHead>
            <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Amount</TableHead>
            <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Notes</TableHead>
            <TableHead className="w-12" />
          </TableRow></TableHeader><TableBody>
            {loading ? [1,2,3].map(i => (
              <TableRow key={`skel-${i}`}><TableCell colSpan={6}><Skeleton className="h-8 w-full rounded" /></TableCell></TableRow>
            )) : items.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="h-40">
                <div className="flex flex-col items-center justify-center text-center py-6">
                  <Wrench className="w-10 h-10 text-slate-300 mb-3" />
                  <h3 className="font-heading text-sm font-bold text-navy-900 mb-1">No other expenses</h3>
                  <p className="text-xs text-slate-400 mb-3">Track rent, utilities, and more</p>
                  <Button onClick={openAdd} variant="outline" size="sm" className="text-xs"><Plus className="w-3 h-3 mr-1" /> Add Expense</Button>
                </div>
              </TableCell></TableRow>
            ) : items.map((e, i) => (
              <TableRow key={e.id} className={`transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} hover:bg-teal-50/30`} data-testid={`other-expense-row-${i}`}>
                <TableCell className="text-xs tabular-nums text-slate-600">{e.expense_date}</TableCell>
                <TableCell className="text-xs font-semibold text-navy-900">{e.title}</TableCell>
                <TableCell><Badge className={`text-[10px] border-0 ${catColor(e.category)}`}>{e.category}</Badge></TableCell>
                <TableCell className="text-xs text-right font-bold text-navy-900 tabular-nums">{fmt(e.amount)}</TableCell>
                <TableCell className="text-xs text-slate-400 max-w-[150px] truncate">{e.notes}</TableCell>
                <TableCell><div className="flex gap-0.5"><Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => openEdit(e)} data-testid={`edit-other-expense-${i}`}><FileText className="w-3.5 h-3.5 text-blue-500" /></Button><Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => requestDelete(e.id)} data-testid={`delete-other-expense-${i}`}><Trash2 className="w-3.5 h-3.5 text-red-400" /></Button></div></TableCell>
              </TableRow>
            ))}
          </TableBody></Table>
          {items.length > 0 && <div className="px-4 py-2.5 border-t border-slate-100 bg-slate-50/50"><p className="text-[11px] text-slate-400">{items.length} expense{items.length !== 1 ? 's' : ''} &middot; Total: <span className="font-bold text-navy-900">{fmt(items.reduce((s, r) => s + (r.amount || 0), 0))}</span></p></div>}
        </div>
      </Card>

      <Dialog open={showAdd} onOpenChange={(v) => { if (!saving) setShowAdd(v); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle className="font-heading text-lg">{editingId ? 'Edit Expense' : 'Add Expense'}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Expense Title *</Label><Input className="mt-1 h-9 text-sm" value={form.title} onChange={(e) => updateField('title', e.target.value)} placeholder="e.g., March Rent" data-testid="form-expense-title" /></div>
            <div>
              <Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Category</Label>
              <Select value={form.category} onValueChange={(v) => updateField('category', v)}>
                <SelectTrigger className="mt-1 h-9 text-sm" data-testid="form-expense-category"><SelectValue /></SelectTrigger>
                <SelectContent>{OTHER_CATEGORIES.map(c => <SelectItem key={c} value={c} className="text-sm">{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Amount *</Label><Input className="mt-1 h-9 text-sm font-semibold" type="number" step="0.01" value={form.amount || ''} onChange={(e) => updateField('amount', parseFloat(e.target.value) || 0)} placeholder="0.00" data-testid="form-expense-amount" /></div>
              <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Date</Label><Input className="mt-1 h-9 text-sm" type="date" value={form.expense_date} onChange={(e) => updateField('expense_date', e.target.value)} data-testid="form-expense-date" /></div>
            </div>
            <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Notes</Label><Textarea className="mt-1 text-sm min-h-[60px]" value={form.notes} onChange={(e) => updateField('notes', e.target.value)} placeholder="Optional notes" data-testid="form-expense-notes" /></div>
          </div>
          <div className="flex gap-3 pt-2"><Button variant="outline" className="h-9 text-xs" onClick={() => setShowAdd(false)} disabled={saving}>Cancel</Button><Button onClick={handleSave} disabled={saving} className="bg-navy-900 hover:bg-navy-800 text-white h-9 text-xs flex-1" data-testid="save-other-expense-btn">{saving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Plus className="w-3.5 h-3.5 mr-1.5" />} {editingId ? 'Update' : 'Save Expense'}</Button></div>
        </DialogContent>
      </Dialog>
      <DuplicateWarningDialog open={showWarning} onClose={cancelSave} onConfirm={confirmSave} duplicates={duplicates} saving={saving} />
      <ConfirmDeleteDialog open={deleteConfirm.open} onClose={cancelDelete} onConfirm={handleDeleteConfirm} message={deleteConfirm.message} />
    </div>
  );
}

// ======================== MAIN EXPENSES PAGE ========================
export default function ExpensesPage() {
  const { api } = useAuth();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState(() => {
    const tab = location.state?.tab;
    if (tab === 'raw_materials' || tab === 'salaries' || tab === 'other') return tab;
    return 'raw_materials';
  });

  // Update tab when navigating from dashboard with state
  useEffect(() => {
    const tab = location.state?.tab;
    if (tab === 'raw_materials' || tab === 'salaries' || tab === 'other') {
      setActiveTab(tab);
      // Clear the state so browser back doesn't re-apply it
      window.history.replaceState({}, '');
    }
  }, [location.state]);

  return (
    <div className="space-y-6 max-w-[1400px]" data-testid="expenses-page">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight">Expenses</h1>
        <p className="text-xs text-slate-400 mt-0.5">Manage all restaurant expenses in one place</p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-slate-100 h-9" data-testid="expense-category-tabs">
          <TabsTrigger value="raw_materials" className="text-xs font-semibold px-5 gap-1.5" data-testid="tab-raw-materials">
            <Beef className="w-3.5 h-3.5" /> Raw Materials
          </TabsTrigger>
          <TabsTrigger value="salaries" className="text-xs font-semibold px-5 gap-1.5" data-testid="tab-salaries">
            <Users2 className="w-3.5 h-3.5" /> Salaries
          </TabsTrigger>
          <TabsTrigger value="other" className="text-xs font-semibold px-5 gap-1.5" data-testid="tab-other-expenses">
            <Wrench className="w-3.5 h-3.5" /> Other Expenses
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Keep all tabs mounted — CSS show/hide prevents unmount/remount DOM conflicts */}
      <div style={{ display: activeTab === 'raw_materials' ? 'block' : 'none' }}>
        <RawMaterialsTab api={api} />
      </div>
      <div style={{ display: activeTab === 'salaries' ? 'block' : 'none' }}>
        <SalariesTab api={api} />
      </div>
      <div style={{ display: activeTab === 'other' ? 'block' : 'none' }}>
        <OtherExpensesTab api={api} />
      </div>
    </div>
  );
}
