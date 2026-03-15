import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import {
  Users, Plus, Pencil, Trash2, ShieldCheck, ShieldOff,
  Loader2, UserCog, Search, Crown, Calculator, Receipt, User, KeyRound
} from 'lucide-react';

const ROLES = [
  { value: 'manager', label: 'Manager', icon: Crown, color: 'bg-violet-100 text-violet-700 border-violet-200' },
  { value: 'accountant', label: 'Accountant', icon: Calculator, color: 'bg-sky-100 text-sky-700 border-sky-200' },
  { value: 'cashier', label: 'Cashier', icon: Receipt, color: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  { value: 'staff', label: 'Staff', icon: User, color: 'bg-slate-100 text-slate-600 border-slate-200' },
];

const PERMISSION_GROUPS = [
  {
    label: 'Sales',
    permissions: [
      { key: 'can_add_sales', label: 'Add sales' },
      { key: 'can_edit_sales', label: 'Edit sales' },
      { key: 'can_delete_sales', label: 'Delete sales' },
    ],
  },
  {
    label: 'Expenses',
    permissions: [
      { key: 'can_add_expenses', label: 'Add expenses' },
      { key: 'can_edit_expenses', label: 'Edit expenses' },
      { key: 'can_delete_expenses', label: 'Delete expenses' },
    ],
  },
  {
    label: 'Files & Reports',
    permissions: [
      { key: 'can_upload_files', label: 'Upload files' },
      { key: 'can_view_reports', label: 'View reports' },
      { key: 'can_export_reports', label: 'Export reports' },
      { key: 'can_view_records', label: 'View records library' },
    ],
  },
  {
    label: 'Management',
    permissions: [
      { key: 'can_manage_vendors', label: 'Manage vendors' },
      { key: 'can_manage_items', label: 'Manage items' },
      { key: 'can_manage_users', label: 'Manage users' },
    ],
  },
];

const ALL_KEYS = PERMISSION_GROUPS.flatMap(g => g.permissions.map(p => p.key));
const ALL_TRUE = Object.fromEntries(ALL_KEYS.map(k => [k, true]));

function roleConfig(role) {
  return ROLES.find(r => r.value === role) || ROLES[3];
}

function permCount(perms) {
  if (!perms) return 0;
  return ALL_KEYS.filter(k => perms[k]).length;
}

const emptyForm = { name: '', email: '', password: '', role: 'staff' };

// ======================== PERMISSIONS PANEL ========================
function PermissionsPanel({ permissions, onChange, disabled }) {
  const allChecked = ALL_KEYS.every(k => permissions[k]);
  const noneChecked = ALL_KEYS.every(k => !permissions[k]);

  const toggleAll = (checked) => {
    const next = {};
    ALL_KEYS.forEach(k => { next[k] = checked; });
    onChange(next);
  };

  return (
    <div className="space-y-3" data-testid="permissions-panel">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <KeyRound className="w-3.5 h-3.5 text-teal-600" />
          <span className="text-xs font-bold text-navy-900">Permissions</span>
          <Badge className="text-[9px] bg-slate-100 text-slate-500 h-4 px-1.5">{permCount(permissions)}/{ALL_KEYS.length}</Badge>
        </div>
        <div className="flex gap-2">
          <button type="button" className="text-[10px] font-semibold text-teal-600 hover:text-teal-700" onClick={() => toggleAll(true)} disabled={disabled} data-testid="perm-select-all">Select All</button>
          <button type="button" className="text-[10px] font-semibold text-slate-400 hover:text-slate-600" onClick={() => toggleAll(false)} disabled={disabled} data-testid="perm-clear-all">Clear All</button>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {PERMISSION_GROUPS.map(group => (
          <div key={group.label} className="rounded-lg border border-slate-200/80 bg-slate-50/50 p-3">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">{group.label}</p>
            <div className="space-y-2">
              {group.permissions.map(perm => (
                <label key={perm.key} className="flex items-center gap-2 cursor-pointer group" data-testid={`perm-${perm.key}`}>
                  <Checkbox
                    checked={!!permissions[perm.key]}
                    onCheckedChange={(checked) => onChange({ ...permissions, [perm.key]: !!checked })}
                    disabled={disabled}
                    className="h-3.5 w-3.5"
                    data-testid={`perm-check-${perm.key}`}
                  />
                  <span className="text-xs text-slate-600 group-hover:text-navy-900 transition-colors">{perm.label}</span>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ======================== MAIN PAGE ========================
export default function UserManagementPage() {
  const { api, user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showDialog, setShowDialog] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [permissions, setPermissions] = useState({});
  const [defaults, setDefaults] = useState({});
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [usersRes, defaultsRes] = await Promise.all([
        api.get('/users'),
        api.get('/users/permissions/defaults'),
      ]);
      setUsers(usersRes.data);
      setDefaults(defaultsRes.data);
    } catch (err) {
      if (err.response?.status === 403) toast.error('Manager access required');
      else toast.error('Failed to load users');
    } finally { setLoading(false); }
  }, [api]);

  useEffect(() => { load(); }, [load]);

  const openAdd = () => {
    setEditingUser(null);
    setForm(emptyForm);
    setPermissions(defaults['staff'] || {});
    setShowDialog(true);
  };

  const openEdit = (u) => {
    setEditingUser(u);
    setForm({ name: u.name, email: u.email, password: '', role: u.role });
    setPermissions(u.permissions || defaults[u.role] || {});
    setShowDialog(true);
  };

  const handleRoleChange = (role) => {
    setForm(f => ({ ...f, role }));
    // Apply role defaults but only if user hasn't customized permissions yet
    if (!editingUser) {
      setPermissions(defaults[role] || {});
    }
  };

  const handleSave = async () => {
    if (!form.name.trim() || !form.email.trim()) {
      toast.error('Name and email are required'); return;
    }
    if (!editingUser && (!form.password || form.password.length < 6)) {
      toast.error('Password must be at least 6 characters'); return;
    }
    setSaving(true);
    try {
      if (editingUser) {
        const payload = { name: form.name, email: form.email, role: form.role, permissions };
        if (form.password) payload.password = form.password;
        await api.put(`/users/${editingUser.id}`, payload);
        toast.success('User updated');
      } else {
        await api.post('/users', { ...form, permissions });
        toast.success('User created');
      }
      setShowDialog(false);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const handleToggleStatus = async (u) => {
    const newStatus = u.status === 'active' ? 'inactive' : 'active';
    try {
      await api.put(`/users/${u.id}`, { status: newStatus });
      toast.success(`${u.name} ${newStatus === 'active' ? 'activated' : 'deactivated'}`);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update status');
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/users/${deleteTarget.id}`);
      toast.success('User deleted');
      setDeleteTarget(null);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Delete failed');
    } finally { setDeleting(false); }
  };

  const filtered = users.filter(u =>
    u.name.toLowerCase().includes(search.toLowerCase()) ||
    u.email.toLowerCase().includes(search.toLowerCase()) ||
    u.role.toLowerCase().includes(search.toLowerCase())
  );

  const counts = { total: users.length, active: users.filter(u => u.status === 'active').length, inactive: users.filter(u => u.status === 'inactive').length };

  return (
    <div className="space-y-5 max-w-[1200px]" data-testid="user-management-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight flex items-center gap-2">
            <UserCog className="w-6 h-6 text-teal-600" /> User Management
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">Manage team members, roles, and permissions</p>
        </div>
        <Button className="bg-teal-600 hover:bg-teal-700 text-white h-9 text-xs font-semibold" onClick={openAdd} data-testid="add-user-btn">
          <Plus className="w-3.5 h-3.5 mr-1.5" /> Add User
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <Card className="border border-slate-100 shadow-sm"><CardContent className="p-4 flex items-center gap-3"><div className="w-9 h-9 rounded-lg bg-navy-900 flex items-center justify-center"><Users className="w-4 h-4 text-white" /></div><div><p className="text-xl font-extrabold text-navy-900">{counts.total}</p><p className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Total Users</p></div></CardContent></Card>
        <Card className="border border-emerald-200/80 shadow-sm"><CardContent className="p-4 flex items-center gap-3"><div className="w-9 h-9 rounded-lg bg-emerald-500 flex items-center justify-center"><ShieldCheck className="w-4 h-4 text-white" /></div><div><p className="text-xl font-extrabold text-emerald-600">{counts.active}</p><p className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Active</p></div></CardContent></Card>
        <Card className="border border-slate-200/80 shadow-sm"><CardContent className="p-4 flex items-center gap-3"><div className="w-9 h-9 rounded-lg bg-slate-400 flex items-center justify-center"><ShieldOff className="w-4 h-4 text-white" /></div><div><p className="text-xl font-extrabold text-slate-500">{counts.inactive}</p><p className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Inactive</p></div></CardContent></Card>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <Input className="pl-9 h-9 text-sm" placeholder="Search by name, email, or role..." value={search} onChange={e => setSearch(e.target.value)} data-testid="user-search" />
      </div>

      {/* Users table */}
      {loading ? (
        <div className="flex items-center justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-teal-600" /></div>
      ) : (
        <Card className="border border-slate-200/80 shadow-sm overflow-hidden" data-testid="users-table-card">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Name</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Email</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Role</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Permissions</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Status</TableHead>
                  <TableHead className="text-[10px] font-bold text-slate-500 uppercase tracking-wider text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((u, i) => {
                  const rc = roleConfig(u.role);
                  const isSelf = u.id === currentUser?.id;
                  const pc = permCount(u.permissions);
                  return (
                    <TableRow key={u.id} className={`${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'} group`} data-testid={`user-row-${i}`}>
                      <TableCell>
                        <div className="flex items-center gap-2.5">
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${u.status === 'active' ? 'bg-teal-600 text-white' : 'bg-slate-300 text-slate-500'}`}>
                            {u.name?.charAt(0)?.toUpperCase() || '?'}
                          </div>
                          <p className="text-xs font-semibold text-navy-900">{u.name}{isSelf && <span className="text-[10px] text-slate-400 ml-1">(You)</span>}</p>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-slate-500">{u.email}</TableCell>
                      <TableCell>
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold border ${rc.color}`}>
                          <rc.icon className="w-3 h-3" /> {rc.label}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className="text-[10px] font-semibold text-slate-500" data-testid={`user-perm-count-${i}`}>{pc}/{ALL_KEYS.length}</span>
                      </TableCell>
                      <TableCell>
                        <Badge className={`text-[10px] font-bold px-2 py-0 h-5 ${u.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`} data-testid={`user-status-${i}`}>
                          {u.status === 'active' ? 'Active' : 'Inactive'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => openEdit(u)} data-testid={`edit-user-${i}`}><Pencil className="w-3.5 h-3.5 text-slate-500" /></Button>
                          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => handleToggleStatus(u)} disabled={isSelf} data-testid={`toggle-status-${i}`}>
                            {u.status === 'active' ? <ShieldOff className="w-3.5 h-3.5 text-amber-500" /> : <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />}
                          </Button>
                          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setDeleteTarget(u)} disabled={isSelf} data-testid={`delete-user-${i}`}><Trash2 className="w-3.5 h-3.5 text-red-400" /></Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {filtered.length === 0 && <TableRow><TableCell colSpan={6} className="text-center py-12 text-sm text-slate-400">No users found</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}

      {/* Add/Edit dialog with permissions */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-hidden flex flex-col" data-testid="user-dialog">
          <DialogHeader className="flex-shrink-0">
            <DialogTitle className="font-heading text-base font-bold text-navy-900">
              {editingUser ? 'Edit User' : 'Add New User'}
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-400">
              {editingUser ? 'Update user details and permissions.' : 'Create a new team member with role-based permissions.'}
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto space-y-4 py-2 min-h-0 pr-1">
            {/* Basic fields */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs font-semibold text-slate-600">Full Name</Label>
                <Input className="mt-1 h-9 text-sm" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="John Smith" data-testid="user-name-input" />
              </div>
              <div>
                <Label className="text-xs font-semibold text-slate-600">Email</Label>
                <Input className="mt-1 h-9 text-sm" type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} placeholder="john@restaurant.com" data-testid="user-email-input" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs font-semibold text-slate-600">
                  Password {editingUser && <span className="text-slate-400 font-normal">(blank = keep)</span>}
                </Label>
                <Input className="mt-1 h-9 text-sm" type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} placeholder={editingUser ? '••••••••' : 'Min 6 chars'} data-testid="user-password-input" />
              </div>
              <div>
                <Label className="text-xs font-semibold text-slate-600">Role</Label>
                <Select value={form.role} onValueChange={handleRoleChange}>
                  <SelectTrigger className="mt-1 h-9 text-sm" data-testid="user-role-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ROLES.map(r => <SelectItem key={r.value} value={r.value} className="text-xs"><span className="flex items-center gap-2"><r.icon className="w-3.5 h-3.5" /> {r.label}</span></SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Divider */}
            <div className="border-t border-slate-200/80 pt-3">
              <PermissionsPanel
                permissions={permissions}
                onChange={setPermissions}
                disabled={form.role === 'manager'}
              />
              {form.role === 'manager' && (
                <p className="text-[10px] text-teal-600 font-medium mt-2 flex items-center gap-1">
                  <Crown className="w-3 h-3" /> Managers automatically have all permissions
                </p>
              )}
            </div>
          </div>
          <DialogFooter className="flex-shrink-0 pt-3 border-t border-slate-100">
            <Button variant="outline" size="sm" className="text-xs" onClick={() => setShowDialog(false)} data-testid="user-cancel-btn">Cancel</Button>
            <Button className="bg-teal-600 hover:bg-teal-700 text-white text-xs" size="sm" onClick={handleSave} disabled={saving} data-testid="user-save-btn">
              {saving && <Loader2 className="w-3 h-3 animate-spin mr-1.5" />}
              {editingUser ? 'Save Changes' : 'Create User'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent className="max-w-sm" data-testid="delete-user-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading text-base font-bold text-navy-900 flex items-center gap-2"><Trash2 className="w-5 h-5 text-red-500" /> Delete User</DialogTitle>
            <DialogDescription className="text-xs text-slate-500 pt-1">Permanently remove <span className="font-semibold text-navy-900">{deleteTarget?.name}</span> ({deleteTarget?.email})? This cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" size="sm" className="text-xs" onClick={() => setDeleteTarget(null)} data-testid="delete-user-cancel">Cancel</Button>
            <Button variant="destructive" size="sm" className="text-xs" onClick={handleDelete} disabled={deleting} data-testid="delete-user-confirm">
              {deleting && <Loader2 className="w-3 h-3 animate-spin mr-1.5" />} Delete User
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
