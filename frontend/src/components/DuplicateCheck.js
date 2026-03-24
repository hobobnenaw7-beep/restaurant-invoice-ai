import { useState, useCallback, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { AlertTriangle, Loader2 } from 'lucide-react';

/**
 * Hook: call checkDuplicates(recordType, data, api) before saving.
 * Returns { checking, duplicates, showWarning, confirmSave, cancelSave, checkDuplicates }.
 */
export function useDuplicateCheck() {
  const [checking, setChecking] = useState(false);
  const [duplicates, setDuplicates] = useState([]);
  const [showWarning, setShowWarning] = useState(false);
  const pendingSaveRef = useRef(null);

  const checkDuplicates = useCallback(async (recordType, data, api, saveFn) => {
    setChecking(true);
    try {
      const res = await api.post('/duplicates/check', { record_type: recordType, data });
      if (res.data.has_duplicates) {
        setDuplicates(res.data.matches);
        pendingSaveRef.current = saveFn;
        setShowWarning(true);
        setChecking(false);
        return;
      }
    } catch {
      // If check fails, just proceed with save
    }
    setChecking(false);
    await saveFn();
  }, []);

  const confirmSave = useCallback(async () => {
    const saveFn = pendingSaveRef.current;
    pendingSaveRef.current = null;
    setShowWarning(false);
    setDuplicates([]);
    if (saveFn) await saveFn();
  }, []);

  const cancelSave = useCallback(() => {
    pendingSaveRef.current = null;
    setShowWarning(false);
    setDuplicates([]);
  }, []);

  return { checking, duplicates, showWarning, confirmSave, cancelSave, checkDuplicates };
}

function fmt(n) { return n != null ? `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : ''; }

export function DuplicateWarningDialog({ open, onClose, onConfirm, duplicates = [], saving }) {
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v && !saving) onClose(); }}>
      <DialogContent className="max-w-md" data-testid="duplicate-warning-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading text-lg flex items-center gap-2 text-amber-700">
            <div className="w-9 h-9 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
            </div>
            Possible Duplicate Detected
          </DialogTitle>
        </DialogHeader>

        <div className="py-3 space-y-3">
          <p className="text-sm text-slate-600">This record appears to have been entered before.</p>

          <div className="space-y-2 max-h-48 overflow-y-auto">
            {duplicates.map((d, i) => (
              <div key={d.id || i} className="bg-amber-50 border border-amber-200 rounded-lg p-3" data-testid={`duplicate-match-${i}`}>
                <p className="text-xs font-semibold text-amber-800">{d.reason}</p>
                <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1.5 text-[11px] text-amber-700">
                  {d.invoice_number && <span>Invoice: {d.invoice_number}</span>}
                  {d.supplier_name && <span>Vendor: {d.supplier_name}</span>}
                  {d.report_date && <span>Date: {d.report_date}</span>}
                  {d.invoice_date && <span>Date: {d.invoice_date}</span>}
                  {d.payment_date && <span>Date: {d.payment_date}</span>}
                  {d.expense_date && <span>Date: {d.expense_date}</span>}
                  {d.employee_name && <span>Employee: {d.employee_name}</span>}
                  {d.title && <span>Title: {d.title}</span>}
                  {d.total != null && <span>Total: {fmt(d.total)}</span>}
                  {d.total_sales != null && <span>Sales: {fmt(d.total_sales)}</span>}
                  {d.amount != null && <span>Amount: {fmt(d.amount)}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={onClose} className="h-9 text-xs" disabled={saving} data-testid="duplicate-cancel-btn">
            Cancel
          </Button>
          <Button onClick={onConfirm} disabled={saving} className="bg-amber-600 hover:bg-amber-700 text-white h-9 text-xs" data-testid="duplicate-save-anyway-btn">
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : null}
            Save Anyway
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
