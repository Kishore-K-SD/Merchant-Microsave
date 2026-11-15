# Merchant MicroSave — Hackathon Demo

A local, demo-only prototype of a merchant liquidity intelligence workflow.

**Demonstrates:** deterministic Safe-to-Reserve calculation, conservative cash-flow projection, dated liability protection, freshness/history gates, merchant approve/adjust/skip controls, a persistent SQLite audit ledger, stress-test scenarios, Gemma 4 31B invoice-document extraction through Sarvam AI, merchant-confirmed purchase history, manual item-level sales capture, and LLM-generated explanations of deterministic trends.

> **Important:** All bundled balances, collections, liabilities and reserve entries are synthetic. This project is not connected to Paytm, a bank, an Account Aggregator, UPI settlement rails, gold, or any real money movement. The recommendation is a hackathon demonstration heuristic, not financial advice or a production-grade underwriting model.

## Requirements
- Python 3.10+
- Node.js 18+ and npm

## Configure Sarvam AI (Gemma 4 31B)
The backend uses Sarvam Token Factory's Chat Completion V2 API. Sarvam lists Gemma 4 31B under the model ID `gemma4`.

1. Create an API subscription key in the Sarvam dashboard.
2. Copy `backend/.env.example` to `backend/.env`.
3. Set `SARVAM_API_KEY` in `backend/.env`.
4. Keep the key in the backend only. Never add it to `frontend/.env` or commit it.

```env
SARVAM_API_KEY=your_key_here
SARVAM_BASE_URL=https://api.sarvam.ai
SARVAM_MODEL=gemma4
```

The application still starts without a key. In that case, the invoice-extraction button returns a clear configuration message and trend insights fall back to deterministic text. No mock LLM response is presented as a live model result.

## Run on Windows
Open two terminals.

### Terminal 1 — Backend
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Terminal 2 — Frontend
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:5173.

## Run on macOS / Linux
### Terminal 1 — Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Terminal 2 — Frontend
```bash
cd frontend
npm install
npm run dev
```

Backend docs: http://127.0.0.1:8000/docs | Health: http://127.0.0.1:8000/health

## Verify backend
From `backend` with the virtual environment active:
```bash
python -m pytest -q
```
The included backend suite passes 19 tests, including mocked Sarvam provider calls and PDF rendering tests.

## Recommended judge walkthrough
1. Start with **Normal trading** and explain the projected minimum balance, protected operating buffer, liabilities and recommendation.
2. Select **Slow sales week** to show lower collections reducing the recommendation.
3. Select **Expense spike** to show increased outflows raising the protected buffer.
4. Select **Stale data feed** to show the engine pausing/reducing recommendations.
5. Upload a supplier invoice image/PDF, review the Gemma extraction and confirm the invoice.
6. Add item-level sales manually or import records through the sales endpoint; compare purchase-price and sales trends.
7. Show how an unpaid invoice with a confirmed due date is added to the cash-flow liability schedule.
8. Approve a smaller amount or skip; show the simulated audit-ledger entry.

## API endpoints
- `GET /health` — includes Sarvam configuration status and model ID, never the API key.
- `GET /api/v1/microsave/demo-data`
- `POST /api/v1/microsave/evaluate`
- `POST /api/v1/microsave/invoices/extract` — accepts a base64 JPG/PNG/WEBP/PDF invoice and returns a draft.
- `POST /api/v1/microsave/invoices/confirm` — persists the merchant-reviewed invoice.
- `GET /api/v1/microsave/invoices/{merchant_id}` — returns confirmed invoices.
- `POST /api/v1/microsave/sales` — records a manual or POS-imported item-level sale.
- `GET /api/v1/microsave/insights/{merchant_id}` — deterministic purchase-price/sales metrics plus a Gemma explanation when configured.
- `POST /api/v1/microsave/ledger/commit`
- `GET /api/v1/microsave/ledger/{merchant_id}`

## Demo assumptions and limitations
- UPI-only data may omit cash, card, other-app collections and off-platform expenses.
- Sample data is synthetic and generated locally.
- Forecasting uses conservative historical quantiles and simple trend/stress adjustments. It is not a trained predictive model.
- Gemma 4 31B is used for invoice document extraction and plain-language explanations only. Sarvam's documentation notes that this model is not specifically tuned for Indian languages, so regional-language invoice accuracy needs real-world validation. It does not calculate, alter or approve Safe-to-Reserve amounts.
- Invoice extraction is a draft. Merchant review is mandatory before persistence. The prototype accepts JPG, PNG, WEBP and PDF invoices up to 5 MB. PDFs are rendered to images by PyMuPDF; only the first three pages are sent to Gemma, with a warning when additional pages exist.
- Purchase-price trends use confirmed invoice line items. Product-demand trends require item-level sales records, entered manually or imported from a POS. Paytm QR payment totals alone do not identify products sold.
- Current stock is not inferred unless opening stock and adjustments for returns, damage and wastage are captured. A purchase invoice alone does not establish current inventory.
- The prototype uses merchant-confirmed demo records stored in local SQLite. It does not connect to Paytm supplier purchasing, bank statements, POS exports or Account Aggregator data automatically.
- The local SQLite ledger records simulated decisions; it does not move funds.
- `data_quality_score` is a heuristic indicator, not a probability or calibrated forecast confidence.
- Before a real pilot, the model needs merchant-specific validation, source reconciliation, secure authentication/authorization, consent and compliance review, transaction idempotency, monitoring and an authorised money-movement partner.

## Troubleshooting
If the frontend cannot reach the API, ensure the backend runs on port 8000. For a different API host/port, create `frontend/.env` with:
```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```
