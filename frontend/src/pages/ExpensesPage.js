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
  Receipt, Beef, Users2, Wrench, FileSpreadsheet
} from 'lucide-react';
import { useDuplicateCheck, DuplicateWarningDialog } from '@/components/DuplicateCheck';
import { ConfirmDeleteDialog } from '@/components/ConfirmDeleteDialog';
import { ConfirmSaveDialog } from '@/components/ConfirmSaveDialog';

function fmt(n) { return n != null ? `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '$0.00'; }
let _keySeq = 0;
function nextKey() { return `k${++_keySeq}_${Date.now()}`; }
function mkItem(raw_name = '', quantity = 1, pack_size = '', unit_price = 0, total = 0, pack_unit = null, total_case_weight = null, normalized_price_per_lb = null, pack_parse_status = null, warning = false, warning_detail = '', confidence_score = null, confidence_level = null, validation_errors = [], valid_calc = null, _reviewed = false, confidence_reason = null, needs_review = false, review_reason = null) {
  return { _key: nextKey(), raw_name, quantity, pack_size, unit_price, total, pack_unit, total_case_weight, normalized_price_per_lb, pack_parse_status, _warning: warning, _warning_detail: warning_detail, confidence_score, confidence_level, validation_errors, valid_calc, _reviewed, confidence_reason, needs_review, review_reason, _fixing: false };
}

// Client-side re-validation (mirrors backend hard gates)
function revalidateItem(item) {
  const qty = parseFloat(item.quantity) || 0;
  const up = parseFloat(item.unit_price) || 0;
  const total = parseFloat(item.total) || 0;
  const name = (item.raw_name || '').trim();
  const errors = [];
  let hardFail = false;
  let score = 0;
  let validCalc = false;

  // Gate 1: Math
  if (qty > 0 && up > 0 && total > 0) {
    const expected = Math.round(qty * up * 100) / 100;
    const tolerance = Math.max(0.02, 0.01 * total);
    if (Math.abs(expected - total) <= tolerance) { validCalc = true; score += 40; }
    else { hardFail = true; errors.push(`Math mismatch: ${qty}×$${up.toFixed(2)}=$${expected.toFixed(2)} ≠ $${total.toFixed(2)}`); }
  } else if (total > 0 && (qty === 0 || up === 0)) { hardFail = true; errors.push('total exists but qty or price missing'); }
  else if (qty > 0 && up > 0 && total === 0) { hardFail = true; errors.push('total is missing'); }
  else { hardFail = true; errors.push('missing core numeric fields'); }

  // Gate 2: Required fields
  const missing = [];
  if (!name) { missing.push('item_name'); hardFail = true; }
  if (qty <= 0) missing.push('qty');
  if (up <= 0) missing.push('unit_price');
  if (total <= 0) missing.push('line_total');
  if (missing.length === 0) score += 20; else errors.push(`missing: ${missing.join(', ')}`);

  // Gate 3: Pack size
  const packRaw = (item.pack_size || '').trim();
  const packStatus = item.pack_parse_status;
  if (packRaw) {
    if (packStatus === 'parsed') score += 20;
    else if (packStatus === 'failed') { hardFail = true; errors.push(`Pack size parse failed: "${packRaw}"`); }
  } else { score += 15; }

  // Gate 4: Name quality
  if (name && name.length >= 2) { const alpha = [...name].filter(c => /[a-zA-Z]/.test(c)).length; if (alpha >= name.length * 0.3) score += 20; else errors.push('Garbled item name'); }
  else errors.push('Item name too short or missing');

  // Gate 5: Suspicious
  if (qty > 0 && up > 0 && qty === up) { hardFail = true; errors.push('qty equals price — suspicious'); }

  score = Math.max(0, Math.min(100, score));
  const level = hardFail ? 'unverified' : score >= 85 ? 'trusted' : 'unverified';

  let reason;
  if (level === 'trusted') reason = 'All checks passed';
  else if (!validCalc && qty > 0 && up > 0 && total > 0) reason = 'Math mismatch (qty × price ≠ total)';
  else if (!name) reason = 'Missing item name';
  else if (packRaw && packStatus === 'failed') reason = 'Pack size could not be parsed';
  else if (missing.length) reason = `Missing fields: ${missing.join(', ')}`;
  else reason = 'Needs review';

  const needsReview = level !== 'trusted';
  return { ...item, valid_calc: validCalc, validation_errors: errors, confidence_score: score, confidence_level: level, confidence_reason: reason, needs_review: needsReview, review_reason: needsReview ? reason : null, _reviewed: false, _fixing: false };
}

const OTHER_CATEGORIES = ['Utilities', 'Taxes', 'Maintenance & Repairs', 'Software & Subscriptions', 'Services', 'Rent / Facility', 'Miscellaneous'];

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
    <div ref={wrapperRef} className="relative">
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
  const [uploadFiles, setUploadFiles] = useState([]);
  const [uploadPreviews, setUploadPreviews] = useState([]);
  const fileImageRef = useRef(null);
  const filePdfRef = useRef(null);
  const fileCameraRef = useRef(null);
  const fileExcelRef = useRef(null);
  const [knownItems, setKnownItems] = useState([]);
  const { checking, duplicates, showWarning, confirmSave, cancelSave, checkDuplicates } = useDuplicateCheck();
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, id: null, message: '', type: null, idx: null });
  const [receiptId, setReceiptId] = useState(null);
  const [parsingMethod, setParsingMethod] = useState(null);
  const [showConfirmSave, setShowConfirmSave] = useState(false);
  const [reviewMode, setReviewMode] = useState(false);

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
    uploadPreviews.forEach(u => URL.revokeObjectURL(u));
    setUploadFiles([]); setUploadPreviews([]); setShowAdd(true); setReviewMode(false);
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
      items: (record.items || []).map(it => mkItem(it.raw_name || '', it.quantity || 0, it.pack_size_raw || it.pack_size || '', it.unit_price || 0, it.total || 0, it.pack_unit || null, it.total_case_weight || null, it.normalized_price_per_lb || null, it.pack_parse_status || null, false, '', it.confidence_score ?? null, it.confidence_level || null, it.validation_errors || [], it.valid_calc ?? null, it.confidence_level === 'trusted', it.confidence_reason || null, !!it.needs_review, it.review_reason || null)),
      subtotal: record.subtotal || 0,
      tax: record.tax || 0,
      total: record.total || 0,
    });
    if (uploadPreviews.length) uploadPreviews.forEach(u => URL.revokeObjectURL(u));
    setUploadFiles([]); setUploadPreviews([]); setShowAdd(true); setReviewMode(false);
    api.get('/items').then(res => {
      const names = [];
      (res.data || []).forEach(item => { names.push(item.name); (item.aliases || []).forEach(a => names.push(a.alias_name)); });
      setKnownItems([...new Set(names)].sort());
    }).catch(() => {});
  };

  const handleFileSelect = (f) => {
    if (!f) return;
    setUploadFiles(prev => [...prev, f]);
    if (f.type.startsWith('image/')) {
      setUploadPreviews(prev => [...prev, URL.createObjectURL(f)]);
    } else {
      setUploadPreviews(prev => [...prev, null]);
    }
  };
  const removeFile = (idx) => {
    setUploadFiles(prev => prev.filter((_, i) => i !== idx));
    setUploadPreviews(prev => { if (prev[idx]) URL.revokeObjectURL(prev[idx]); return prev.filter((_, i) => i !== idx); });
  };
  const clearAllFiles = () => {
    uploadPreviews.forEach(u => { if (u) URL.revokeObjectURL(u); });
    setUploadFiles([]); setUploadPreviews([]);
  };
  const isExcelFile = (f) => { const n = (f?.name || '').toLowerCase(); return n.endsWith('.xlsx') || n.endsWith('.xls') || n.endsWith('.csv'); };

  const extractingRef = useRef(false);
  const handleExtract = async () => {
    if (!uploadFiles.length || extractingRef.current) return;
    extractingRef.current = true;
    setExtracting(true);
    try {
      const fd = new FormData();
      // Send all files under 'files' key for multi-image, or 'file' for single+excel
      if (uploadFiles.length === 1 && isExcelFile(uploadFiles[0])) {
        fd.append('file', uploadFiles[0]);
      } else {
        uploadFiles.forEach(f => fd.append('files', f));
      }
      fd.append('document_type', 'purchase_invoice');
      const ep = (uploadFiles.length === 1 && isExcelFile(uploadFiles[0])) ? '/upload/parse-excel' : '/upload/extract';
      const res = await api.post(ep, fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 90000 });
      const d = res.data?.extracted_data || {};
      const items = Array.isArray(d.items) ? d.items : [];
      const hasWarnings = d._has_warnings || false;
      setForm({
        supplier_name: d.supplier_name || '',
        invoice_number: d.invoice_number || '',
        invoice_date: d.invoice_date || new Date().toISOString().split('T')[0],
        items: items.length > 0
          ? items.map(it => mkItem(it.raw_name || '', parseFloat(it.quantity) || 0, it.pack_size_raw || it.pack_size || '', parseFloat(it.unit_price) || 0, parseFloat(it.total) || 0, it.pack_unit || null, it.total_case_weight != null ? parseFloat(it.total_case_weight) : null, it.normalized_price_per_lb != null ? parseFloat(it.normalized_price_per_lb) : null, it.pack_parse_status || null, !!it._warning, it._warning_detail || '', it.confidence_score ?? null, it.confidence_level || null, it.validation_errors || [], it.valid_calc ?? null, false, it.confidence_reason || null, !!it.needs_review, it.review_reason || null))
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
      // Check for items that need review
      const uncertainCount = items.filter(it => it.needs_review || ((it.confidence_level || 'trusted') !== 'trusted')).length;
      if (uncertainCount > 0) {
        toast.warning(`${uncertainCount} item${uncertainCount > 1 ? 's' : ''} need${uncertainCount === 1 ? 's' : ''} review — check highlighted rows`);
        setReviewMode(true);
      } else if (hasWarnings) {
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

  const handleSave = () => {
    if (!form.supplier_name.trim()) { toast.error('Vendor name is required'); return; }
    setShowConfirmSave(true);
  };
  const executeSave = async () => {
    setShowConfirmSave(false);
    const doSave = async () => {
      setSaving(true);
      try {
        const payload = { ...form, items: form.items.map(({ _key, _warning, _warning_detail, _reviewed, _fixing, ...rest }) => ({ ...rest, pack_size: rest.pack_size || '' })) };
        delete payload._has_warnings; delete payload._warnings; delete payload._subtotal_warning; delete payload._total_warning; delete payload._date_warning;
        if (editingId) {
          await api.put(`/purchases/${editingId}`, payload);
          toast.success('Updated');
        } else {
          const res = await api.post('/purchases', payload);
          if (uploadFiles.length > 0 && res.data?.id) {
            try {
              const fd = new FormData();
              fd.append('file', uploadFiles[0]);
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
        if (receiptId || uploadFiles.length > 0) {
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
                <TableCell className="text-xs text-center text-slate-500">
                  <span>{(p.items || []).length}</span>
                  {(() => {
                    const reviewCount = (p.items || []).filter(it => it.needs_review).length;
                    return reviewCount > 0 ? (
                      <span className="ml-1 inline-flex items-center gap-0.5 text-[9px] font-semibold text-amber-600" title={`${reviewCount} item${reviewCount !== 1 ? 's' : ''} need review`} data-testid={`review-count-${i}`}>
                        <AlertTriangle className="w-2.5 h-2.5" />{reviewCount}
                      </span>
                    ) : null;
                  })()}
                </TableCell>
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
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="font-heading text-lg">Purchase Details</DialogTitle></DialogHeader>
          {selected && <div className="space-y-5">
            <div className="grid grid-cols-3 gap-4">{[['Vendor', selected.supplier_name], ['Invoice #', selected.invoice_number], ['Date', selected.invoice_date]].map(([l, v]) => <div key={l}><p className="text-[10px] font-bold text-slate-400 uppercase">{l}</p><p className="text-sm font-semibold text-navy-900 mt-0.5">{v}</p></div>)}</div>
            {/* Review summary banner in detail view */}
            {(() => {
              const reviewItems = (selected.items || []).filter(it => it.needs_review);
              if (reviewItems.length === 0) return null;
              return (
                <div className="flex items-center gap-2.5 p-2.5 rounded-lg bg-amber-50 border border-amber-200" data-testid="detail-review-banner">
                  <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" />
                  <p className="text-xs text-amber-800">
                    <span className="font-semibold">{reviewItems.length} item{reviewItems.length !== 1 ? 's' : ''}</span> flagged for review — edit this invoice to resolve
                  </p>
                </div>
              );
            })()}
            <Separator />
            <Table><TableHeader><TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
              <TableHead className="text-[10px] font-bold text-slate-500 uppercase w-8">Status</TableHead>
              <TableHead className="text-[10px] font-bold text-slate-500 uppercase">Item</TableHead>
              <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right">Qty</TableHead>
              <TableHead className="text-[10px] font-bold text-slate-500 uppercase">Pack Size</TableHead>
              <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right">Price</TableHead>
              <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right">Total</TableHead>
              <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right">Case Wt</TableHead>
              <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right">$/LB</TableHead>
            </TableRow></TableHeader><TableBody>
              {(selected.items || []).map((it, i) => {
                const flagged = it.needs_review;
                return (
                <TableRow key={i} className={`${flagged ? 'bg-amber-50/60' : i % 2 === 0 ? '' : 'bg-slate-50/40'}`} data-testid={`detail-item-row-${i}`}>
                  <TableCell className="text-center">
                    {flagged ? (
                      <span className="inline-flex w-5 h-5 rounded-full bg-amber-100 items-center justify-center" title={it.review_reason || 'Needs review'} data-testid={`detail-review-dot-${i}`}>
                        <AlertTriangle className="w-3 h-3 text-amber-600" />
                      </span>
                    ) : it.confidence_level ? (
                      <span className="inline-flex w-5 h-5 rounded-full bg-emerald-100 items-center justify-center" title="Verified" data-testid={`detail-ok-dot-${i}`}>
                        <svg className="w-3 h-3 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                      </span>
                    ) : <span className="text-slate-300">—</span>}
                  </TableCell>
                  <TableCell>
                    <div className="text-sm font-medium">{it.raw_name}</div>
                    {flagged && it.review_reason && <div className="text-[10px] text-amber-600 mt-0.5" data-testid={`detail-review-reason-${i}`}>{it.review_reason}</div>}
                  </TableCell>
                  <TableCell className="text-sm text-right tabular-nums">{it.quantity}</TableCell>
                  <TableCell className="text-sm text-slate-500">{it.pack_size_raw || it.pack_size || '—'}</TableCell>
                  <TableCell className="text-sm text-right tabular-nums">{fmt(it.unit_price)}</TableCell>
                  <TableCell className="text-sm text-right font-semibold tabular-nums">{fmt(it.total)}</TableCell>
                  <TableCell className="text-sm text-right tabular-nums">{it.pack_parse_status === 'parsed' && it.total_case_weight != null ? `${it.total_case_weight} ${it.pack_unit || ''}`.trim() : '—'}</TableCell>
                  <TableCell className="text-sm text-right tabular-nums">{it.normalized_price_per_lb != null && it.normalized_price_per_lb > 0 ? <span className="text-teal-700 font-semibold">{fmt(it.normalized_price_per_lb)}</span> : <span className="text-slate-300">—</span>}</TableCell>
                </TableRow>
                );
              })}
            </TableBody></Table>
            <div className="flex justify-end"><div className="text-right space-y-1 min-w-[200px]"><div className="flex justify-between text-sm"><span className="text-slate-500">Subtotal</span><span className="tabular-nums">{fmt(selected.subtotal)}</span></div><div className="flex justify-between text-sm"><span className="text-slate-500">Tax</span><span className="tabular-nums">{fmt(selected.tax)}</span></div><Separator className="my-1" /><div className="flex justify-between text-base font-bold"><span>Total</span><span className="tabular-nums">{fmt(selected.total)}</span></div></div></div>
          </div>}
        </DialogContent>
      </Dialog>

      {/* Add Dialog — prevent close during save */}
      <Dialog open={showAdd} onOpenChange={(v) => { if (!saving && !extracting) setShowAdd(v); }}>
        <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="font-heading text-lg">{editingId ? 'Edit Purchase' : 'Add Raw Material Purchase'}</DialogTitle></DialogHeader>
          <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/50 p-4" data-testid="raw-material-upload-zone">
            {uploadFiles.length > 0 ? <div className="space-y-3">
              {/* Page thumbnails */}
              <div className="flex flex-wrap gap-2">
                {uploadFiles.map((uf, idx) => (
                  <div key={idx} className="relative group rounded-lg border border-slate-200 bg-white p-1.5 w-[80px]" data-testid={`upload-page-${idx}`}>
                    {uploadPreviews[idx] ? <img src={uploadPreviews[idx]} alt={`Page ${idx+1}`} className="w-full h-14 object-cover rounded" /> : <div className="w-full h-14 rounded bg-slate-100 flex items-center justify-center">{isExcelFile(uf) ? <Sheet className="w-5 h-5 text-slate-400" /> : <FileText className="w-5 h-5 text-slate-400" />}</div>}
                    <p className="text-[9px] font-semibold text-center text-slate-500 mt-1 truncate">Page {idx+1}</p>
                    <button onClick={() => removeFile(idx)} className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-red-500 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity" data-testid={`remove-page-${idx}`}><X className="w-3 h-3" /></button>
                  </div>
                ))}
                {/* Add another image button */}
                <label className="w-[80px] h-[82px] rounded-lg border-2 border-dashed border-slate-200 flex flex-col items-center justify-center cursor-pointer hover:border-teal-300 hover:bg-teal-50/30 transition-colors" data-testid="add-another-image-btn">
                  <Plus className="w-5 h-5 text-slate-400" />
                  <span className="text-[9px] font-semibold text-slate-400 mt-0.5">Add Page</span>
                  <input type="file" accept="image/*,.pdf" className="hidden" onChange={(e) => handleFileSelect(e.target.files?.[0])} />
                </label>
              </div>
              <div className="flex items-center justify-between">
                <p className="text-[10px] text-slate-400">{uploadFiles.length} page{uploadFiles.length !== 1 ? 's' : ''} selected</p>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" className="h-8 text-xs" onClick={clearAllFiles}><X className="w-3 h-3 mr-1" /> Clear All</Button>
                  <Button size="sm" className="h-8 text-xs bg-teal-600 hover:bg-teal-700 text-white" onClick={handleExtract} disabled={extracting} data-testid="raw-material-extract-btn">{extracting ? <><Loader2 className="w-3 h-3 animate-spin mr-1" /> Extracting...</> : <><Sparkles className="w-3 h-3 mr-1" /> Extract Data</>}</Button>
                </div>
              </div>
            </div>
            : <div className="space-y-3"><div className="flex items-center gap-2.5"><div className="w-9 h-9 rounded-lg bg-teal-50 border border-teal-200 flex items-center justify-center flex-shrink-0"><Upload className="w-4 h-4 text-teal-600" /></div><div><p className="text-xs font-semibold text-navy-900">Upload a purchase invoice</p><p className="text-[10px] text-slate-400">AI will extract vendor, items, and totals — supports multi-page documents</p></div></div>
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
          {form._has_warnings && !reviewMode && (
            <div className="flex items-start gap-2.5 p-3 rounded-lg bg-amber-50 border border-amber-200" data-testid="ocr-warning-banner">
              <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-amber-800">Review needed</p>
                <p className="text-[10px] text-amber-600 mt-0.5">Some extracted values may be inaccurate. Fields highlighted in yellow need your attention.</p>
              </div>
            </div>
          )}
          {/* Confidence review banner */}
          {(() => {
            const uncertain = form.items.filter(it => (it.needs_review || (it.confidence_level && it.confidence_level !== 'trusted')) && !it._reviewed);
            const total = form.items.filter(it => it.confidence_level || it.needs_review).length;
            const trustedCount = form.items.filter(it => !it.needs_review && it.confidence_level === 'trusted').length;
            if (total === 0 || uncertain.length === 0) return null;
            return (
              <div className="flex items-center gap-3 p-3 rounded-lg bg-indigo-50 border border-indigo-200" data-testid="confidence-review-banner">
                <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0">
                  <Eye className="w-4 h-4 text-indigo-600" />
                </div>
                <div className="flex-1">
                  <p className="text-xs font-semibold text-indigo-900">
                    {uncertain.length} of {total} items need review
                  </p>
                  <p className="text-[10px] text-indigo-600 mt-0.5">
                    {trustedCount} items auto-verified. Review only the uncertain rows below.
                  </p>
                </div>
                <button
                  onClick={() => setReviewMode(r => !r)}
                  className={`text-[10px] font-semibold px-3 py-1.5 rounded-lg transition-colors ${reviewMode ? 'bg-indigo-600 text-white' : 'bg-white border border-indigo-200 text-indigo-700 hover:bg-indigo-100'}`}
                  data-testid="review-mode-toggle"
                >
                  {reviewMode ? 'Show All Items' : 'Focus Review'}
                </button>
              </div>
            );
          })()}
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
              {/* Column headers */}
              <div className="grid grid-cols-[24px_minmax(140px,2fr)_65px_100px_85px_85px_65px_65px_32px] gap-1.5 items-center px-2 mb-1">
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider text-center" title="Confidence"></span>
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">Item Name</span>
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider text-center">Qty</span>
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider text-center">Pack Size</span>
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider text-right">Price</span>
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider text-right">Total</span>
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider text-center">Case Wt</span>
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider text-right">$/LB</span>
                <span />
              </div>
              <div className="space-y-1.5">{form.items.filter(item => {
                if (!reviewMode) return true;
                return (item.needs_review || (item.confidence_level && item.confidence_level !== 'trusted')) && !item._reviewed;
              }).map((item) => {
                const i = form.items.indexOf(item);
                const cl = item.confidence_level;
                const isUncertain = (item.needs_review || (cl && cl !== 'trusted')) && !item._reviewed;
                const isTrusted = (!item.needs_review && cl === 'trusted') || item._reviewed;
                const confidenceDot = isTrusted ? 'bg-emerald-500' : cl === 'unverified' ? 'bg-amber-500' : 'bg-slate-300';
                const confidenceTitle = item._reviewed ? 'Confirmed by user' : cl === 'trusted' ? 'Trusted — auto-verified' : cl === 'unverified' ? 'Unverified — needs review' : '';
                const rowBorder = item._fixing ? 'border-blue-300 bg-blue-50/40 ring-1 ring-blue-200' : isUncertain ? 'border-amber-200 bg-amber-50/40' : item._reviewed ? 'bg-emerald-50/30 border border-emerald-200' : item._warning ? 'bg-amber-50 border border-amber-200' : 'bg-slate-50';
                const fixHighlight = item._fixing ? 'ring-1 ring-blue-300 border-blue-300' : '';
                return (
                <div key={item._key} className={`rounded-lg p-2 border ${rowBorder}`} data-testid={`line-item-${i}`}>
                  <div className="grid grid-cols-[24px_minmax(140px,2fr)_65px_100px_85px_85px_65px_65px_32px] gap-1.5 items-center">
                    {/* Confidence indicator */}
                    <div className="flex flex-col items-center gap-0.5" title={confidenceTitle} data-testid={`confidence-dot-${i}`}>
                      <div className={`w-3 h-3 rounded-full ${confidenceDot} flex items-center justify-center`}>
                        {isTrusted && <svg className="w-2 h-2 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                      </div>
                    </div>
                    <div className="min-w-0">
                      <ItemAutocomplete value={item.raw_name} onChange={(v) => { updateItem(i, 'raw_name', v); if (isUncertain || item._fixing) { setForm(f => { const it = [...f.items]; it[i] = revalidateItem({...it[i], raw_name: v}); return {...f, items: it}; }); } }} knownItems={knownItems} index={i} />
                    </div>
                    <Input className={`text-xs h-8 text-center tabular-nums ${fixHighlight} ${item._warning && (!item.quantity) ? 'border-amber-300' : ''}`} type="number" placeholder="Qty" value={item.quantity || ''} onChange={(e) => { const val = parseFloat(e.target.value) || 0; updateItem(i, 'quantity', val); if (isUncertain || item._fixing) { setForm(f => { const it = [...f.items]; const newTotal = Math.round(val * (parseFloat(it[i].unit_price)||0) * 100) / 100; it[i] = revalidateItem({...it[i], quantity: val, total: newTotal}); return {...f, items: it}; }); } }} data-testid={`line-item-qty-${i}`} />
                    <Input className="text-xs h-8 text-center tabular-nums" type="text" placeholder="10/4 LB" value={item.pack_size || ''} onChange={(e) => updateItem(i, 'pack_size', e.target.value)} data-testid={`line-item-pack-size-${i}`} />
                    <Input className={`text-xs h-8 text-right tabular-nums ${fixHighlight} ${item._warning && (!item.unit_price) ? 'border-amber-300' : ''}`} type="number" step="0.01" placeholder="Price" value={item.unit_price || ''} onChange={(e) => { const val = parseFloat(e.target.value) || 0; updateItem(i, 'unit_price', val); if (isUncertain || item._fixing) { setForm(f => { const it = [...f.items]; const newTotal = Math.round((parseFloat(it[i].quantity)||0) * val * 100) / 100; it[i] = revalidateItem({...it[i], unit_price: val, total: newTotal}); return {...f, items: it}; }); } }} data-testid={`line-item-price-${i}`} />
                    <div className={`text-xs h-8 flex items-center justify-end font-semibold tabular-nums px-2 rounded-md bg-slate-100 border border-slate-200 text-slate-700 select-none ${item._warning ? 'border-amber-300 bg-amber-50' : ''}`} data-testid={`line-item-total-${i}`}>{item.total ? `$${Number(item.total).toFixed(2)}` : '$0.00'}</div>
                    <div className={`text-[10px] h-8 flex items-center justify-center tabular-nums rounded-md border select-none ${item.pack_parse_status === 'failed' ? 'bg-red-50 border-red-200 text-red-400' : 'bg-slate-100 border-slate-200 text-slate-500'}`} data-testid={`line-item-casewt-${i}`}>{item.pack_parse_status === 'parsed' && item.total_case_weight != null ? `${item.total_case_weight} ${item.pack_unit || ''}`.trim() : '—'}</div>
                    <div className={`text-[10px] h-8 flex items-center justify-end tabular-nums rounded-md px-1 select-none ${isUncertain ? 'text-slate-300 bg-slate-100 border border-slate-200' : item.normalized_price_per_lb != null && item.normalized_price_per_lb > 0 ? 'font-semibold text-teal-700 bg-teal-50 border border-teal-200' : item.pack_parse_status === 'failed' ? 'text-red-400 bg-red-50 border border-red-200' : 'text-slate-300 bg-slate-100 border border-slate-200'}`} data-testid={`line-item-nup-${i}`}>{isUncertain ? '—' : (item.normalized_price_per_lb != null && item.normalized_price_per_lb > 0 ? `$${item.normalized_price_per_lb.toFixed(2)}` : '—')}</div>
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0 flex-shrink-0" onClick={() => requestDeleteItem(i)} data-testid={`delete-line-item-${i}`}><Trash2 className="w-3 h-3 text-red-400" /></Button>
                  </div>
                  {/* Status + reason + actions row */}
                  {(cl || item.needs_review) && (
                    <div className="flex items-center gap-2 mt-1.5 pl-7">
                      {isTrusted ? (
                        <span className="inline-flex items-center gap-1 text-[9px] font-semibold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full" data-testid={`status-badge-${i}`}>
                          <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                          {item._reviewed ? 'Confirmed' : 'Trusted'}
                        </span>
                      ) : (
                        <>
                          <span className="inline-flex items-center gap-1 text-[9px] font-semibold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full" data-testid={`status-badge-${i}`}>
                            <AlertTriangle className="w-2.5 h-2.5" /> Needs Review
                          </span>
                          <span className="text-[9px] text-amber-600" data-testid={`review-reason-${i}`}>{item.review_reason || item.confidence_reason || item.validation_errors?.[0] || 'Needs review'}</span>
                          <div className="ml-auto flex items-center gap-1.5">
                            <button
                              className={`text-[9px] font-semibold px-2 py-0.5 rounded transition-colors ${item._fixing ? 'text-blue-700 bg-blue-200' : 'text-blue-700 bg-blue-100 hover:bg-blue-200'}`}
                              onClick={() => setForm(f => {
                                const it = [...f.items];
                                it[i] = { ...it[i], _fixing: !it[i]._fixing };
                                return { ...f, items: it };
                              })}
                              data-testid={`fix-item-${i}`}
                            >{item._fixing ? 'Done Fixing' : 'Fix'}</button>
                            <button
                              className="text-[9px] font-semibold text-emerald-700 bg-emerald-100 hover:bg-emerald-200 px-2 py-0.5 rounded transition-colors"
                              onClick={() => setForm(f => {
                                const it = [...f.items];
                                it[i] = { ...it[i], _reviewed: true, _fixing: false };
                                return { ...f, items: it };
                              })}
                              data-testid={`accept-item-${i}`}
                            >Accept</button>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                  {item._warning_detail && !isUncertain && !cl && <p className="text-[9px] text-amber-600 mt-1 pl-7"><AlertTriangle className="w-2.5 h-2.5 inline mr-0.5" />{item._warning_detail}</p>}
                </div>
                );
              })}</div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Subtotal {form._subtotal_warning && <AlertTriangle className="w-3 h-3 inline text-amber-500" />}</Label><div className={`mt-1 h-9 flex items-center px-3 text-sm tabular-nums rounded-md border select-none ${form._subtotal_warning ? 'border-amber-300 bg-amber-50/50 text-amber-900' : 'border-slate-200 bg-slate-100 text-slate-700'}`} data-testid="form-subtotal">{fmt(form.subtotal)}</div></div>
              <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Tax</Label><Input className="mt-1 h-9 text-sm" type="number" step="0.01" value={form.tax || ''} onChange={(e) => { const tax = parseFloat(e.target.value) || 0; setForm(f => ({ ...f, tax, total: round2(f.subtotal + tax) })); }} data-testid="form-tax" /></div>
              <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Total {form._total_warning && <AlertTriangle className="w-3 h-3 inline text-amber-500" />}</Label><div className={`mt-1 h-9 flex items-center px-3 text-sm font-bold tabular-nums rounded-md border select-none ${form._total_warning ? 'border-amber-300 bg-amber-50/50 text-amber-900' : 'border-slate-200 bg-slate-100 text-navy-900'}`} data-testid="form-total">{fmt(form.total)}</div></div>
            </div>
          </div>
          <div className="flex gap-3 pt-2"><Button variant="outline" className="h-9 text-xs" onClick={() => setShowAdd(false)} disabled={saving}>Cancel</Button><Button onClick={handleSave} disabled={saving} className="bg-navy-900 hover:bg-navy-800 text-white h-9 text-xs flex-1" data-testid="save-raw-material-btn">{saving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Plus className="w-3.5 h-3.5 mr-1.5" />} {editingId ? 'Update' : 'Confirm & Save'}</Button></div>
        </DialogContent>
      </Dialog>
      <DuplicateWarningDialog open={showWarning} onClose={cancelSave} onConfirm={confirmSave} duplicates={duplicates} saving={saving} />
      <ConfirmDeleteDialog open={deleteConfirm.open} onClose={cancelDelete} onConfirm={handleDeleteConfirm} message={deleteConfirm.message} />
      <ConfirmSaveDialog open={showConfirmSave} onClose={() => setShowConfirmSave(false)} onConfirm={executeSave} vendor={form.supplier_name} date={form.invoice_date} total={form.total} saving={saving} />
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
  const [showConfirmSave, setShowConfirmSave] = useState(false);

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
  const handleSave = () => {
    if (!form.employee_name.trim()) { toast.error('Employee name is required'); return; }
    if (!form.amount) { toast.error('Salary amount is required'); return; }
    setShowConfirmSave(true);
  };
  const executeSave = async () => {
    setShowConfirmSave(false);
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
      <ConfirmSaveDialog open={showConfirmSave} onClose={() => setShowConfirmSave(false)} onConfirm={executeSave} vendor={form.employee_name} date={form.payment_date} total={form.amount} saving={saving} />
    </div>
  );
}

// ======================== OTHER EXPENSES TAB ========================
function OtherExpensesTab({ api }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ title: '', category: 'Miscellaneous', amount: 0, expense_date: new Date().toISOString().split('T')[0], notes: '' });
  const [saving, setSaving] = useState(false);
  const [filterCat, setFilterCat] = useState('all');
  const { checking, duplicates, showWarning, confirmSave, cancelSave, checkDuplicates } = useDuplicateCheck();
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, id: null, message: '' });
  const [showConfirmSave, setShowConfirmSave] = useState(false);

  // Upload / OCR state
  const [uploadFiles, setUploadFiles] = useState([]);
  const [uploadPreviews, setUploadPreviews] = useState([]);
  const [extracting, setExtracting] = useState(false);
  const extractingRef = useRef(false);
  const [receiptId, setReceiptId] = useState(null);
  const [parsingMethod, setParsingMethod] = useState(null);

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

  const openAdd = () => {
    setEditingId(null);
    setForm({ title: '', category: 'Miscellaneous', amount: 0, expense_date: new Date().toISOString().split('T')[0], notes: '' });
    uploadPreviews.forEach(u => { if (u) URL.revokeObjectURL(u); });
    setUploadFiles([]); setUploadPreviews([]);
    setReceiptId(null); setParsingMethod(null);
    setShowAdd(true);
  };
  const openEdit = (record) => {
    setEditingId(record.id);
    setForm({ title: record.title || '', category: record.category || 'Miscellaneous', amount: record.amount || 0, expense_date: record.expense_date || '', notes: record.notes || '' });
    uploadPreviews.forEach(u => { if (u) URL.revokeObjectURL(u); });
    setUploadFiles([]); setUploadPreviews([]);
    setReceiptId(null); setParsingMethod(null);
    setShowAdd(true);
  };

  const handleFile = (file) => {
    if (!file) return;
    setUploadFiles(prev => [...prev, file]);
    setUploadPreviews(prev => [...prev, file.type.startsWith('image/') ? URL.createObjectURL(file) : null]);
  };
  const removeFile = (idx) => {
    setUploadFiles(prev => prev.filter((_, i) => i !== idx));
    setUploadPreviews(prev => { if (prev[idx]) URL.revokeObjectURL(prev[idx]); return prev.filter((_, i) => i !== idx); });
  };
  const clearAllFiles = () => {
    uploadPreviews.forEach(u => { if (u) URL.revokeObjectURL(u); });
    setUploadFiles([]); setUploadPreviews([]);
  };

  const handleExtract = async () => {
    if (!uploadFiles.length || extractingRef.current) return;
    setExtracting(true); extractingRef.current = true;
    try {
      const fd = new FormData();
      uploadFiles.forEach(f => fd.append('files', f));
      fd.append('document_type', 'other_expense');
      const res = await api.post('/upload/extract', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 90000 });
      const d = res.data?.extracted_data || {};
      setForm(f => ({
        ...f,
        title: d.title || f.title,
        category: OTHER_CATEGORIES.includes(d.category) ? d.category : f.category,
        amount: parseFloat(d.amount) || f.amount,
        expense_date: d.expense_date || f.expense_date,
        notes: [d.vendor_name, d.reference_number, d.notes].filter(Boolean).join(' — ') || f.notes,
      }));
      if (res.data?.receipt_id) setReceiptId(res.data.receipt_id);
      if (res.data?.parsing_method) setParsingMethod(res.data.parsing_method);
      toast.success(res.data.message || 'Data extracted! Review and save.');
    } catch (err) { toast.error('Extraction failed: ' + (err.response?.data?.detail || 'Try again.')); }
    finally { setExtracting(false); extractingRef.current = false; }
  };

  const handleSave = () => {
    if (!form.title.trim()) { toast.error('Expense title is required'); return; }
    if (!form.amount) { toast.error('Amount is required'); return; }
    setShowConfirmSave(true);
  };
  const executeSave = async () => {
    setShowConfirmSave(false);
    const doSave = async () => {
      setSaving(true);
      try {
        if (editingId) {
          await api.put(`/other-expenses/${editingId}`, form);
          toast.success('Updated');
        } else {
          const res = await api.post('/other-expenses', form);
          if (uploadFiles.length > 0 && res.data?.id) {
            try {
              const fd = new FormData();
              fd.append('file', uploadFiles[0]);
              fd.append('folder', 'expenses');
              fd.append('transaction_type', 'other_expense');
              fd.append('transaction_id', res.data.id);
              fd.append('transaction_date', form.expense_date || '');
              fd.append('transaction_amount', form.amount || 0);
              fd.append('transaction_notes', form.title || '');
              fd.append('vendor_name', '');
              await api.post('/records/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
            } catch { /* silent */ }
          }
          toast.success('Expense saved');
        }
        // Learn vendor pattern
        if (receiptId || uploadFiles.length > 0) {
          try {
            await api.post('/receipts/learn', {
              receipt_id: receiptId,
              vendor_name: form.notes?.split(' — ')[0] || form.title || '',
              corrected_items: [],
              corrected_date: form.expense_date,
              corrected_total: form.amount,
              hints: { expense_category: form.category },
            });
          } catch { /* silent */ }
        }
        setShowAdd(false);
        setReceiptId(null); setParsingMethod(null);
        load(true);
        dataEvents.emit();
      }
      catch (err) { toast.error('Save failed: ' + (err.response?.data?.detail || '')); }
      finally { setSaving(false); }
    };
    if (editingId) { await doSave(); } else { await checkDuplicates('other_expense', form, api, doSave); }
  };

  const catColor = (c) => {
    const map = { 'Utilities': 'bg-amber-100 text-amber-700', 'Taxes': 'bg-red-100 text-red-700', 'Maintenance & Repairs': 'bg-slate-100 text-slate-700', 'Software & Subscriptions': 'bg-violet-100 text-violet-700', 'Services': 'bg-blue-100 text-blue-700', 'Rent / Facility': 'bg-emerald-100 text-emerald-700', 'Miscellaneous': 'bg-slate-100 text-slate-600' };
    return map[c] || 'bg-slate-100 text-slate-600';
  };

  const filtered = filterCat === 'all' ? items : items.filter(e => e.category === filterCat);

  return (
    <div className="space-y-4" data-testid="other-expenses-tab">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <Select value={filterCat} onValueChange={setFilterCat}>
            <SelectTrigger className="w-[180px] h-8 text-xs" data-testid="filter-other-category"><SelectValue placeholder="All Categories" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all" className="text-xs font-semibold">All Categories</SelectItem>
              {OTHER_CATEGORIES.map(c => <SelectItem key={c} value={c} className="text-xs">{c}</SelectItem>)}
            </SelectContent>
          </Select>
          {filterCat !== 'all' && <Badge className={`text-[10px] border-0 cursor-pointer ${catColor(filterCat)}`} onClick={() => setFilterCat('all')}>{filterCat} &times;</Badge>}
        </div>
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
            )) : filtered.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="h-40">
                <div className="flex flex-col items-center justify-center text-center py-6">
                  <Wrench className="w-10 h-10 text-slate-300 mb-3" />
                  <h3 className="font-heading text-sm font-bold text-navy-900 mb-1">{filterCat !== 'all' ? `No ${filterCat} expenses` : 'No other expenses'}</h3>
                  <p className="text-xs text-slate-400 mb-3">Track rent, utilities, and more</p>
                  <Button onClick={openAdd} variant="outline" size="sm" className="text-xs"><Plus className="w-3 h-3 mr-1" /> Add Expense</Button>
                </div>
              </TableCell></TableRow>
            ) : filtered.map((e, i) => (
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
          {filtered.length > 0 && <div className="px-4 py-2.5 border-t border-slate-100 bg-slate-50/50"><p className="text-[11px] text-slate-400">{filtered.length} expense{filtered.length !== 1 ? 's' : ''}{filterCat !== 'all' ? ` in ${filterCat}` : ''} &middot; Total: <span className="font-bold text-navy-900">{fmt(filtered.reduce((s, r) => s + (r.amount || 0), 0))}</span>{filterCat !== 'all' && items.length !== filtered.length ? <span className="ml-2">({items.length} total across all categories)</span> : ''}</p></div>}
        </div>
      </Card>

      <Dialog open={showAdd} onOpenChange={(v) => { if (!saving && !extracting) setShowAdd(v); }}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="font-heading text-lg">{editingId ? 'Edit Expense' : 'Add Expense'}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            {/* Upload zone — only for new entries */}
            {!editingId && (
              <div className="rounded-lg border-2 border-dashed border-slate-200 p-3" data-testid="other-expense-upload-zone">
                <div className="flex items-center gap-2 mb-2">
                  <Upload className="w-4 h-4 text-teal-600" />
                  <span className="text-xs font-bold text-navy-900">Upload a document</span>
                  <span className="text-[10px] text-slate-400">AI will extract details — supports multi-page</span>
                </div>
                {uploadFiles.length > 0 ? (
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-2">
                      {uploadFiles.map((uf, idx) => (
                        <div key={idx} className="relative group rounded-lg border border-slate-200 bg-white p-1.5 w-[80px]" data-testid={`oe-upload-page-${idx}`}>
                          {uploadPreviews[idx] ? <img src={uploadPreviews[idx]} alt={`Page ${idx+1}`} className="w-full h-14 object-cover rounded" /> : <div className="w-full h-14 rounded bg-slate-100 flex items-center justify-center"><FileText className="w-5 h-5 text-slate-400" /></div>}
                          <p className="text-[9px] font-semibold text-center text-slate-500 mt-1">Page {idx+1}</p>
                          <button onClick={() => removeFile(idx)} className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-red-500 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity" data-testid={`oe-remove-page-${idx}`}><X className="w-3 h-3" /></button>
                        </div>
                      ))}
                      <label className="w-[80px] h-[82px] rounded-lg border-2 border-dashed border-slate-200 flex flex-col items-center justify-center cursor-pointer hover:border-teal-300 hover:bg-teal-50/30 transition-colors" data-testid="oe-add-another-image-btn">
                        <Plus className="w-5 h-5 text-slate-400" />
                        <span className="text-[9px] font-semibold text-slate-400 mt-0.5">Add Page</span>
                        <input type="file" accept="image/*,.pdf" className="hidden" onChange={(e) => handleFile(e.target.files?.[0])} />
                      </label>
                    </div>
                    <div className="flex items-center justify-between">
                      <p className="text-[10px] text-slate-400">{uploadFiles.length} page{uploadFiles.length !== 1 ? 's' : ''}</p>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={clearAllFiles}><X className="w-3 h-3 mr-1" /> Clear</Button>
                        <Button size="sm" className="h-7 text-xs bg-teal-600 hover:bg-teal-700 text-white" onClick={handleExtract} disabled={extracting} data-testid="extract-other-expense-btn">
                          {extracting ? <><Loader2 className="w-3 h-3 animate-spin mr-1" /> Extracting...</> : <><Sparkles className="w-3 h-3 mr-1" /> Extract</>}
                        </Button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-4 gap-2">
                    {[
                      { icon: Camera, label: 'Photo', accept: 'image/*', capture: 'environment' },
                      { icon: ImageIcon, label: 'Image', accept: 'image/*' },
                      { icon: FileText, label: 'PDF', accept: '.pdf' },
                      { icon: FileSpreadsheet, label: 'Excel', accept: '.xlsx,.xls,.csv' },
                    ].map(({ icon: Icon, label, accept, capture }) => (
                      <label key={label} className="flex flex-col items-center gap-1.5 p-3 rounded-md border border-slate-100 hover:border-teal-300 hover:bg-teal-50/30 cursor-pointer transition-colors">
                        <Icon className="w-5 h-5 text-slate-400" />
                        <span className="text-[10px] font-medium text-slate-500">{label}</span>
                        <input type="file" accept={accept} capture={capture} className="hidden" onChange={(e) => handleFile(e.target.files?.[0])} />
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )}

            {parsingMethod && (
              <div className="flex items-center gap-2 text-[10px]" data-testid="other-expense-parsing-badge">
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-semibold ${parsingMethod === 'vendor' ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-blue-700'}`}>
                  <Sparkles className="w-3 h-3" />
                  {parsingMethod === 'vendor' ? 'Vendor pattern matched' : 'General parsing'}
                </span>
              </div>
            )}

            <div><Label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Expense Title *</Label><Input className="mt-1 h-9 text-sm" value={form.title} onChange={(e) => updateField('title', e.target.value)} placeholder="e.g., March Electricity Bill" data-testid="form-expense-title" /></div>
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
      <ConfirmSaveDialog open={showConfirmSave} onClose={() => setShowConfirmSave(false)} onConfirm={executeSave} vendor={form.title} date={form.expense_date} total={form.amount} saving={saving} />
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
