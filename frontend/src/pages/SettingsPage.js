import { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import {
  Loader2, Save, User, Building2, DollarSign, Bell,
  Globe, Trash2, AlertTriangle, Camera, Upload, X
} from 'lucide-react';

const CURRENCIES = [
  { value: 'USD', label: 'USD ($)' },
  { value: 'EUR', label: 'EUR (\u20ac)' },
  { value: 'GBP', label: 'GBP (\u00a3)' },
  { value: 'CAD', label: 'CAD (C$)' },
  { value: 'AUD', label: 'AUD (A$)' },
  { value: 'AED', label: 'AED (\u062f.\u0625)' },
  { value: 'SAR', label: 'SAR (\ufdfc)' },
  { value: 'INR', label: 'INR (\u20b9)' },
  { value: 'TRY', label: 'TRY (\u20ba)' },
];

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'ar', label: 'Arabic' },
  { value: 'tr', label: 'Turkish' },
  { value: 'de', label: 'German' },
];

const DATE_FORMATS = [
  { value: 'YYYY-MM-DD', label: '2026-03-19' },
  { value: 'MM/DD/YYYY', label: '03/19/2026' },
  { value: 'DD/MM/YYYY', label: '19/03/2026' },
];

const EXPENSE_CATS = ['Rent', 'Electricity', 'Water', 'Gas', 'Maintenance', 'Equipment', 'Insurance', 'Marketing', 'Other'];

