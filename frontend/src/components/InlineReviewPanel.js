import { useState, useRef, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Card } from '@/components/ui/card';
import { toast } from 'sonner';
import {
  AlertTriangle, CheckCircle2, Loader2, ArrowRight, ShieldCheck, ChevronLeft, ChevronRight
} from 'lucide-react';

function fmt(n) {
  return n != null ? `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '$0.00';
}

function EditableCell({ value, field, itemIndex, purchaseId, api, onSaved, isMissing }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(value ?? '');
  const [saving, setSaving] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => { setVal(value ?? ''); }, [value]);
  useEffect(() => { if (editing && inputRef.current) inputRef.current.select(); }, [editing]);

  const save = async () => {
    const numVal = parseFloat(val) || 0;
    if (numVal === (parseFloat(value) || 0)) { setEditing(false); return; }
    setSaving(true);
    try {
      const res = await api.patch(`/purchases/${purchaseId}/items/${itemIndex}`, { [field]: numVal });
      onSaved(res.data);
      setEditing(false);
      toast.success(`${field === 'unit_price' ? 'Price' : field === 'total' ? 'Total' : 'Qty'} updated`);
    } catch (err) {
      toast.error('Save failed: ' + (err.response?.data?.detail || err.message));
    } finally { setSaving(false); }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') save();
    if (e.key === 'Escape') { setVal(value ?? ''); setEditing(false); }
  };

  if (editing) {
    return (
      <div className="relative">
        <Input
          ref={inputRef}
          type="number"
          step="0.01"
          className="h-7 text-xs text-right w-20 pr-1 border-blue-400 focus:ring-blue-300"
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={save}
          disabled={saving}
          data-testid={`inline-edit-${field}-${itemIndex}`}
        />
        {saving && <Loader2 className="absolute right-1 top-1.5 w-3 h-3 animate-spin text-blue-500" />}
      </div>
    );
  }

  const displayVal = field === 'quantity' ? (value || 0) : fmt(value || 0);
  return (
    <span
      onClick={() => setEditing(true)}
      className={`cursor-pointer px-1.5 py-0.5 rounded text-xs tabular-nums transition-colors ${
        isMissing
          ? 'bg-red-100 text-red-700 border border-red-200 border-dashed font-semibold hover:bg-red-200'
          : 'hover:bg-blue-50 hover:text-blue-700'
      }`}
      title="Click to edit"
      data-testid={`inline-cell-${field}-${itemIndex}`}
    >
      {isMissing ? '—' : displayVal}
    </span>
  );
}

export default function InlineReviewPanel({ purchases, api, onRefresh }) {
  const [currentIdx, setCurrentIdx] = useState(0);
  const [localPurchases, setLocalPurchases] = useState(purchases);
  const [verifying, setVerifying] = useState(false);

  useEffect(() => { setLocalPurchases(purchases); setCurrentIdx(0); }, [purchases]);

  const handleItemSaved = useCallback((data) => {
    setLocalPurchases(prev => {
      const updated = [...prev];
      const p = { ...updated[currentIdx] };
      const items = [...(p.items || [])];
      items[data.item_index] = data.item;
      p.items = items;
      p.total = data.purchase_totals?.total ?? p.total;
      p.subtotal = data.purchase_totals?.subtotal ?? p.subtotal;
      p.review_status = data.review_status ?? p.review_status;
      updated[currentIdx] = p;
      return updated;
    });
  }, [currentIdx]);

  const purchase = localPurchases[currentIdx];
  if (!purchase) {
    return (
      <Card className="p-8 text-center border-slate-200" data-testid="no-review-items">
        <ShieldCheck className="w-10 h-10 text-emerald-400 mx-auto mb-3" />
        <p className="text-sm font-semibold text-slate-700">No invoices need review</p>
        <p className="text-xs text-slate-400 mt-1">All extraction results are verified</p>
      </Card>
    );
  }

  const items = purchase.items || [];
  const reviewItems = items.filter(it => it.needs_review);
  const allResolved = reviewItems.length === 0;

  const markVerified = async () => {
    setVerifying(true);
    try {
      await api.patch(`/purchases/${purchase.id}/verify`);
      toast.success('Invoice marked as verified');
      if (onRefresh) onRefresh();
    } catch (err) {
      toast.error('Verification failed: ' + (err.response?.data?.detail || err.message));
    } finally { setVerifying(false); }
  };

  return (
    <Card className="border-slate-200 overflow-hidden" data-testid="inline-review-panel">
      {/* Header */}
      <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-navy-900">{purchase.supplier_name}</h3>
            <Badge variant="outline" className="text-[10px] font-mono">{purchase.invoice_number}</Badge>
          </div>
          <p className="text-[10px] text-slate-400 mt-0.5">
            {purchase.invoice_date} &middot; {items.length} items &middot;
            <span className={reviewItems.length > 0 ? 'text-amber-600 font-semibold' : 'text-emerald-600'}>
              {' '}{reviewItems.length > 0 ? `${reviewItems.length} need review` : 'All verified'}
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Nav */}
          <Button
            variant="outline" size="sm" className="h-7 w-7 p-0"
            disabled={currentIdx === 0}
            onClick={() => setCurrentIdx(i => i - 1)}
            data-testid="review-prev-btn"
          ><ChevronLeft className="w-3.5 h-3.5" /></Button>
          <span className="text-[10px] text-slate-500 tabular-nums">{currentIdx + 1}/{localPurchases.length}</span>
          <Button
            variant="outline" size="sm" className="h-7 w-7 p-0"
            disabled={currentIdx >= localPurchases.length - 1}
            onClick={() => setCurrentIdx(i => i + 1)}
            data-testid="review-next-btn"
          ><ChevronRight className="w-3.5 h-3.5" /></Button>

          {/* Mark Verified */}
          {allResolved && (
            <Button
              size="sm"
              className="h-7 text-xs bg-emerald-600 hover:bg-emerald-700 text-white gap-1"
              onClick={markVerified}
              disabled={verifying}
              data-testid="mark-verified-btn"
            >
              {verifying ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
              Mark Verified
            </Button>
          )}
        </div>
      </div>

      {/* Items table — inline editable */}
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="bg-white hover:bg-white">
              <TableHead className="text-[10px] font-bold text-slate-400 uppercase w-6">#</TableHead>
              <TableHead className="text-[10px] font-bold text-slate-400 uppercase">Item Name</TableHead>
              <TableHead className="text-[10px] font-bold text-slate-400 uppercase w-12">Code</TableHead>
              <TableHead className="text-[10px] font-bold text-slate-400 uppercase text-right w-14">Qty</TableHead>
              <TableHead className="text-[10px] font-bold text-slate-400 uppercase text-right w-20">Price</TableHead>
              <TableHead className="text-[10px] font-bold text-slate-400 uppercase text-right w-20">Total</TableHead>
              <TableHead className="text-[10px] font-bold text-slate-400 uppercase w-10">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((it, i) => {
              const flagged = it.needs_review;
              const missingPrice = flagged && (!it.unit_price || it.unit_price === 0);
              const missingTotal = flagged && (!it.total || it.total === 0);
              const missingQty = flagged && (!it.quantity || it.quantity === 0);
              const rowBg = flagged ? 'bg-amber-50/60' : i % 2 === 0 ? '' : 'bg-slate-50/40';

              return (
                <TableRow key={i} className={`${rowBg} transition-colors`} data-testid={`review-row-${i}`}>
                  <TableCell className="text-[10px] text-slate-400 tabular-nums">{i + 1}</TableCell>
                  <TableCell className="text-xs font-medium text-slate-800 max-w-[200px] truncate" title={it.raw_name}>
                    {it.raw_name || <span className="text-red-400 italic">No name</span>}
                  </TableCell>
                  <TableCell className="text-[10px] text-slate-400 font-mono">{it.item_code || '—'}</TableCell>
                  <TableCell className="text-right">
                    <EditableCell
                      value={it.quantity}
                      field="quantity"
                      itemIndex={i}
                      purchaseId={purchase.id}
                      api={api}
                      onSaved={handleItemSaved}
                      isMissing={missingQty}
                    />
                  </TableCell>
                  <TableCell className="text-right">
                    <EditableCell
                      value={it.unit_price}
                      field="unit_price"
                      itemIndex={i}
                      purchaseId={purchase.id}
                      api={api}
                      onSaved={handleItemSaved}
                      isMissing={missingPrice}
                    />
                  </TableCell>
                  <TableCell className="text-right">
                    <EditableCell
                      value={it.total}
                      field="total"
                      itemIndex={i}
                      purchaseId={purchase.id}
                      api={api}
                      onSaved={handleItemSaved}
                      isMissing={missingTotal}
                    />
                  </TableCell>
                  <TableCell className="text-center">
                    {flagged ? (
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-500 inline" />
                    ) : (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 inline" />
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {/* Footer — totals */}
      <div className="px-4 py-2.5 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
        <p className="text-[10px] text-slate-400">
          {reviewItems.length > 0 ? (
            <><AlertTriangle className="w-3 h-3 text-amber-500 inline mr-1" />{reviewItems.length} item{reviewItems.length !== 1 ? 's' : ''} need review — click missing values to edit</>
          ) : (
            <><CheckCircle2 className="w-3 h-3 text-emerald-500 inline mr-1" />All items verified</>
          )}
        </p>
        <div className="text-right">
          <p className="text-[10px] text-slate-400">Invoice Total</p>
          <p className="text-sm font-bold text-navy-900 tabular-nums" data-testid="review-invoice-total">{fmt(purchase.total)}</p>
        </div>
      </div>
    </Card>
  );
}
