from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class UserRegister(BaseModel):
    email: str
    password: str
    name: str
    restaurant_name: str


class UserLogin(BaseModel):
    email: str
    password: str


class PurchaseCreate(BaseModel):
    supplier_name: str
    supplier_id: Optional[str] = None
    invoice_number: str
    invoice_date: str
    items: List[Dict[str, Any]]
    subtotal: float
    tax: float
    total: float


class PurchaseUpdate(BaseModel):
    supplier_name: Optional[str] = None
    supplier_id: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    items: Optional[List[Dict[str, Any]]] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None


class SalesCreate(BaseModel):
    report_date: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    total_sales: float
    items: Optional[List[Dict[str, Any]]] = []


class SalesUpdate(BaseModel):
    report_date: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    total_sales: Optional[float] = None
    items: Optional[List[Dict[str, Any]]] = None


class SupplierCreate(BaseModel):
    name: str
    contact_person: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    address: Optional[str] = ""


class CanonicalItemVariant(BaseModel):
    key: str
    label: Optional[str] = ""


class CanonicalItemCreate(BaseModel):
    name: str
    category: Optional[str] = ""
    storage_category: Optional[str] = ""  # dry, chilled, frozen
    category_source: Optional[str] = "auto"  # auto, manual
    unit: Optional[str] = ""
    variants: Optional[List[CanonicalItemVariant]] = None


class ItemAliasCreate(BaseModel):
    canonical_item_id: str
    alias_name: str


class ChatMessageIn(BaseModel):
    message: str


class SalaryCreate(BaseModel):
    employee_name: str
    position: Optional[str] = ""
    amount: float
    payment_date: str
    notes: Optional[str] = ""


class SalaryUpdate(BaseModel):
    employee_name: Optional[str] = None
    position: Optional[str] = None
    amount: Optional[float] = None
    payment_date: Optional[str] = None
    notes: Optional[str] = None


class OtherExpenseCreate(BaseModel):
    title: str
    category: str
    amount: float
    expense_date: str
    notes: Optional[str] = ""


class OtherExpenseUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[float] = None
    expense_date: Optional[str] = None
    notes: Optional[str] = None


class SettingsUpdate(BaseModel):
    name: Optional[str] = None
    restaurant_name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    currency: Optional[str] = None
    default_tax_rate: Optional[float] = None
    default_expense_category: Optional[str] = None
    alerts_enabled: Optional[bool] = None
    alert_price_increase: Optional[bool] = None
    alert_cheaper_vendor: Optional[bool] = None
    alert_not_ordered: Optional[bool] = None
    language: Optional[str] = None
    date_format: Optional[str] = None


class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str = "staff"
    permissions: Optional[Dict[str, bool]] = None
    data_scope: Optional[str] = None
    approval_rule: str = "pending_all"
    auto_approve_limit: Optional[float] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    permissions: Optional[Dict[str, bool]] = None
    data_scope: Optional[str] = None
    approval_rule: Optional[str] = None
    auto_approve_limit: Optional[float] = None


class ApprovalAction(BaseModel):
    action: str
    reason: Optional[str] = None


class ReceiptLearnRequest(BaseModel):
    receipt_id: Optional[str] = None
    vendor_name: str
    vendor_id: Optional[str] = None
    corrected_items: List[Dict[str, Any]] = []
    corrected_date: Optional[str] = None
    corrected_total: Optional[float] = None
    hints: Optional[Dict[str, Any]] = None


class DuplicateCheckRequest(BaseModel):
    record_type: str
    data: Dict[str, Any]
