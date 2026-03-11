import { useState, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import { Upload, FileImage, FileText, Camera, Loader2, Check, Plus, Trash2, ArrowLeft, ArrowRight, Sparkles } from 'lucide-react';

export default function UploadPage() {
  const { api } = useAuth();
  const [step, setStep] = useState(1);
  const [docType, setDocType] = useState('purchase_invoice');
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [extracting, setExtracting] = useState(false);
  const [extracted, setExtracted] = useState(null);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef(null);
  const cameraRef = useRef(null);

  const handleFile = (f) => {
    if (!f) return;
    setFile(f);
    if (f.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = (e) => setPreview(e.target.result);
      reader.readAsDataURL(f);
    } else { setPreview(null); }
    setStep(2);
  };

  const extract = async () => {
    if (!file) return;
    setExtracting(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('document_type', docType);
      const res = await api.post('/upload/extract', formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 });
      setExtracted(res.data.extracted_data);
      setStep(3);
      toast.success('Data extracted!');
    } catch (err) {
      toast.error('Extraction failed. ' + (err.response?.data?.detail || 'Try again.'));
    } finally { setExtracting(false); }
  };

  const save = async () => {
    setSaving(true);
    try {
      if (docType === 'purchase_invoice') {
        await api.post('/purchases', {
          supplier_name: extracted.supplier_name || '', invoice_number: extracted.invoice_number || '',
          invoice_date: extracted.invoice_date || new Date().toISOString().split('T')[0],
          items: extracted.items || [], subtotal: parseFloat(extracted.subtotal) || 0,
          tax: parseFloat(extracted.tax) || 0, total: parseFloat(extracted.total) || 0,
        });
      } else {
        await api.post('/sales', {
          report_date: extracted.report_date || new Date().toISOString().split('T')[0],
          total_sales: parseFloat(extracted.total_sales) || 0, items: extracted.items || [],
        });
      }
      toast.success('Saved successfully!');
      reset();
    } catch (err) {
      toast.error('Save failed: ' + (err.response?.data?.detail || ''));
    } finally { setSaving(false); }
  };

  const updateField = (key, val) => setExtracted({ ...extracted, [key]: val });
  const updateItem = (idx, key, val) => {
    const items = [...(extracted.items || [])];
    items[idx] = { ...items[idx], [key]: val };
    setExtracted({ ...extracted, items });
  };
  const removeItem = (idx) => { const items = [...(extracted.items || [])]; items.splice(idx, 1); setExtracted({ ...extracted, items }); };
  const addItem = () => {
    const items = [...(extracted.items || [])];
    if (docType === 'purchase_invoice') items.push({ raw_name: '', quantity: 0, unit: '', unit_price: 0, total: 0 });
    else items.push({ menu_item: '', quantity: 0, revenue: 0 });
    setExtracted({ ...extracted, items });
  };
  const reset = () => { setStep(1); setFile(null); setPreview(null); setExtracted(null); };

  return (
    <div className="max-w-3xl mx-auto space-y-8" data-testid="upload-page">
      <div>
        <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-navy-900 tracking-tight">Upload Center</h1>
        <p className="text-sm text-slate-400 mt-1">Scan invoices and sales reports with AI</p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {['Upload', 'Extract', 'Review & Save'].map((s, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold transition-all ${step > i + 1 ? 'bg-teal-600 text-white' : step === i + 1 ? 'bg-navy-900 text-white' : 'bg-slate-200 text-slate-400'}`}>
              {step > i + 1 ? <Check className="w-3.5 h-3.5" /> : i + 1}
            </div>
            <span className={`text-xs font-semibold hidden sm:inline ${step >= i + 1 ? 'text-navy-900' : 'text-slate-300'}`}>{s}</span>
            {i < 2 && <div className={`w-10 h-px ${step > i + 1 ? 'bg-teal-500' : 'bg-slate-200'}`} />}
          </div>
        ))}
      </div>

      {/* Step 1: Upload */}
      {step === 1 && (
        <Card className="border border-slate-100 shadow-sm">
          <CardContent className="p-8">
            <div className="mb-6">
              <Label className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 block">Document Type</Label>
              <Select value={docType} onValueChange={setDocType}>
                <SelectTrigger data-testid="doc-type-select" className="w-full max-w-xs h-11"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="purchase_invoice">Purchase Invoice</SelectItem>
                  <SelectItem value="sales_report">Sales Report</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Separator className="mb-6" />

            <div
              className="upload-zone rounded-2xl p-16 text-center cursor-pointer group"
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('drag-over'); }}
              onDragLeave={(e) => e.currentTarget.classList.remove('drag-over')}
              onDrop={(e) => { e.preventDefault(); e.currentTarget.classList.remove('drag-over'); handleFile(e.dataTransfer.files[0]); }}
              data-testid="upload-dropzone"
            >
              <div className="w-16 h-16 rounded-2xl bg-slate-100 group-hover:bg-teal-50 flex items-center justify-center mx-auto mb-4 transition-colors">
                <Upload className="w-7 h-7 text-slate-400 group-hover:text-teal-600 transition-colors" />
              </div>
              <p className="text-base font-semibold text-navy-900 mb-1">Drop your file here</p>
              <p className="text-sm text-slate-400">or click to browse. Supports JPG, PNG, and PDF.</p>
            </div>
            <input ref={fileRef} type="file" className="hidden" accept="image/*,.pdf" onChange={(e) => handleFile(e.target.files[0])} />

            <div className="flex gap-3 mt-6">
              <Button variant="outline" className="flex-1 h-11" onClick={() => fileRef.current?.click()} data-testid="upload-image-btn">
                <FileImage className="w-4 h-4 mr-2" /> Image
              </Button>
              <Button variant="outline" className="flex-1 h-11" onClick={() => { fileRef.current.accept = '.pdf'; fileRef.current.click(); }} data-testid="upload-pdf-btn">
                <FileText className="w-4 h-4 mr-2" /> PDF
              </Button>
              <Button variant="outline" className="flex-1 h-11" onClick={() => cameraRef.current?.click()} data-testid="upload-camera-btn">
                <Camera className="w-4 h-4 mr-2" /> Camera
              </Button>
              <input ref={cameraRef} type="file" className="hidden" accept="image/*" capture="environment" onChange={(e) => handleFile(e.target.files[0])} />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 2: Extract */}
      {step === 2 && (
        <Card className="border border-slate-100 shadow-sm">
          <CardContent className="p-8">
            <div className="flex items-center gap-5 p-5 bg-slate-50 rounded-xl mb-6">
              {preview ? <img src={preview} alt="Preview" className="w-20 h-20 object-cover rounded-lg border border-slate-200" /> : <div className="w-20 h-20 bg-slate-200 rounded-lg flex items-center justify-center"><FileText className="w-8 h-8 text-slate-400" /></div>}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-navy-900 truncate">{file?.name}</p>
                <p className="text-xs text-slate-400 mt-0.5">{(file?.size / 1024).toFixed(1)} KB &middot; {docType === 'purchase_invoice' ? 'Purchase Invoice' : 'Sales Report'}</p>
              </div>
            </div>
            <div className="flex gap-3">
              <Button variant="outline" onClick={reset} className="h-11"><ArrowLeft className="w-4 h-4 mr-1" /> Back</Button>
              <Button onClick={extract} disabled={extracting} className="bg-teal-600 hover:bg-teal-700 text-white h-11 flex-1" data-testid="extract-btn">
                {extracting ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Extracting with AI...</> : <><Sparkles className="w-4 h-4 mr-2" /> Extract Data</>}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 3: Review & Save */}
      {step === 3 && extracted && (
        <Card className="border border-slate-100 shadow-sm">
          <CardHeader className="px-8 pt-6 pb-4">
            <CardTitle className="font-heading text-lg font-bold">Review Extracted Data</CardTitle>
            <CardDescription>Verify and edit before saving</CardDescription>
          </CardHeader>
          <CardContent className="px-8 pb-8 space-y-5">
            {docType === 'purchase_invoice' ? (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Supplier</Label><Input className="mt-1.5 h-10" value={extracted.supplier_name || ''} onChange={(e) => updateField('supplier_name', e.target.value)} data-testid="edit-supplier" /></div>
                  <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Invoice #</Label><Input className="mt-1.5 h-10" value={extracted.invoice_number || ''} onChange={(e) => updateField('invoice_number', e.target.value)} data-testid="edit-invoice-number" /></div>
                  <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Date</Label><Input className="mt-1.5 h-10" type="date" value={extracted.invoice_date || ''} onChange={(e) => updateField('invoice_date', e.target.value)} data-testid="edit-invoice-date" /></div>
                </div>
                <Separator />
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Line Items</Label>
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={addItem}><Plus className="w-3 h-3 mr-1" /> Add</Button>
                  </div>
                  <div className="space-y-2">
                    {(extracted.items || []).map((item, i) => (
                      <div key={i} className="grid grid-cols-12 gap-2 items-center p-2.5 bg-slate-50 rounded-lg">
                        <Input className="col-span-4 text-xs h-8" placeholder="Item name" value={item.raw_name || ''} onChange={(e) => updateItem(i, 'raw_name', e.target.value)} />
                        <Input className="col-span-2 text-xs h-8" type="number" placeholder="Qty" value={item.quantity || ''} onChange={(e) => updateItem(i, 'quantity', parseFloat(e.target.value) || 0)} />
                        <Input className="col-span-2 text-xs h-8" placeholder="Unit" value={item.unit || ''} onChange={(e) => updateItem(i, 'unit', e.target.value)} />
                        <Input className="col-span-2 text-xs h-8" type="number" step="0.01" placeholder="Price" value={item.unit_price || ''} onChange={(e) => updateItem(i, 'unit_price', parseFloat(e.target.value) || 0)} />
                        <div className="col-span-2 flex gap-1 items-center">
                          <span className="text-xs font-semibold text-navy-900 tabular-nums">${(item.quantity * item.unit_price || item.total || 0).toFixed(2)}</span>
                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 ml-auto" onClick={() => removeItem(i)}><Trash2 className="w-3 h-3 text-red-400" /></Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <Separator />
                <div className="grid grid-cols-3 gap-4">
                  <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Subtotal</Label><Input className="mt-1.5 h-10" type="number" step="0.01" value={extracted.subtotal || ''} onChange={(e) => updateField('subtotal', parseFloat(e.target.value) || 0)} /></div>
                  <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Tax</Label><Input className="mt-1.5 h-10" type="number" step="0.01" value={extracted.tax || ''} onChange={(e) => updateField('tax', parseFloat(e.target.value) || 0)} /></div>
                  <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Total</Label><Input className="mt-1.5 h-10 font-bold" type="number" step="0.01" value={extracted.total || ''} onChange={(e) => updateField('total', parseFloat(e.target.value) || 0)} /></div>
                </div>
              </>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Report Date</Label><Input className="mt-1.5 h-10" type="date" value={extracted.report_date || ''} onChange={(e) => updateField('report_date', e.target.value)} /></div>
                  <div><Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Total Sales</Label><Input className="mt-1.5 h-10 font-bold" type="number" step="0.01" value={extracted.total_sales || ''} onChange={(e) => updateField('total_sales', parseFloat(e.target.value) || 0)} /></div>
                </div>
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <Label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Sales Items</Label>
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={addItem}><Plus className="w-3 h-3 mr-1" /> Add</Button>
                  </div>
                  {(extracted.items || []).map((item, i) => (
                    <div key={i} className="grid grid-cols-4 gap-2 items-center bg-slate-50 p-2.5 rounded-lg mb-2">
                      <Input className="col-span-2 text-xs h-8" placeholder="Menu item" value={item.menu_item || ''} onChange={(e) => updateItem(i, 'menu_item', e.target.value)} />
                      <Input className="text-xs h-8" type="number" placeholder="Qty" value={item.quantity || ''} onChange={(e) => updateItem(i, 'quantity', parseFloat(e.target.value) || 0)} />
                      <div className="flex gap-1"><Input className="text-xs h-8" type="number" step="0.01" placeholder="Revenue" value={item.revenue || ''} onChange={(e) => updateItem(i, 'revenue', parseFloat(e.target.value) || 0)} /><Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => removeItem(i)}><Trash2 className="w-3 h-3 text-red-400" /></Button></div>
                    </div>
                  ))}
                </div>
              </>
            )}
            <div className="flex gap-3 pt-2">
              <Button variant="outline" onClick={reset} className="h-11">Cancel</Button>
              <Button onClick={save} disabled={saving} className="bg-navy-900 hover:bg-navy-800 text-white h-11 flex-1" data-testid="save-extracted-btn">
                {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Check className="w-4 h-4 mr-2" />} Save to Records
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
