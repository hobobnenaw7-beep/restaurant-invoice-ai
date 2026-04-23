import { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Separator } from '@/components/ui/separator';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { toast } from 'sonner';
import {
  AlertTriangle, CheckCircle2, Pencil, X, Save, Loader2,
  History, ChevronDown, ChevronUp, ArrowUpRight, ArrowDownRight, Minus,
  ShieldCheck, ShieldAlert, Info
} from 'lucide-react';

function fmt(n) {
  return n != null ? `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '$0.00';
}

function classifyIssue(item) {
  const errors = item.validation_errors || [];
  const reason = (item.review_reason || '').toLowerCase();
  const name = (item.raw_name || '').trim();
  if (errors.some(e => /math mismatch/i.test(e)) || reason.includes('math mismatch'))
    return { type: 'math', label: 'Math Mismatch', color: 'text-red-700', bg: 'bg-red-100 border-red-200' };
  if (errors.some(e => /pack.*parse.*failed/i.test(e)) || reason.includes('pack size'))
    return { type: 'pack', label: 'Pack Parse Failed', color: 'text-orange-700', bg: 'bg-orange-100 border-orange-200' };
  if (!name || errors.some(e => /item_name/i.test(e)) || reason.includes('missing item name'))
    return { type: 'name', label: 'Missing Name', color: 'text-red-700', bg: 'bg-red-100 border-red-200' };
  if (errors.some(e => /suspicious/i.test(e)) || reason.includes('suspicious'))
    return { type: 'suspicious', label: 'Suspicious', color: 'text-red-700', bg: 'bg-red-100 border-red-200' };
  if (errors.some(e => /missing:/i.test(e)) || reason.includes('missing fields'))
    return { type: 'missing', label: 'Missing Fields', color: 'text-amber-700', bg: 'bg-amber-100 border-amber-200' };
  return { type: 'review', label: 'Needs Review', color: 'text-amber-700', bg: 'bg-amber-100 border-amber-200' };
}

// Which fields are problematic for a given item
function getProblematicFields(item) {
  const fields = new Set();
  const errors = item.validation_errors || [];
  const reason = (item.review_reason || '').toLowerCase();
  for (const e of errors) {
    const el = e.toLowerCase();
    if (el.includes('math mismatch') || el.includes('total')) fields.add('total');
    if (el.includes('qty') || el.includes('quantity')) fields.add('quantity');
    if (el.includes('unit_price') || el.includes('price')) fields.add('unit_price');
    if (el.includes('item_name') || el.includes('name')) fields.add('raw_name');
    if (el.includes('pack')) fields.add('pack_size');
    if (el.includes('missing') && el.includes('line_total')) fields.add('total');
  }
  if (reason.includes('math')) { fields.add('total'); fields.add('unit_price'); fields.add('quantity'); }
  if (reason.includes('name')) fields.add('raw_name');
  if (reason.includes('pack')) fields.add('pack_size');
  return fields;
}

function DeltaBadge({ delta }) {
  if (delta === 'improved') return <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 text-[9px] gap-1"><ArrowUpRight className="w-2.5 h-2.5" />Improved</Badge>;
  if (delta === 'degraded') return <Badge className="bg-red-100 text-red-700 border-red-200 text-[9px] gap-1"><ArrowDownRight className="w-2.5 h-2.5" />Degraded</Badge>;
  return null;
}

export default function InvoiceReviewDialog({ purchase, open, onClose, onOpen, api, onUpdate }) {
  const [items, setItems] = useState([]);
  const [editingRow, setEditingRow] = useState(null);
  const [editValues, setEditValues] = useState({});
  const [saving, setSaving] = useState(false);
  const [editHistory, setEditHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [totals, setTotals] = useState({ subtotal: 0, tax: 0, total: 0 });
  const [lastDelta, setLastDelta] = useState(null);
  const sessionStart = useRef(null);
  const editsInSession = useRef(0);

  useEffect(() => {
    if (purchase) {
      setItems((purchase.items || []).map((it, i) => ({ ...it, _idx: i })));
      setTotals({ subtotal: purchase.subtotal || 0, tax: purchase.tax || 0, total: purchase.total || 0 });
      setEditingRow(null);
      setLastDelta(null);
    }
  }, [purchase]);

  // Track session start time
  useEffect(() => {
    if (open && purchase?.id) {
      sessionStart.current = Date.now();
      editsInSession.current = 0;
      if (onOpen) onOpen();
    }
  }, [open, purchase?.id, onOpen]);

  const loadHistory = useCallback(async () => {
    if (!purchase?.id) return;
    try {
      const res = await api.get(`/purchases/${purchase.id}/edit-history`);
      setEditHistory(res.data.edit_history || []);
    } catch { /* silent */ }
  }, [api, purchase?.id]);

  useEffect(() => {
    if (open && purchase?.id) loadHistory();
  }, [open, purchase?.id, loadHistory]);

  if (!purchase) return null;

  const logMetrics = async () => {
    if (!sessionStart.current || !purchase?.id) return;
    const seconds = (Date.now() - sessionStart.current) / 1000;
    if (seconds < 2) return; // Skip accidental opens
    try {
      await api.post('/metrics/review-session', {
        purchase_id: purchase.id,
        supplier_name: purchase.supplier_name || '',
        time_spent_seconds: seconds,
        edits_count: editsInSession.current,
        flagged_rows_count: (purchase.items || []).filter(it => it.needs_review).length,
        total_rows: (purchase.items || []).length,
      });
    } catch { /* silent */ }
    sessionStart.current = null;
  };

  const handleClose = () => {
    logMetrics();
    cancelEdit();
    onClose();
  };

  const reviewItems = items.filter(it => it.needs_review);
  const passItems = items.filter(it => !it.needs_review && it.confidence_level === 'trusted');

  const startEdit = (idx) => {
    const item = items[idx];
    setEditingRow(idx);
    setEditValues({
      raw_name: item.raw_name || '',
      quantity: item.quantity || 0,
      unit_price: item.unit_price || 0,
      total: item.total || 0,
      pack_size: item.pack_size_raw || item.pack_size || '',
    });
    setLastDelta(null);
  };

  const cancelEdit = () => {
    setEditingRow(null);
    setEditValues({});
  };

  const saveEdit = async (idx) => {
    setSaving(true);
    try {
      const res = await api.patch(`/purchases/${purchase.id}/items/${idx}`, editValues);
      const data = res.data;
      // Update the item in local state
      setItems(prev => {
        const updated = [...prev];
        updated[idx] = { ...data.item, _idx: idx };
        return updated;
      });
      setTotals(data.purchase_totals);
      setLastDelta({ idx, delta: data.validation_delta });
      setEditingRow(null);
      setEditValues({});
      editsInSession.current += 1;
      loadHistory();
      if (onUpdate) onUpdate(data);
      const deltaMsg = data.validation_delta === 'improved' ? ' — validation improved!' :
                        data.validation_delta === 'degraded' ? ' — warning: validation degraded' : '';
      toast.success(`Item updated${deltaMsg}`);
      // Correction Pipeline v3: surface catalog linkage outcome to the user
      const link = data.catalog_linkage;
      if (link && link.action === 'linked' && link.canonical_name) {
        toast.success(`Linked to catalog: ${link.canonical_name}`, { duration: 3500 });
      } else if (link && link.action === 'suggested' && link.canonical_name) {
        toast.info(`Added "${link.canonical_name}" as a suggested item — review in Items`, { duration: 4500 });
      }
    } catch (err) {
      toast.error('Failed to save: ' + (err.response?.data?.detail || ''));
    } finally {
      setSaving(false);
    }
  };

  const startFixFlagged = (idx) => {
    const item = items[idx];
    const problemFields = getProblematicFields(item);
    startEdit(idx);
    // Focus will be handled by the input autoFocus on first problem field
    setTimeout(() => {
      const firstField = ['raw_name', 'quantity', 'unit_price', 'total', 'pack_size'].find(f => problemFields.has(f));
      if (firstField) {
        const el = document.querySelector(`[data-testid="edit-${firstField}-${idx}"]`);
        if (el) el.focus();
      }
    }, 100);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose(); }}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col" data-testid="invoice-review-dialog">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="font-heading text-lg flex items-center gap-2">
            Invoice Review
            {purchase.supplier_name && <span className="text-teal-600">— {purchase.supplier_name}</span>}
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 min-h-0">
          {/* Invoice header info */}
          <div className="grid grid-cols-3 gap-4" data-testid="invoice-header-info">
            {[['Vendor', purchase.supplier_name], ['Invoice #', purchase.invoice_number], ['Date', purchase.invoice_date]].map(([l, v]) => (
              <div key={l}>
                <p className="text-[10px] font-bold text-slate-400 uppercase">{l}</p>
                <p className="text-sm font-semibold text-navy-900 mt-0.5">{v || '—'}</p>
              </div>
            ))}
          </div>

          {/* Validation summary banner */}
          <div className={`flex items-center gap-3 p-3 rounded-lg border ${
            reviewItems.length === 0 ? 'bg-emerald-50 border-emerald-200' : 'bg-amber-50 border-amber-200'
          }`} data-testid="validation-summary-banner">
            {reviewItems.length === 0 ? (
              <>
                <ShieldCheck className="w-5 h-5 text-emerald-600 flex-shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-emerald-800">All items verified</p>
                  <p className="text-[10px] text-emerald-600">{items.length} items — all pass validation</p>
                </div>
              </>
            ) : (
              <>
                <ShieldAlert className="w-5 h-5 text-amber-600 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-xs font-semibold text-amber-800">
                    {items.length} items: {passItems.length} pass, {reviewItems.length} need{reviewItems.length === 1 ? 's' : ''} review
                  </p>
                  <p className="text-[10px] text-amber-600">Click Fix on flagged rows to correct inline</p>
                </div>
              </>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="text-[10px] gap-1 h-7"
              onClick={() => setShowHistory(!showHistory)}
              data-testid="toggle-history-btn"
            >
              <History className="w-3 h-3" /> {showHistory ? 'Hide' : 'Show'} History ({editHistory.length})
            </Button>
          </div>

          {/* Edit history panel */}
          {showHistory && editHistory.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 space-y-2 max-h-48 overflow-y-auto" data-testid="edit-history-panel">
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Edit Audit Trail</p>
              {editHistory.slice().reverse().map((entry, ei) => (
                <div key={ei} className="flex items-start gap-2 text-[10px] py-1.5 border-b border-slate-100 last:border-0" data-testid={`history-entry-${ei}`}>
                  <span className="text-slate-400 tabular-nums flex-shrink-0 w-28">
                    {new Date(entry.edited_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                  </span>
                  <span className="text-slate-600 flex-shrink-0">Item {entry.item_index + 1}:</span>
                  <div className="flex-1 space-y-0.5">
                    {Object.entries(entry.changes).map(([field, vals]) => (
                      <div key={field} className="flex items-center gap-1">
                        <span className="font-semibold text-slate-700">{field}:</span>
                        <span className="text-red-500 line-through">{typeof vals.previous === 'number' ? vals.previous.toFixed(2) : vals.previous || '(empty)'}</span>
                        <span className="text-slate-400">&rarr;</span>
                        <span className="text-emerald-700 font-medium">{typeof vals.new === 'number' ? vals.new.toFixed(2) : vals.new}</span>
                      </div>
                    ))}
                  </div>
                  <DeltaBadge delta={entry.validation_delta} />
                  <span className="text-slate-400 flex-shrink-0">{entry.edited_by}</span>
                </div>
              ))}
            </div>
          )}
          {showHistory && editHistory.length === 0 && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-center" data-testid="edit-history-empty">
              <p className="text-xs text-slate-400">No edits recorded yet</p>
            </div>
          )}

          <Separator />

          {/* Line items table with inline editing */}
          <TooltipProvider>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                    <TableHead className="text-[10px] font-bold text-slate-500 uppercase w-8">Status</TableHead>
                    <TableHead className="text-[10px] font-bold text-slate-500 uppercase">Item</TableHead>
                    <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right w-16">Qty</TableHead>
                    <TableHead className="text-[10px] font-bold text-slate-500 uppercase w-24">Pack</TableHead>
                    <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right w-20">Price</TableHead>
                    <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-right w-20">Total</TableHead>
                    <TableHead className="text-[10px] font-bold text-slate-500 uppercase text-center w-20">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((it, i) => {
                    const flagged = it.needs_review;
                    const issue = flagged ? classifyIssue(it) : null;
                    const problemFields = flagged ? getProblematicFields(it) : new Set();
                    const isEditing = editingRow === i;
                    const deltaForRow = lastDelta?.idx === i ? lastDelta.delta : null;

                    const fieldBorder = (field) => {
                      if (isEditing) return 'border-blue-300 focus:border-blue-500';
                      if (problemFields.has(field)) return 'border-red-300 bg-red-50/50';
                      return '';
                    };

                    return (
                      <TableRow
                        key={i}
                        className={`transition-colors ${
                          isEditing ? 'bg-blue-50/50 ring-1 ring-blue-200' :
                          flagged ? 'bg-amber-50/50' :
                          i % 2 === 0 ? '' : 'bg-slate-50/40'
                        }`}
                        data-testid={`review-item-row-${i}`}
                      >
                        {/* Status cell */}
                        <TableCell className="text-center" data-testid={`review-status-${i}`}>
                          {flagged ? (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="inline-flex w-5 h-5 rounded-full bg-amber-100 items-center justify-center cursor-help">
                                  <AlertTriangle className="w-3 h-3 text-amber-600" />
                                </span>
                              </TooltipTrigger>
                              <TooltipContent side="right" className="max-w-xs">
                                <p className="font-semibold text-xs mb-1">{issue?.label}</p>
                                {(it.validation_errors || []).map((e, ei) => (
                                  <p key={ei} className="text-[10px] text-slate-600">{e}</p>
                                ))}
                                {it.review_reason && <p className="text-[10px] text-amber-600 mt-1">{it.review_reason}</p>}
                              </TooltipContent>
                            </Tooltip>
                          ) : (
                            <span className="inline-flex w-5 h-5 rounded-full bg-emerald-100 items-center justify-center">
                              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                            </span>
                          )}
                          {deltaForRow && <div className="mt-1"><DeltaBadge delta={deltaForRow} /></div>}
                        </TableCell>

                        {/* Item name */}
                        <TableCell>
                          {isEditing ? (
                            <Input
                              className={`text-xs h-7 ${fieldBorder('raw_name')}`}
                              value={editValues.raw_name}
                              onChange={(e) => setEditValues(v => ({ ...v, raw_name: e.target.value }))}
                              data-testid={`edit-raw_name-${i}`}
                              autoFocus={problemFields.has('raw_name')}
                            />
                          ) : (
                            <div>
                              <span className={`text-sm font-medium ${problemFields.has('raw_name') ? 'text-red-700' : ''}`}>{it.raw_name || '—'}</span>
                              {flagged && issue && (
                                <div className="mt-0.5">
                                  <Badge className={`text-[9px] border ${issue.bg}`} data-testid={`issue-badge-${i}`}>
                                    {issue.label}
                                  </Badge>
                                </div>
                              )}
                            </div>
                          )}
                        </TableCell>

                        {/* Qty */}
                        <TableCell className="text-right">
                          {isEditing ? (
                            <Input
                              className={`text-xs h-7 text-right tabular-nums w-16 ${fieldBorder('quantity')}`}
                              type="number"
                              value={editValues.quantity || ''}
                              onChange={(e) => setEditValues(v => ({ ...v, quantity: parseFloat(e.target.value) || 0 }))}
                              data-testid={`edit-quantity-${i}`}
                              autoFocus={problemFields.has('quantity') && !problemFields.has('raw_name')}
                            />
                          ) : (
                            <span className={`text-sm tabular-nums ${problemFields.has('quantity') ? 'text-red-700 font-semibold' : ''}`}>{it.quantity}</span>
                          )}
                        </TableCell>

                        {/* Pack */}
                        <TableCell>
                          {isEditing ? (
                            <Input
                              className={`text-xs h-7 w-24 ${fieldBorder('pack_size')}`}
                              value={editValues.pack_size}
                              onChange={(e) => setEditValues(v => ({ ...v, pack_size: e.target.value }))}
                              data-testid={`edit-pack_size-${i}`}
                            />
                          ) : (
                            <span className={`text-sm text-slate-500 ${problemFields.has('pack_size') ? 'text-orange-700' : ''}`}>
                              {it.pack_size_raw || it.pack_size || '—'}
                            </span>
                          )}
                        </TableCell>

                        {/* Price */}
                        <TableCell className="text-right">
                          {isEditing ? (
                            <Input
                              className={`text-xs h-7 text-right tabular-nums w-20 ${fieldBorder('unit_price')}`}
                              type="number"
                              step="0.01"
                              value={editValues.unit_price || ''}
                              onChange={(e) => setEditValues(v => ({ ...v, unit_price: parseFloat(e.target.value) || 0 }))}
                              data-testid={`edit-unit_price-${i}`}
                              autoFocus={problemFields.has('unit_price') && !problemFields.has('raw_name') && !problemFields.has('quantity')}
                            />
                          ) : (
                            <span className={`text-sm tabular-nums ${problemFields.has('unit_price') ? 'text-red-700 font-semibold' : ''}`}>{fmt(it.unit_price)}</span>
                          )}
                        </TableCell>

                        {/* Total */}
                        <TableCell className="text-right">
                          {isEditing ? (
                            <Input
                              className={`text-xs h-7 text-right tabular-nums w-20 ${fieldBorder('total')}`}
                              type="number"
                              step="0.01"
                              value={editValues.total || ''}
                              onChange={(e) => setEditValues(v => ({ ...v, total: parseFloat(e.target.value) || 0 }))}
                              data-testid={`edit-total-${i}`}
                            />
                          ) : (
                            <span className={`text-sm font-semibold tabular-nums ${problemFields.has('total') ? 'text-red-700' : ''}`}>{fmt(it.total)}</span>
                          )}
                        </TableCell>

                        {/* Actions */}
                        <TableCell className="text-center">
                          {isEditing ? (
                            <div className="flex items-center justify-center gap-1">
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 w-6 p-0"
                                onClick={() => saveEdit(i)}
                                disabled={saving}
                                data-testid={`save-edit-${i}`}
                              >
                                {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3 text-emerald-600" />}
                              </Button>
                              <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={cancelEdit} data-testid={`cancel-edit-${i}`}>
                                <X className="w-3 h-3 text-slate-400" />
                              </Button>
                            </div>
                          ) : (
                            <div className="flex items-center justify-center gap-1">
                              {flagged ? (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-6 text-[10px] text-blue-700 bg-blue-50 hover:bg-blue-100 px-2 gap-1"
                                  onClick={() => startFixFlagged(i)}
                                  data-testid={`fix-item-btn-${i}`}
                                >
                                  <Pencil className="w-2.5 h-2.5" /> Fix
                                </Button>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-6 w-6 p-0 opacity-40 hover:opacity-100"
                                  onClick={() => startEdit(i)}
                                  data-testid={`edit-item-btn-${i}`}
                                >
                                  <Pencil className="w-3 h-3 text-slate-500" />
                                </Button>
                              )}
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </TooltipProvider>

          {/* Totals */}
          <div className="flex justify-end">
            <div className="text-right space-y-1 min-w-[200px]">
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">Subtotal</span>
                <span className="tabular-nums">{fmt(totals.subtotal)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">Tax</span>
                <span className="tabular-nums">{fmt(totals.tax)}</span>
              </div>
              <Separator className="my-1" />
              <div className="flex justify-between text-base font-bold">
                <span>Total</span>
                <span className="tabular-nums">{fmt(totals.total)}</span>
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
