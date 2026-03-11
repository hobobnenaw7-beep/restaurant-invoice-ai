import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import { Loader2, Save, User, Building2 } from 'lucide-react';

export default function SettingsPage() {
  const { api, user: authUser } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: '', restaurant_name: '', address: '', phone: '' });

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get('/settings');
        setForm({ name: res.data.user?.name || '', restaurant_name: res.data.restaurant?.name || '', address: res.data.restaurant?.address || '', phone: res.data.restaurant?.phone || '' });
      } catch { toast.error('Failed to load'); }
      finally { setLoading(false); }
    };
    load();
  }, []); // eslint-disable-line

  const save = async () => {
    setSaving(true);
    try { await api.put('/settings', form); toast.success('Settings saved!'); }
    catch { toast.error('Save failed'); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="max-w-2xl space-y-6"><Skeleton className="h-48 rounded-xl" /><Skeleton className="h-64 rounded-xl" /></div>;

  return (
    <div className="max-w-2xl space-y-8" data-testid="settings-page">
      <div>
        <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-navy-900 tracking-tight">Settings</h1>
        <p className="text-sm text-slate-400 mt-1">Manage your profile and restaurant</p>
      </div>

      <Card className="border border-slate-100 shadow-sm">
        <CardHeader className="pb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-navy-900 flex items-center justify-center"><User className="w-5 h-5 text-white" /></div>
            <div>
              <CardTitle className="font-heading text-base font-bold">Profile</CardTitle>
              <CardDescription className="text-xs">Your personal information</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Full Name</Label>
            <Input className="mt-1.5 h-10" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="settings-name" />
          </div>
          <div>
            <Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Email</Label>
            <Input className="mt-1.5 h-10 bg-slate-50 text-slate-500" value={authUser?.email || ''} disabled />
          </div>
        </CardContent>
      </Card>

      <Card className="border border-slate-100 shadow-sm">
        <CardHeader className="pb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-teal-600 flex items-center justify-center"><Building2 className="w-5 h-5 text-white" /></div>
            <div>
              <CardTitle className="font-heading text-base font-bold">Restaurant</CardTitle>
              <CardDescription className="text-xs">Your restaurant details</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Restaurant Name</Label>
            <Input className="mt-1.5 h-10" value={form.restaurant_name} onChange={(e) => setForm({ ...form, restaurant_name: e.target.value })} data-testid="settings-restaurant" />
          </div>
          <div>
            <Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Address</Label>
            <Input className="mt-1.5 h-10" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} placeholder="Enter address" />
          </div>
          <div>
            <Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Phone</Label>
            <Input className="mt-1.5 h-10" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="Enter phone number" />
          </div>
        </CardContent>
      </Card>

      <Button onClick={save} disabled={saving} className="bg-navy-900 hover:bg-navy-800 text-white h-11 px-6" data-testid="save-settings-btn">
        {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Save className="w-4 h-4 mr-2" />}
        Save Changes
      </Button>
    </div>
  );
}
