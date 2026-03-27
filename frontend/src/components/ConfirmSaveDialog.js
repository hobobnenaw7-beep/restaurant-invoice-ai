import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { CheckCircle } from 'lucide-react';

export function ConfirmSaveDialog({ open, onClose, onConfirm, vendor, date, total, saving }) {
  return (
    <AlertDialog open={open} onOpenChange={(v) => { if (!v && !saving) onClose(); }}>
      <AlertDialogContent data-testid="confirm-save-dialog">
        <AlertDialogHeader>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-teal-100 flex items-center justify-center flex-shrink-0">
              <CheckCircle className="w-5 h-5 text-teal-600" />
            </div>
            <AlertDialogTitle className="text-base font-bold text-navy-900">Confirm & Save</AlertDialogTitle>
          </div>
          <AlertDialogDescription className="sr-only">Review before saving</AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-3 py-2">
          <div className="flex justify-between items-center py-2 border-b border-slate-100">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Vendor</span>
            <span className="text-sm font-bold text-navy-900 text-right max-w-[60%] truncate" data-testid="confirm-vendor">{vendor || '—'}</span>
          </div>
          <div className="flex justify-between items-center py-2 border-b border-slate-100">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Date</span>
            <span className="text-sm font-bold text-navy-900 tabular-nums" data-testid="confirm-date">{date || '—'}</span>
          </div>
          <div className="flex justify-between items-center py-2">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total</span>
            <span className="text-lg font-bold text-teal-700 tabular-nums" data-testid="confirm-total">
              {typeof total === 'number' ? `$${total.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
            </span>
          </div>
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel className="text-xs h-9" disabled={saving} data-testid="confirm-save-back">Back</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={saving}
            className="bg-teal-600 hover:bg-teal-700 text-white text-xs h-9"
            data-testid="confirm-save-submit"
          >
            {saving ? 'Saving...' : 'Save'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
