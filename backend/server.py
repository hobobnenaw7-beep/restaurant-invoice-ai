from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from core.database import client, UPLOADS_DIR

# --- Import all route modules ---
from routes.auth import router as auth_router
from routes.audit import router as audit_router
from routes.approvals import router as approvals_router
from routes.dashboard import router as dashboard_router
from routes.upload import router as upload_router
from routes.receipts import router as receipts_router
from routes.records import router as records_router
from routes.duplicates import router as duplicates_router
from routes.purchases import router as purchases_router
from routes.salaries import router as salaries_router
from routes.other_expenses import router as other_expenses_router
from routes.sales import router as sales_router
from routes.suppliers import router as suppliers_router
from routes.items import router as items_router
from routes.reports import router as reports_router
from routes.prices import router as prices_router
from routes.vendor_comparison import router as vendor_comparison_router
from routes.alerts import router as alerts_router
from routes.chat import router as chat_router
from routes.settings import router as settings_router
from routes.password_reset import router as password_reset_router
from routes.correction_memory import router as correction_memory_router
from routes.metrics import router as metrics_router
from routes.usability_metrics import router as usability_metrics_router
from routes.profit_dashboard import router as profit_dashboard_router
from routes.product_identity import router as product_identity_router
from routes.price_intelligence import router as price_intelligence_router
from routes.procurement import router as procurement_router
from routes.procurement_suggestions import router as procurement_suggestions_router
from routes.procurement_audit import router as procurement_audit_router
from routes.orders import router as orders_router

# --- App setup ---
app = FastAPI()

# --- Static files ---
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# Also serve under /api/uploads for ingress compatibility (external access)
app.mount("/api/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="api_uploads")

# --- API router with /api prefix ---
api_router = APIRouter(prefix="/api")

# Mount all domain routers
api_router.include_router(auth_router)
api_router.include_router(audit_router)
api_router.include_router(approvals_router)
api_router.include_router(dashboard_router)
api_router.include_router(upload_router)
api_router.include_router(receipts_router)
api_router.include_router(records_router)
api_router.include_router(duplicates_router)
api_router.include_router(purchases_router)
api_router.include_router(salaries_router)
api_router.include_router(other_expenses_router)
api_router.include_router(sales_router)
api_router.include_router(suppliers_router)
api_router.include_router(items_router)
api_router.include_router(reports_router)
api_router.include_router(prices_router)
api_router.include_router(vendor_comparison_router)
api_router.include_router(alerts_router)
api_router.include_router(chat_router)
api_router.include_router(settings_router)
api_router.include_router(password_reset_router)
api_router.include_router(correction_memory_router)
api_router.include_router(metrics_router)
api_router.include_router(usability_metrics_router)
api_router.include_router(profit_dashboard_router)
api_router.include_router(product_identity_router)
api_router.include_router(price_intelligence_router)
api_router.include_router(procurement_router)
api_router.include_router(procurement_suggestions_router)
api_router.include_router(procurement_audit_router)
api_router.include_router(orders_router)

app.include_router(api_router)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Lifecycle ---
@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
