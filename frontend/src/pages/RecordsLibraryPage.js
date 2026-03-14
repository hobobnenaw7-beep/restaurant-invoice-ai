import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import {
  FolderOpen, DollarSign, Receipt, Search, Download,
  Trash2, Eye, FileText, Image as ImageIcon, Sheet,
  File, X, Loader2, FolderArchive, Upload, ChevronUp,
  ChevronDown, AlertTriangle, ShieldCheck
} from 'lucide-react';

function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}
function fmtMoney(n) {
  return n != null && n !== 0 ? `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '';
}
function fileIcon(ext) {
  const e = (ext || '').toLowerCase();
  if (['jpg','jpeg','png','webp','gif','heic'].includes(e)) return <ImageIcon className="w-4 h-4 text-sky-500" />;
  if (e === 'pdf') return <FileText className="w-4 h-4 text-red-500" />;
  if (['xlsx','xls','csv'].includes(e)) return <Sheet className="w-4 h-4 text-emerald-500" />;
  return <File className="w-4 h-4 text-slate-400" />;
}
function typeLabel(ext) {
  const e = (ext || '').toLowerCase();
  if (['jpg','jpeg','png','webp','gif','heic'].includes(e)) return 'Image';
  if (e === 'pdf') return 'PDF';
  if (['xlsx','xls','csv'].includes(e)) return 'Excel';
  return e.toUpperCase() || 'File';
}
function typeBadgeColor(ext) {
  const e = (ext || '').toLowerCase();
  if (['jpg','jpeg','png','webp','gif','heic'].includes(e)) return 'bg-sky-100 text-sky-700 border-sky-200';
  if (e === 'pdf') return 'bg-red-50 text-red-600 border-red-200';
  if (['xlsx','xls','csv'].includes(e)) return 'bg-emerald-50 text-emerald-600 border-emerald-200';
  return 'bg-slate-100 text-slate-600 border-slate-200';
}
function transactionLabel(t) {
  return { sale: 'Sale', raw_material: 'Raw Material', salary: 'Salary', other_expense: 'Other Expense' }[t] || t || '—';
}

// ======================== FILE PREVIEW DIALOG ========================
function FilePreviewDialog({ record, open, onClose, api }) {
  const [fileUrl, setFileUrl] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !record) { setFileUrl(null); return; }
    let revoke;
    setLoading(true);
    api.get(`/records/${record.id}/file`, { responseType: 'blob' })
      .then(res => { const url = URL.createObjectURL(res.data); setFileUrl(url); revoke = url; })
      .catch(() => toast.error('Failed to load file'))
      .finally(() => setLoading(false));
    return () => { if (revoke) URL.revokeObjectURL(revoke); };
  }, [open, record?.id]);

  if (!record) return null;
  const ext = (record.file_extension || '').toLowerCase();
  const isImage = ['jpg','jpeg','png','webp','gif','heic'].includes(ext);
  const isPdf = ext === 'pdf';

  const handleDownload = () => {
    if (!fileUrl) return;
    const a = document.createElement('a'); a.href = fileUrl; a.download = record.file_name;
    document.body.appendChild(a); a.click(); a.remove();
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-hidden flex flex-col" data-testid="file-preview-dialog">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="font-heading text-base font-bold text-navy-900 flex items-center gap-2">
            {fileIcon(ext)} {record.file_name}
          </DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto space-y-4 min-h-0">
          <div className="rounded-xl border border-slate-200 bg-slate-50 min-h-[200px] flex items-center justify-center overflow-hidden" data-testid="file-preview-area">
            {loading ? <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
            : isImage && fileUrl ? <img src={fileUrl} alt={record.file_name} className="max-w-full max-h-[400px] object-contain" />
            : isPdf && fileUrl ? <iframe src={fileUrl} title={record.file_name} className="w-full h-[400px] border-0" />
            : <div className="text-center py-12"><File className="w-10 h-10 text-slate-300 mx-auto mb-2" /><p className="text-xs text-slate-400">Preview not available for this file type</p><Button variant="outline" size="sm" className="mt-3 text-xs" onClick={handleDownload}><Download className="w-3 h-3 mr-1.5" /> Download to view</Button></div>}
          </div>
          <Card className="border border-slate-200/80 shadow-sm" data-testid="transaction-details-card">
            <CardContent className="p-4 space-y-3">
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Linked Transaction</p>
              <div className="grid grid-cols-2 gap-3">
                <div><p className="text-[10px] text-slate-400">Transaction Type</p><p className="text-xs font-semibold text-navy-900">{transactionLabel(record.transaction_type)}</p></div>
                <div><p className="text-[10px] text-slate-400">Transaction ID</p><p className="text-xs font-mono text-slate-600 truncate">{record.transaction_id || '—'}</p></div>
                <div><p className="text-[10px] text-slate-400">Date</p><p className="text-xs font-semibold text-navy-900">{record.transaction_date || '—'}</p></div>
                <div><p className="text-[10px] text-slate-400">Amount</p><p className="text-xs font-bold text-navy-900">{record.transaction_amount ? fmtMoney(record.transaction_amount) : '—'}</p></div>
                {record.vendor_name && <div><p className="text-[10px] text-slate-400">Vendor</p><p className="text-xs font-semibold text-navy-900">{record.vendor_name}</p></div>}
                {record.transaction_notes && <div className="col-span-2"><p className="text-[10px] text-slate-400">Notes</p><p className="text-xs text-slate-600">{record.transaction_notes}</p></div>}
              </div>
              <div className="border-t border-slate-100 pt-3 mt-3">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">File Info</p>
                <div className="grid grid-cols-3 gap-3">
                  <div><p className="text-[10px] text-slate-400">Type</p><p className="text-xs text-slate-600">{typeLabel(record.file_extension)}</p></div>
                  <div><p className="text-[10px] text-slate-400">Size</p><p className="text-xs text-slate-600">{fmtSize(record.file_size)}</p></div>
                  <div><p className="text-[10px] text-slate-400">Uploaded</p><p className="text-xs text-slate-600">{record.upload_date}</p></div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-2 border-t border-slate-100 mt-2">
                <ShieldCheck className="w-3.5 h-3.5 text-teal-500" />
                <p className="text-[10px] text-teal-600 font-medium">Permanently stored for tax and audit purposes</p>
              </div>
            </CardContent>
          </Card>
        </div>
        <div className="flex justify-end gap-2 pt-3 border-t border-slate-100 flex-shrink-0">
          <Button variant="outline" size="sm" className="text-xs" onClick={handleDownload} disabled={!fileUrl} data-testid="preview-download-btn"><Download className="w-3 h-3 mr-1.5" /> Download</Button>
          <Button variant="outline" size="sm" className="text-xs" onClick={() => onClose(false)}><X className="w-3 h-3 mr-1.5" /> Close</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ======================== DELETE CONFIRMATION DIALOG ========================
function DeleteConfirmDialog({ record, open, onClose, onConfirm, deleting }) {
  if (!record) return null;
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md" data-testid="delete-confirm-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading text-base font-bold text-navy-900 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-500" /> Delete Record
          </DialogTitle>
          <DialogDescription className="text-xs text-slate-500 pt-2">
            This file is stored for <span className="font-semibold text-navy-900">tax and audit purposes</span>.
            Deleting it will permanently remove it from your records. This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 my-2">
          <div className="flex items-center gap-2">
            {fileIcon(record.file_extension)}
            <div className="min-w-0">
              <p className="text-xs font-semibold text-navy-900 truncate">{record.file_name}</p>
              <p className="text-[10px] text-slate-400">{transactionLabel(record.transaction_type)} &middot; {record.upload_date}</p>
            </div>
          </div>
        </div>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" size="sm" className="text-xs" onClick={() => onClose(false)} data-testid="delete-cancel-btn">Cancel</Button>
          <Button variant="destructive" size="sm" className="text-xs" onClick={onConfirm} disabled={deleting} data-testid="delete-confirm-btn">
            {deleting ? <Loader2 className="w-3 h-3 animate-spin mr-1.5" /> : <Trash2 className="w-3 h-3 mr-1.5" />} Delete Permanently
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ======================== BULK UPLOAD ZONE ========================
function BulkUploadZone({ folder, api, onUploaded }) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0, errors: [] });
  const fileInputRef = useRef(null);

  const uploadFiles = async (files) => {
    if (!files.length) return;
    setUploading(true);
    setProgress({ done: 0, total: files.length, errors: [] });
    const errors = [];
    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      try {
        const fd = new FormData();
        fd.append('file', f);
        fd.append('folder', folder);
        fd.append('transaction_type', '');
        fd.append('transaction_id', '');
        fd.append('transaction_date', '');
        fd.append('transaction_amount', 0);
        fd.append('transaction_notes', '');
        fd.append('vendor_name', '');
        await api.post('/records/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      } catch (err) {
        const msg = err.response?.data?.detail || 'Upload failed';
        errors.push({ name: f.name, error: msg });
      }
      setProgress(p => ({ ...p, done: i + 1 }));
    }
    setProgress(p => ({ ...p, errors }));
    setUploading(false);
    const successCount = files.length - errors.length;
    if (successCount > 0) toast.success(`${successCount} file${successCount > 1 ? 's' : ''} uploaded`);
    if (errors.length > 0) {
      errors.forEach(e => toast.error(`${e.name}: ${e.error}`, { duration: 5000 }));
    }
    onUploaded();
  };

  const handleDrop = (e) => {
    e.preventDefault(); setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length) uploadFiles(files);
  };
  const handleFileInput = (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length) uploadFiles(files);
    e.target.value = '';
  };

  return (
    <div
      className={`rounded-xl border-2 border-dashed transition-colors p-5 text-center ${
        dragging ? 'border-teal-400 bg-teal-50/50' : 'border-slate-200 bg-slate-50/30 hover:border-slate-300'
      }`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      data-testid="bulk-upload-zone"
    >
      {uploading ? (
        <div className="space-y-2">
          <Loader2 className="w-6 h-6 animate-spin text-teal-600 mx-auto" />
          <p className="text-xs font-semibold text-navy-900">Uploading {progress.done}/{progress.total} files...</p>
          <div className="w-48 h-1.5 bg-slate-200 rounded-full mx-auto overflow-hidden">
            <div className="h-full bg-teal-500 rounded-full transition-all" style={{ width: `${(progress.done / progress.total) * 100}%` }} />
          </div>
        </div>
      ) : (
        <>
          <Upload className={`w-7 h-7 mx-auto mb-2 ${dragging ? 'text-teal-500' : 'text-slate-300'}`} />
          <p className="text-xs font-semibold text-navy-900 mb-1">
            {dragging ? 'Drop files here' : 'Drag & drop files here'}
          </p>
          <p className="text-[10px] text-slate-400 mb-3">or click to browse &middot; Images, PDFs, Excel files</p>
          <Button variant="outline" size="sm" className="text-xs h-8" onClick={() => fileInputRef.current?.click()} data-testid="bulk-upload-browse-btn">
            <Upload className="w-3 h-3 mr-1.5" /> Browse Files
          </Button>
          <input ref={fileInputRef} type="file" className="hidden" multiple accept="image/*,.pdf,.xlsx,.xls,.csv" onChange={handleFileInput} />
        </>
      )}
    </div>
  );
}

// ======================== SORT HEADER ========================
function SortHead({ label, field, sortBy, sortOrder, onSort, align, testId }) {
  const active = sortBy === field;
  return (
    <TableHead
      className={`text-[10px] font-bold text-slate-500 uppercase tracking-wider cursor-pointer select-none hover:text-navy-900 transition-colors ${align === 'right' ? 'text-right' : ''}`}
      onClick={() => onSort(field)}
      data-testid={testId}
    >
      <span className="inline-flex items-center gap-0.5">
        {label}
        {active && (sortOrder === 'desc' ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />)}
      </span>
    </TableHead>
  );
}

// ======================== MAIN PAGE ========================
export default function RecordsLibraryPage() {
  const { api } = useAuth();
  const [folder, setFolder] = useState('sales');
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [fileType, setFileType] = useState('');
  const [sortBy, setSortBy] = useState('upload_date');
  const [sortOrder, setSortOrder] = useState('desc');
  const [previewRecord, setPreviewRecord] = useState(null);
  const [deleteRecord, setDeleteRecord] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { folder, sort_by: sortBy, sort_order: sortOrder };
      if (search) params.search = search;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      if (fileType) params.file_type = fileType;
      const res = await api.get('/records', { params });
      setRecords(res.data);
    } catch { toast.error('Failed to load records'); }
    finally { setLoading(false); }
  }, [api, folder, search, dateFrom, dateTo, fileType, sortBy, sortOrder]);

  useEffect(() => { load(); }, [load]);

  const handleSort = (field) => {
    if (sortBy === field) {
      setSortOrder(o => o === 'desc' ? 'asc' : 'desc');
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteRecord) return;
    setDeleting(true);
    try {
      await api.delete(`/records/${deleteRecord.id}`);
      toast.success('File deleted');
      setDeleteRecord(null);
      load();
    } catch { toast.error('Delete failed'); }
    finally { setDeleting(false); }
  };

  const handleDownload = async (rec) => {
    try {
      const res = await api.get(`/records/${rec.id}/file`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a'); a.href = url; a.download = rec.file_name;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { toast.error('Download failed'); }
  };

  const folderLabel = folder === 'sales' ? 'Sales Files' : 'Expense Files';

  return (
    <div className="space-y-5 max-w-[1400px]" data-testid="records-library-page">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight flex items-center gap-2">
          <FolderArchive className="w-6 h-6 text-teal-600" /> Records Library
        </h1>
        <p className="text-xs text-slate-400 mt-0.5">Permanently stored documents for tax and audit purposes</p>
      </div>

      <Tabs value={folder} onValueChange={(v) => { setFolder(v); setSearch(''); setDateFrom(''); setDateTo(''); setFileType(''); setSortBy('upload_date'); setSortOrder('desc'); }}>
        <TabsList className="bg-slate-100 h-10" data-testid="folder-tabs">
          <TabsTrigger value="sales" className="text-xs font-semibold px-4 gap-2" data-testid="folder-tab-sales">
            <DollarSign className="w-4 h-4" /> Sales Files
          </TabsTrigger>
          <TabsTrigger value="expenses" className="text-xs font-semibold px-4 gap-2" data-testid="folder-tab-expenses">
            <Receipt className="w-4 h-4" /> Expense Files
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Bulk upload */}
      <BulkUploadZone folder={folder} api={api} onUploaded={load} />

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3" data-testid="records-filters">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input className="pl-9 h-9 text-sm" placeholder="Search by file name..." value={search} onChange={(e) => setSearch(e.target.value)} data-testid="records-search" />
        </div>
        <Input type="date" className="h-9 text-xs w-36" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} data-testid="records-date-from" />
        <Input type="date" className="h-9 text-xs w-36" value={dateTo} min={dateFrom} onChange={(e) => setDateTo(e.target.value)} data-testid="records-date-to" />
        <Select value={fileType} onValueChange={setFileType}>
          <SelectTrigger className="h-9 w-36 text-xs" data-testid="records-file-type-filter"><SelectValue placeholder="All Types" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all" className="text-xs">All Types</SelectItem>
            <SelectItem value="image" className="text-xs">Images</SelectItem>
            <SelectItem value="pdf" className="text-xs">PDF</SelectItem>
            <SelectItem value="excel" className="text-xs">Excel/CSV</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Content */}
      {loading ? (
        <div className="space-y-2"><Skeleton className="h-12 rounded-lg" /><Skeleton className="h-12 rounded-lg" /><Skeleton className="h-12 rounded-lg" /></div>
      ) : records.length === 0 ? (
        <Card className="border border-slate-200/80 shadow-sm">
          <CardContent className="flex flex-col items-center py-14 text-center">
            <FolderOpen className="w-12 h-12 text-slate-300 mb-3" />
            <h3 className="font-heading text-sm font-bold text-navy-900 mb-1">{folderLabel} is empty</h3>
            <p className="text-xs text-slate-400 max-w-xs">
              Upload files above or add {folder === 'sales' ? 'sales' : 'expenses'} with attachments to populate this archive.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card className="border border-slate-200/80 shadow-sm overflow-hidden" data-testid="records-table-card">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider w-10"></TableHead>
                  <SortHead label="File Name" field="name" sortBy={sortBy} sortOrder={sortOrder} onSort={handleSort} testId="sort-name" />
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Type</TableHead>
                  <SortHead label="Upload Date" field="upload_date" sortBy={sortBy} sortOrder={sortOrder} onSort={handleSort} testId="sort-date" />
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Transaction</TableHead>
                  <SortHead label="Amount" field="amount" sortBy={sortBy} sortOrder={sortOrder} onSort={handleSort} align="right" testId="sort-amount" />
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Size</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {records.map((rec, i) => (
                  <TableRow key={rec.id} className={`${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} group`} data-testid={`record-row-${i}`}>
                    <TableCell className="w-10 pr-0">{fileIcon(rec.file_extension)}</TableCell>
                    <TableCell>
                      <button className="text-xs font-medium text-navy-900 hover:text-teal-600 transition-colors text-left truncate max-w-[200px] block" onClick={() => setPreviewRecord(rec)} data-testid={`record-name-${i}`}>
                        {rec.file_name}
                      </button>
                    </TableCell>
                    <TableCell>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold border ${typeBadgeColor(rec.file_extension)}`}>
                        {typeLabel(rec.file_extension)}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs tabular-nums text-slate-500">{rec.upload_date}</TableCell>
                    <TableCell>
                      <div className="text-xs">
                        <span className="font-medium text-navy-900">{transactionLabel(rec.transaction_type)}</span>
                        {rec.vendor_name && <span className="text-slate-400 ml-1">({rec.vendor_name})</span>}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-right font-semibold tabular-nums text-navy-900">
                      {rec.transaction_amount ? fmtMoney(rec.transaction_amount) : '—'}
                    </TableCell>
                    <TableCell className="text-xs text-slate-400">{fmtSize(rec.file_size)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setPreviewRecord(rec)} data-testid={`record-preview-${i}`}>
                          <Eye className="w-3.5 h-3.5 text-slate-500" />
                        </Button>
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => handleDownload(rec)} data-testid={`record-download-${i}`}>
                          <Download className="w-3.5 h-3.5 text-slate-500" />
                        </Button>
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setDeleteRecord(rec)} data-testid={`record-delete-${i}`}>
                          <Trash2 className="w-3.5 h-3.5 text-red-400" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between">
            <p className="text-[11px] text-slate-400">{records.length} file{records.length !== 1 ? 's' : ''} in {folderLabel}</p>
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="w-3 h-3 text-teal-500" />
              <p className="text-[10px] text-teal-600 font-medium">Stored for tax & audit</p>
            </div>
          </div>
        </Card>
      )}

      <FilePreviewDialog record={previewRecord} open={!!previewRecord} onClose={() => setPreviewRecord(null)} api={api} />
      <DeleteConfirmDialog record={deleteRecord} open={!!deleteRecord} onClose={() => setDeleteRecord(null)} onConfirm={handleDeleteConfirm} deleting={deleting} />
    </div>
  );
}
