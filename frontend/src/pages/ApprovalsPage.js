import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import {
  ClipboardCheck, Clock, CheckCircle2, XCircle, Search,
  DollarSign, Receipt, Users, Loader2, Filter
} from 'lucide-react';

function fmtMoney(n) {
  return n != null ? `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '$0.00';
}

function typeLabel(t) {
  return { sale: 'Sale', purchase: 'Raw Material', salary: 'Salary', other_expense: 'Other Expense' }[t] || t;
}

function typeBadge(t) {
  const map = {
    sale: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    purchase: 'bg-sky-100 text-sky-700 border-sky-200',
    salary: 'bg-violet-100 text-violet-700 border-violet-200',
    other_expense: 'bg-amber-100 text-amber-700 border-amber-200',
  };
  return map[t] || 'bg-slate-100 text-slate-600 border-slate-200';
}

function statusBadge(s) {
  if (s === 'approved') return 'bg-emerald-100 text-emerald-700';
  if (s === 'rejected') return 'bg-red-100 text-red-600';
  return 'bg-amber-100 text-amber-700';
}

function description(rec) {
  if (rec.record_type === 'purchase') return rec.supplier_name || 'Purchase';
  if (rec.record_type === 'salary') return rec.employee_name || 'Salary';
  if (rec.record_type === 'other_expense') return rec.title || rec.category || 'Expense';
  return 'Sale';
}

export default function ApprovalsPage() {
  const { api } = useAuth();
  const [records, setRecords] = useState([]);
  const [counts, setCounts] = useState({ total: 0, sale: 0, purchase: 0, salary: 0, other_expense: 0 });
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('all');
  const [statusFilter, setStatusFilter] = useState('pending');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [rejectDialog, setRejectDialog] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [processing, setProcessing] = useState('');

  const loadCounts = useCallback(async () => {
    try { const res = await api.get('/approvals/counts'); setCounts(res.data); } catch {}
  }, [api]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { status: statusFilter };
      if (tab !== 'all') params.record_type = tab;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await api.get('/approvals', { params });
      setRecords(res.data);
    } catch { toast.error('Failed to load approvals'); }
    finally { setLoading(false); }
  }, [api, tab, statusFilter, dateFrom, dateTo]);

  useEffect(() => { load(); loadCounts(); }, [load, loadCounts]);

  const handleApprove = async (rec) => {
    setProcessing(rec.record_id);
    try {
      await api.put(`/approvals/${rec.record_type}/${rec.record_id}`, { action: 'approve' });
      toast.success(`${typeLabel(rec.record_type)} approved`);
      load();
      loadCounts();
    } catch { toast.error('Approval failed'); }
    finally { setProcessing(''); }
  };

  const handleRejectConfirm = async () => {
    if (!rejectDialog) return;
    setProcessing(rejectDialog.record_id);
    try {
      await api.put(`/approvals/${rejectDialog.record_type}/${rejectDialog.record_id}`, {
        action: 'reject',
        reason: rejectReason || 'Rejected by manager',
      });
      toast.success(`${typeLabel(rejectDialog.record_type)} rejected`);
      setRejectDialog(null);
      setRejectReason('');
      load();
      loadCounts();
    } catch { toast.error('Rejection failed'); }
    finally { setProcessing(''); }
  };

  return (
    <div className="space-y-5 max-w-[1400px]" data-testid="approvals-page">
      {/* Header */}
      <div>
        <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight flex items-center gap-2">
          <ClipboardCheck className="w-6 h-6 text-teal-600" /> Approvals
        </h1>
        <p className="text-xs text-slate-400 mt-0.5">Review and approve pending sales, expenses, and records</p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {[
          { label: 'Total Pending', value: counts.total, icon: Clock, color: 'bg-amber-500' },
          { label: 'Sales', value: counts.sale, icon: DollarSign, color: 'bg-emerald-500' },
          { label: 'Purchases', value: counts.purchase, icon: Receipt, color: 'bg-sky-500' },
          { label: 'Salaries', value: counts.salary, icon: Users, color: 'bg-violet-500' },
          { label: 'Other', value: counts.other_expense, icon: Receipt, color: 'bg-amber-500' },
        ].map((c, i) => (
          <Card key={i} className="border border-slate-100 shadow-sm">
            <CardContent className="p-3 flex items-center gap-2.5">
              <div className={`w-8 h-8 rounded-lg ${c.color} flex items-center justify-center`}><c.icon className="w-4 h-4 text-white" /></div>
              <div><p className="text-lg font-extrabold text-navy-900">{c.value}</p><p className="text-[9px] text-slate-400 uppercase font-bold tracking-wider">{c.label}</p></div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="bg-slate-100 h-8" data-testid="approval-type-tabs">
            <TabsTrigger value="all" className="text-[11px] font-semibold px-3 h-7" data-testid="approval-tab-all">All</TabsTrigger>
            <TabsTrigger value="sale" className="text-[11px] font-semibold px-3 h-7" data-testid="approval-tab-sale">Sales</TabsTrigger>
            <TabsTrigger value="purchase" className="text-[11px] font-semibold px-3 h-7" data-testid="approval-tab-purchase">Purchases</TabsTrigger>
            <TabsTrigger value="salary" className="text-[11px] font-semibold px-3 h-7" data-testid="approval-tab-salary">Salaries</TabsTrigger>
            <TabsTrigger value="other_expense" className="text-[11px] font-semibold px-3 h-7" data-testid="approval-tab-other">Other</TabsTrigger>
          </TabsList>
        </Tabs>
        <Tabs value={statusFilter} onValueChange={setStatusFilter}>
          <TabsList className="bg-slate-100 h-8" data-testid="approval-status-tabs">
            <TabsTrigger value="pending" className="text-[11px] font-semibold px-3 h-7" data-testid="status-pending">Pending</TabsTrigger>
            <TabsTrigger value="approved" className="text-[11px] font-semibold px-3 h-7" data-testid="status-approved">Approved</TabsTrigger>
            <TabsTrigger value="rejected" className="text-[11px] font-semibold px-3 h-7" data-testid="status-rejected">Rejected</TabsTrigger>
          </TabsList>
        </Tabs>
        <Input type="date" className="h-8 text-xs w-36" value={dateFrom} onChange={e => setDateFrom(e.target.value)} data-testid="approval-date-from" />
        <Input type="date" className="h-8 text-xs w-36" value={dateTo} min={dateFrom} onChange={e => setDateTo(e.target.value)} data-testid="approval-date-to" />
      </div>

      {/* Records table */}
      {loading ? (
        <div className="space-y-2"><Skeleton className="h-12 rounded-lg" /><Skeleton className="h-12 rounded-lg" /><Skeleton className="h-12 rounded-lg" /></div>
      ) : records.length === 0 ? (
        <Card className="border border-slate-200/80 shadow-sm">
          <CardContent className="flex flex-col items-center py-14 text-center">
            <CheckCircle2 className="w-12 h-12 text-emerald-200 mb-3" />
            <h3 className="font-heading text-sm font-bold text-navy-900 mb-1">
              {statusFilter === 'pending' ? 'No pending approvals' : `No ${statusFilter} records`}
            </h3>
            <p className="text-xs text-slate-400">All caught up! Records requiring approval will appear here.</p>
          </CardContent>
        </Card>
      ) : (
        <Card className="border border-slate-200/80 shadow-sm overflow-hidden" data-testid="approvals-table-card">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Type</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Description</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Created By</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Date</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Amount</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Status</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Notes</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {records.map((rec, i) => (
                  <TableRow key={`${rec.record_type}-${rec.record_id}`} className={`${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} group`} data-testid={`approval-row-${i}`}>
                    <TableCell>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold border ${typeBadge(rec.record_type)}`}>
                        {typeLabel(rec.record_type)}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs font-medium text-navy-900">{description(rec)}</TableCell>
                    <TableCell className="text-xs text-slate-500">{rec.created_by_name || 'Unknown'}</TableCell>
                    <TableCell className="text-xs tabular-nums text-slate-500">{rec.date}</TableCell>
                    <TableCell className="text-xs text-right font-bold tabular-nums text-navy-900">{fmtMoney(rec.amount)}</TableCell>
                    <TableCell>
                      <Badge className={`text-[10px] font-bold px-2 py-0 h-5 capitalize ${statusBadge(rec.approval_status)}`} data-testid={`approval-status-${i}`}>
                        {rec.approval_status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-slate-400 max-w-[150px] truncate">
                      {rec.rejection_reason || rec.notes || '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      {rec.approval_status === 'pending' ? (
                        <div className="flex justify-end gap-1.5">
                          <Button
                            size="sm" className="h-7 text-[10px] font-bold bg-emerald-600 hover:bg-emerald-700 text-white px-3"
                            onClick={() => handleApprove(rec)}
                            disabled={processing === rec.record_id}
                            data-testid={`approve-btn-${i}`}
                          >
                            {processing === rec.record_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3 mr-1" />}
                            Approve
                          </Button>
                          <Button
                            variant="outline" size="sm" className="h-7 text-[10px] font-bold text-red-600 border-red-200 hover:bg-red-50 px-3"
                            onClick={() => { setRejectDialog(rec); setRejectReason(''); }}
                            disabled={processing === rec.record_id}
                            data-testid={`reject-btn-${i}`}
                          >
                            <XCircle className="w-3 h-3 mr-1" /> Reject
                          </Button>
                        </div>
                      ) : (
                        <span className="text-[10px] text-slate-400">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/50">
            <p className="text-[11px] text-slate-400">{records.length} record{records.length !== 1 ? 's' : ''}</p>
          </div>
        </Card>
      )}

      {/* Reject dialog */}
      <Dialog open={!!rejectDialog} onOpenChange={() => setRejectDialog(null)}>
        <DialogContent className="max-w-sm" data-testid="reject-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading text-base font-bold text-navy-900 flex items-center gap-2">
              <XCircle className="w-5 h-5 text-red-500" /> Reject Record
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-500 pt-1">
              Reject this {rejectDialog ? typeLabel(rejectDialog.record_type).toLowerCase() : 'record'} entry of {rejectDialog ? fmtMoney(rejectDialog.amount) : ''}?
            </DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <Textarea
              placeholder="Reason for rejection (optional)..."
              className="text-sm min-h-[80px]"
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
              data-testid="reject-reason-input"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" className="text-xs" onClick={() => setRejectDialog(null)} data-testid="reject-cancel-btn">Cancel</Button>
            <Button variant="destructive" size="sm" className="text-xs" onClick={handleRejectConfirm} disabled={processing === rejectDialog?.record_id} data-testid="reject-confirm-btn">
              {processing === rejectDialog?.record_id && <Loader2 className="w-3 h-3 animate-spin mr-1.5" />} Reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
