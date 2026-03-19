import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import { Search, Plus, Edit, Trash2, Loader2, Users, ChevronRight } from 'lucide-react';

function fmt(n) { return n != null ? `$${Number(n).toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}` : '$0'; }

export default function VendorsPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: '', contact_person: '', phone: '', email: '', address: '' });
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try { const res = await api.get('/suppliers', { params: { search } }); setVendors(res.data); }
    catch { toast.error('Failed to load'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [search]); // eslint-disable-line

  const openNew = () => { setEditing(null); setForm({ name: '', contact_person: '', phone: '', email: '', address: '' }); setDialogOpen(true); };
  const openEdit = (s) => { setEditing(s); setForm({ name: s.name, contact_person: s.contact_person || '', phone: s.phone || '', email: s.email || '', address: s.address || '' }); setDialogOpen(true); };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (editing) await api.put(`/suppliers/${editing.id}`, form);
      else await api.post('/suppliers', form);
      toast.success(editing ? 'Updated' : 'Created');
      setDialogOpen(false); load();
    } catch { toast.error('Save failed'); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this vendor?')) return;
    try { await api.delete(`/suppliers/${id}`); toast.success('Deleted'); load(); } catch { toast.error('Failed'); }
  };

  return (
    <div className="space-y-6 max-w-[1400px]" data-testid="vendors-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-navy-900 tracking-tight">Vendors</h1>
          <p className="text-sm text-slate-400 mt-1">Manage vendors and track spending</p>
        </div>
        <Button onClick={openNew} className="bg-navy-900 hover:bg-navy-800 text-white h-10 px-5" data-testid="add-vendor-btn">
          <Plus className="w-4 h-4 mr-2" /> Add Vendor
        </Button>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <Input className="pl-9 h-10" placeholder="Search vendors..." value={search} onChange={(e) => setSearch(e.target.value)} data-testid="search-vendors" />
      </div>

      <Card className="border border-slate-100 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-6 space-y-3">{[1,2,3].map(i => <Skeleton key={i} className="h-14 w-full rounded-lg" />)}</div>
        ) : vendors.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4"><Users className="w-6 h-6 text-slate-300" /></div>
            <h3 className="font-heading text-base font-bold text-navy-900 mb-1">No vendors yet</h3>
            <p className="text-sm text-slate-400">Add your first vendor to start tracking.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Vendor</TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Contact</TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Phone</TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Total Spent</TableHead>
                  <TableHead className="text-[11px] font-bold text-slate-500 uppercase tracking-wider text-center">Invoices</TableHead>
                  <TableHead className="w-20" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {vendors.map((s, i) => (
                  <TableRow key={s.id} className={`transition-colors cursor-pointer ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} hover:bg-teal-50/30`} onClick={() => navigate(`/vendors/${s.id}`)} data-testid={`vendor-row-${i}`}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-navy-900 text-white flex items-center justify-center text-[11px] font-bold flex-shrink-0">{s.name?.charAt(0)}</div>
                        <span className="text-sm font-semibold text-navy-900">{s.name}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-slate-500">{s.contact_person || '—'}</TableCell>
                    <TableCell className="text-sm text-slate-500 tabular-nums">{s.phone || '—'}</TableCell>
                    <TableCell className="text-sm text-right font-bold text-navy-900 tabular-nums">{fmt(s.total_spending)}</TableCell>
                    <TableCell className="text-sm text-center text-slate-500">{s.invoice_count || 0}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-0.5">
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={(e) => { e.stopPropagation(); openEdit(s); }}><Edit className="w-3.5 h-3.5 text-slate-500" /></Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={(e) => { e.stopPropagation(); handleDelete(s.id); }}><Trash2 className="w-3.5 h-3.5 text-red-400" /></Button>
                        <ChevronRight className="w-4 h-4 text-slate-300 ml-1 self-center" />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-heading text-lg">{editing ? 'Edit Vendor' : 'New Vendor'}</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Vendor Name</Label><Input className="mt-1.5 h-10" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="input-vendor-name" /></div>
            <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Contact Person</Label><Input className="mt-1.5 h-10" value={form.contact_person} onChange={(e) => setForm({ ...form, contact_person: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Phone</Label><Input className="mt-1.5 h-10" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></div>
              <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Email</Label><Input className="mt-1.5 h-10" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
            </div>
            <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Address</Label><Input className="mt-1.5 h-10" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving || !form.name} className="bg-teal-600 hover:bg-teal-700 text-white" data-testid="save-vendor-btn">
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null} Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