function SectionCard({ icon: Icon, iconBg, title, description, children }) {
  return (
    <Card className="border border-slate-100 shadow-sm">
      <CardHeader className="pb-4">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl ${iconBg} flex items-center justify-center`}>
            <Icon className="w-5 h-5 text-white" />
          </div>
          <div>
            <CardTitle className="font-heading text-base font-bold">{title}</CardTitle>
            <CardDescription className="text-xs">{description}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
    </Card>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">{label}</Label>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

function ToggleRow({ label, description, checked, onCheckedChange, testId }) {
  return (
    <div className="flex items-center justify-between py-2">
      <div>
        <p className="text-sm font-medium text-navy-900">{label}</p>
        {description && <p className="text-xs text-slate-400 mt-0.5">{description}</p>}
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} data-testid={testId} />
    </div>
  );
}

export default function SettingsPage() {
  const { api, user: authUser } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showReset, setShowReset] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetConfirm, setResetConfirm] = useState('');
  const [logo, setLogo] = useState(null);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const logoRef = useRef(null);

  const [form, setForm] = useState({
    name: '', restaurant_name: '', address: '', phone: '', email: '',
    currency: 'USD', default_tax_rate: 0, default_expense_category: 'Rent',
    alerts_enabled: true, alert_price_increase: true, alert_cheaper_vendor: true, alert_not_ordered: true,
    language: 'en', date_format: 'YYYY-MM-DD',
  });

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get('/settings');
        const r = res.data.restaurant || {};
        const u = res.data.user || {};
        setForm({
          name: u.name || '',
          restaurant_name: r.name || '',
          address: r.address || '',
          phone: r.phone || '',
          email: r.email || '',
          currency: r.currency || 'USD',
          default_tax_rate: r.default_tax_rate ?? 0,
          default_expense_category: r.default_expense_category || 'Rent',
          alerts_enabled: r.alerts_enabled !== false,
          alert_price_increase: r.alert_price_increase !== false,
          alert_cheaper_vendor: r.alert_cheaper_vendor !== false,
          alert_not_ordered: r.alert_not_ordered !== false,
          language: r.language || 'en',
          date_format: r.date_format || 'YYYY-MM-DD',
        });
        setLogo(r.logo || null);
      } catch { toast.error('Failed to load settings'); }
      finally { setLoading(false); }
    };
    load();
  }, []); // eslint-disable-line

  const update = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      await api.put('/settings', form);
      toast.success('Settings saved');
    } catch { toast.error('Save failed'); }
    finally { setSaving(false); }
  };

  const handleLogoUpload = async (file) => {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { toast.error('Logo must be under 2 MB'); return; }
    setUploadingLogo(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await api.post('/settings/upload-logo', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setLogo(res.data.logo);
      toast.success('Logo uploaded');
    } catch { toast.error('Upload failed'); }
    finally { setUploadingLogo(false); }
  };

  const removeLogo = async () => {
    try {
      await api.put('/settings', { ...form });
      setLogo(null);
      toast.success('Logo removed');
    } catch { toast.error('Failed to remove logo'); }
  };

  const handleReset = async () => {
    if (resetConfirm !== 'DELETE') return;
    setResetting(true);
    try {
      await api.post('/settings/reset-data');
      toast.success('All data has been reset');
      setShowReset(false);
      setResetConfirm('');
    } catch { toast.error('Reset failed'); }
    finally { setResetting(false); }
  };

  if (loading) {
    return (
      <div className="max-w-2xl space-y-6" data-testid="settings-loading">
        <Skeleton className="h-8 w-40" />
        {[1,2,3,4,5].map(i => <Skeleton key={i} className="h-48 rounded-xl" />)}
      </div>
    );
  }

  return (
    <div className="max-w-2xl space-y-6 pb-10" data-testid="settings-page">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl font-extrabold text-navy-900 tracking-tight">Settings</h1>
        <p className="text-xs text-slate-400 mt-0.5">Manage your restaurant profile and preferences</p>
      </div>

      {/* ==================== RESTAURANT PROFILE ==================== */}
      <SectionCard icon={Building2} iconBg="bg-teal-600" title="Restaurant Profile" description="Your restaurant information">
        {/* Logo */}
        <div>
          <Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Restaurant Logo</Label>
          <div className="mt-2 flex items-center gap-4">
            <div
              className="w-20 h-20 rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 flex items-center justify-center overflow-hidden cursor-pointer hover:border-teal-300 transition-colors"
              onClick={() => logoRef.current?.click()}
              data-testid="settings-logo-area"
            >
              {uploadingLogo ? (
                <Loader2 className="w-6 h-6 text-slate-300 animate-spin" />
              ) : logo ? (
                <img src={logo} alt="Logo" className="w-full h-full object-cover" />
              ) : (
                <Camera className="w-6 h-6 text-slate-300" />
              )}
            </div>
            <div className="space-y-1.5">
              <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => logoRef.current?.click()} disabled={uploadingLogo}>
                <Upload className="w-3 h-3 mr-1.5" /> Upload Logo
              </Button>
              {logo && (
                <Button size="sm" variant="ghost" className="h-8 text-xs text-red-500 hover:text-red-700" onClick={removeLogo}>
                  <X className="w-3 h-3 mr-1" /> Remove
                </Button>
              )}
              <p className="text-[10px] text-slate-400">PNG, JPG up to 2 MB</p>
            </div>
            <input ref={logoRef} type="file" className="hidden" accept="image/png,image/jpeg,image/jpg,image/webp" onChange={(e) => handleLogoUpload(e.target.files?.[0])} />
          </div>
        </div>

        <Field label="Restaurant Name">
          <Input className="h-10" value={form.restaurant_name} onChange={(e) => update('restaurant_name', e.target.value)} placeholder="My Restaurant" data-testid="settings-restaurant-name" />
        </Field>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Phone Number">
            <Input className="h-10" value={form.phone} onChange={(e) => update('phone', e.target.value)} placeholder="+1 (555) 000-0000" data-testid="settings-phone" />
          </Field>
          <Field label="Email">
            <Input className="h-10" type="email" value={form.email} onChange={(e) => update('email', e.target.value)} placeholder="contact@restaurant.com" data-testid="settings-email" />
          </Field>
        </div>

        <Field label="Address">
          <Input className="h-10" value={form.address} onChange={(e) => update('address', e.target.value)} placeholder="123 Main St, City, State" data-testid="settings-address" />
        </Field>
      </SectionCard>

      {/* ==================== PROFILE ==================== */}
      <SectionCard icon={User} iconBg="bg-navy-900" title="Your Profile" description="Personal account information">
        <Field label="Full Name">
          <Input className="h-10" value={form.name} onChange={(e) => update('name', e.target.value)} data-testid="settings-name" />
        </Field>
        <Field label="Email Address">
          <Input className="h-10 bg-slate-50 text-slate-500" value={authUser?.email || ''} disabled />
        </Field>
      </SectionCard>

      {/* ==================== FINANCIAL ==================== */}
      <SectionCard icon={DollarSign} iconBg="bg-indigo-600" title="Financial Settings" description="Currency, tax, and default values">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Currency">
            <Select value={form.currency} onValueChange={(v) => update('currency', v)}>
              <SelectTrigger className="h-10" data-testid="settings-currency"><SelectValue /></SelectTrigger>
              <SelectContent>
                {CURRENCIES.map(c => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Default Tax Rate (%)">
            <Input className="h-10" type="number" step="0.01" min="0" max="100" value={form.default_tax_rate || ''} onChange={(e) => update('default_tax_rate', parseFloat(e.target.value) || 0)} placeholder="0" data-testid="settings-tax-rate" />
          </Field>
        </div>
        <Field label="Default Expense Category">
          <Select value={form.default_expense_category} onValueChange={(v) => update('default_expense_category', v)}>
            <SelectTrigger className="h-10" data-testid="settings-expense-category"><SelectValue /></SelectTrigger>
            <SelectContent>
              {EXPENSE_CATS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </Field>
      </SectionCard>

      {/* ==================== NOTIFICATIONS ==================== */}
      <SectionCard icon={Bell} iconBg="bg-amber-500" title="Notification Settings" description="Control which alerts you receive">
        <ToggleRow
          label="Smart Alerts"
          description="Master toggle for all alert types"
          checked={form.alerts_enabled}
          onCheckedChange={(v) => update('alerts_enabled', v)}
          testId="settings-alerts-enabled"
        />
        <div className={`space-y-0 divide-y divide-slate-100 ${!form.alerts_enabled ? 'opacity-40 pointer-events-none' : ''}`}>
          <ToggleRow
            label="Price Increase Alerts"
            description="Notify when item prices increase from a vendor"
            checked={form.alert_price_increase}
            onCheckedChange={(v) => update('alert_price_increase', v)}
            testId="settings-alert-price"
          />
          <ToggleRow
            label="Cheaper Vendor Alerts"
            description="Notify when a cheaper vendor is available for an item"
            checked={form.alert_cheaper_vendor}
            onCheckedChange={(v) => update('alert_cheaper_vendor', v)}
            testId="settings-alert-cheaper"
          />
          <ToggleRow
            label="Not Ordered Recently Alerts"
            description="Notify when items haven't been ordered in a while"
            checked={form.alert_not_ordered}
            onCheckedChange={(v) => update('alert_not_ordered', v)}
            testId="settings-alert-not-ordered"
          />
        </div>
      </SectionCard>

      {/* ==================== LANGUAGE / DISPLAY ==================== */}
      <SectionCard icon={Globe} iconBg="bg-violet-600" title="Language & Display" description="Localization preferences">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Language">
            <Select value={form.language} onValueChange={(v) => update('language', v)}>
              <SelectTrigger className="h-10" data-testid="settings-language"><SelectValue /></SelectTrigger>
              <SelectContent>
                {LANGUAGES.map(l => <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Date Format">
            <Select value={form.date_format} onValueChange={(v) => update('date_format', v)}>
              <SelectTrigger className="h-10" data-testid="settings-date-format"><SelectValue /></SelectTrigger>
              <SelectContent>
                {DATE_FORMATS.map(f => <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
        </div>
      </SectionCard>

      {/* ==================== SAVE BUTTON ==================== */}
      <Button onClick={save} disabled={saving} className="bg-navy-900 hover:bg-navy-800 text-white h-11 px-8 text-sm" data-testid="save-settings-btn">
        {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Save className="w-4 h-4 mr-2" />}
        Save Settings
      </Button>

      {/* ==================== DANGER ZONE ==================== */}
      <Card className="border border-red-200 shadow-sm">
        <CardHeader className="pb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-red-600 flex items-center justify-center">
              <Trash2 className="w-5 h-5 text-white" />
            </div>
            <div>
              <CardTitle className="font-heading text-base font-bold text-red-700">Data Management</CardTitle>
              <CardDescription className="text-xs text-red-400">Irreversible actions — proceed with caution</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="bg-red-50 border border-red-100 rounded-lg p-4">
            <h3 className="text-sm font-bold text-red-800 mb-1">Reset All Data</h3>
            <p className="text-xs text-red-600 mb-3">
              This will permanently delete all vendors, items, expenses, sales records, and uploaded files.
              Your account and restaurant profile will be kept.
            </p>
            <Button variant="outline" className="border-red-300 text-red-700 hover:bg-red-100 h-9 text-xs" onClick={() => setShowReset(true)} data-testid="reset-data-btn">
              <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Reset All Data
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ==================== RESET CONFIRMATION DIALOG ==================== */}
      <Dialog open={showReset} onOpenChange={(v) => { if (!resetting) setShowReset(v); }}>
        <DialogContent className="max-w-md" data-testid="reset-confirm-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading text-lg flex items-center gap-2 text-red-700">
              <div className="w-9 h-9 rounded-lg bg-red-100 flex items-center justify-center flex-shrink-0">
                <AlertTriangle className="w-5 h-5 text-red-600" />
              </div>
              Confirm Data Reset
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-slate-600">
              This action is <span className="font-bold text-red-700">permanent and cannot be undone</span>.
              All of the following will be deleted:
            </p>
            <ul className="text-xs text-slate-600 space-y-1 pl-4 list-disc">
              <li>All vendor records</li>
              <li>All item records and aliases</li>
              <li>All expense records (raw materials, salaries, other)</li>
              <li>All sales records</li>
              <li>All uploaded files and records library</li>
              <li>All alerts</li>
            </ul>
            <div>
              <Label className="text-xs font-bold text-red-600">Type DELETE to confirm</Label>
              <Input
                className="mt-1.5 h-10 border-red-200 focus:border-red-400"
                value={resetConfirm}
                onChange={(e) => setResetConfirm(e.target.value)}
                placeholder="Type DELETE"
                data-testid="reset-confirm-input"
              />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-2">
            <Button variant="outline" className="h-9 text-xs" onClick={() => { setShowReset(false); setResetConfirm(''); }} disabled={resetting}>
              Cancel
            </Button>
            <Button
              onClick={handleReset}
              disabled={resetConfirm !== 'DELETE' || resetting}
              className="bg-red-600 hover:bg-red-700 text-white h-9 text-xs"
              data-testid="reset-confirm-btn"
            >
              {resetting ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Trash2 className="w-3.5 h-3.5 mr-1.5" />}
              Reset All Data
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
