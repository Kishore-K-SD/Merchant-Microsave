import { useCallback, useEffect, useMemo, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Banknote,
  BrainCircuit,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  CirclePause,
  Clock3,
  Database,
  FileText,
  History,
  Info,
  LoaderCircle,
  Plus,
  RefreshCw,
  Upload,
  PackageSearch,
  ShieldCheck,
  ShieldAlert,
  Sparkles,
  Wallet,
  XCircle,
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

type Source = {
  source_name: string;
  source_type: 'paytm_settlement' | 'account_aggregator' | 'bill_registry';
  last_synced_minutes_ago: number;
  status: 'FRESH' | 'STALE' | 'DISCONNECTED';
  coverage_note: string;
};
type Liability = {
  id: string;
  title: string;
  category: 'supplier' | 'rent' | 'utilities' | 'payroll' | 'emi' | 'tax' | 'other';
  amount: number;
  due_in_days: number;
  recurrence: 'one_time' | 'weekly' | 'monthly';
  priority: 'critical' | 'high' | 'medium';
};
type Cashflow = { date: string; upi_inflow: number; outflow: number; net_flow?: number | null };
type EvaluationRequest = {
  merchant_id: string;
  shop_name: string;
  available_balance: number;
  horizon_days: number;
  data_sources: Source[];
  liabilities: Liability[];
  recent_cashflows: Cashflow[];
  seasonality_mode: 'normal' | 'festive_surge' | 'crunch_warning';
  custom_buffer_override: number | null;
  cashflow_scope: 'upi_only' | 'multi_channel';
};
type ForecastDay = {
  day: number;
  date: string;
  conservative_inflow: number;
  stressed_operating_outflow: number;
  due_liabilities: number;
  projected_closing_balance: number;
};
type Evaluation = {
  generated_at: string;
  merchant_id: string;
  freshness_grade: 'HIGH_TRUST' | 'DEGRADED_STALE' | 'UNRELIABLE_HALT';
  max_stale_minutes: number;
  data_quality_score: number;
  history_days: number;
  due_0_to_3_days: number;
  due_4_to_7_days: number;
  due_8_to_14_days: number;
  due_15_to_30_days: number;
  total_horizon_liabilities: number;
  available_balance: number;
  p20_daily_inflow: number;
  p80_daily_operating_outflow: number;
  working_capital_buffer: number;
  projected_min_balance: number;
  safe_surplus: number;
  recommended_reserve: number;
  reserve_status: 'READY_TO_RESERVE' | 'CAUTIOUS_RESERVE' | 'PAUSE_RECOMMENDED' | 'DATA_STALE_HOLD' | 'DATA_INSUFFICIENT_HOLD';
  uncertainty_band: string;
  risk_flags: string[];
  calibration_factors: string[];
  reasoning_steps: string[];
  decision_explanation: string;
  forecast: ForecastDay[];
};
type InvoiceLineItem = {
  product_name: string;
  normalized_product_name: string;
  quantity: number | null;
  unit: string | null;
  unit_price: number | null;
  line_total: number | null;
  sku?: string | null;
};
type InvoiceDraft = {
  supplier_name: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  currency: string;
  subtotal: number | null;
  tax_amount: number | null;
  total_amount: number | null;
  amount_paid: number | null;
  items: InvoiceLineItem[];
  warnings: string[];
  requires_review: boolean;
  extraction_model?: string | null;
};
type ConfirmedInvoice = { invoice_id: string; merchant_id: string; status: string; created_at: string; invoice: InvoiceDraft };
type PurchaseTrend = {
  product_name: string; unit: string; purchase_line_count: number; total_recorded_quantity: number;
  first_observed_unit_price: number | null; latest_observed_unit_price: number | null;
  price_change_pct: number | null; first_purchase_date: string; last_purchase_date: string;
};
type SalesTrend = {
  product_name: string; unit: string; record_count_30d: number;
  quantity_sold_30d: number; average_selling_price: number; last_sale_date: string;
};
type MerchantInsights = {
  merchant_id: string; generated_at: string; invoice_count: number; sales_record_count_30d: number;
  purchase_trends: PurchaseTrend[]; sales_trends_30d: SalesTrend[]; llm_narrative: string;
  llm_status: 'GENERATED' | 'NOT_CONFIGURED' | 'UPSTREAM_ERROR'; llm_model: string;
  data_limitations: string[]; llm_caveats: string[];
};

type LedgerEntry = {
  entry_id: string;
  merchant_id: string;
  timestamp: string;
  action: 'APPROVED' | 'MODIFIED_APPROVED' | 'SKIPPED';
  recommended_amount: number;
  executed_amount: number;
  instrument_split: Record<string, number>;
  settlement_ref: string;
  balance_before: number;
  balance_after: number;
  data_quality_score: number;
  simulated: boolean;
};

const money = (value: number) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value || 0);
const shortDate = (date: string) => new Date(`${date}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-slate-200 bg-white shadow-sm ${className}`}>{children}</section>;
}
function SectionTitle({ icon: Icon, eyebrow, title, right }: { icon: typeof Wallet; eyebrow?: string; title: string; right?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-start gap-3">
        <div className="rounded-xl bg-sky-50 p-2.5 text-sky-700"><Icon size={18} /></div>
        <div>
          {eyebrow && <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-sky-700">{eyebrow}</p>}
          <h2 className="text-base font-bold text-slate-900">{title}</h2>
        </div>
      </div>
      {right}
    </div>
  );
}

export default function App() {
  const [request, setRequest] = useState<EvaluationRequest | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [selectedReserve, setSelectedReserve] = useState(0);
  const [scenario, setScenario] = useState('normal');
  const [newTitle, setNewTitle] = useState('');
  const [newAmount, setNewAmount] = useState('');
  const [newDue, setNewDue] = useState('3');
  const [newCategory, setNewCategory] = useState<Liability['category']>('supplier');
  const [invoiceFile, setInvoiceFile] = useState<File | null>(null);
  const [invoiceDraft, setInvoiceDraft] = useState<InvoiceDraft | null>(null);
  const [invoiceModel, setInvoiceModel] = useState('gemma4');
  const [invoiceBusy, setInvoiceBusy] = useState(false);
  const [invoiceSaving, setInvoiceSaving] = useState(false);
  const [invoiceMessage, setInvoiceMessage] = useState('');
  const [invoiceError, setInvoiceError] = useState('');
  const [confirmedInvoices, setConfirmedInvoices] = useState<ConfirmedInvoice[]>([]);
  const [merchantInsights, setMerchantInsights] = useState<MerchantInsights | null>(null);
  const [salesProduct, setSalesProduct] = useState('');
  const [salesQuantity, setSalesQuantity] = useState('');
  const [salesUnit, setSalesUnit] = useState('pack');
  const [salesPrice, setSalesPrice] = useState('');
  const [salesBusy, setSalesBusy] = useState(false);

  const loadLedger = useCallback(async (merchantId: string) => {
    const rows = await api<LedgerEntry[]>(`/api/v1/microsave/ledger/${encodeURIComponent(merchantId)}`);
    setLedger(rows);
  }, []);

  const loadPurchaseInsights = useCallback(async (merchantId: string) => {
    const [invoiceRows, trends] = await Promise.all([
      api<ConfirmedInvoice[]>(`/api/v1/microsave/invoices/${encodeURIComponent(merchantId)}`),
      api<MerchantInsights>(`/api/v1/microsave/insights/${encodeURIComponent(merchantId)}`),
    ]);
    setConfirmedInvoices(invoiceRows);
    setMerchantInsights(trends);
  }, []);

  const runEvaluation = useCallback(async (payload: EvaluationRequest, showLoader = true) => {
    if (showLoader) setEvaluating(true);
    setError('');
    try {
      const result = await api<Evaluation>('/api/v1/microsave/evaluate', {
        method: 'POST', body: JSON.stringify(payload),
      });
      setRequest(payload);
      setEvaluation(result);
      setSelectedReserve(result.recommended_reserve);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to evaluate merchant cash flow.');
      throw err;
    } finally {
      if (showLoader) setEvaluating(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const demo = await api<EvaluationRequest>('/api/v1/microsave/demo-data');
        if (!active) return;
        setRequest(demo);
        const result = await api<Evaluation>('/api/v1/microsave/evaluate', { method: 'POST', body: JSON.stringify(demo) });
        if (!active) return;
        setEvaluation(result);
        setSelectedReserve(result.recommended_reserve);
        const rows = await api<LedgerEntry[]>(`/api/v1/microsave/ledger/${encodeURIComponent(demo.merchant_id)}`);
        if (active) setLedger(rows);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : 'Could not connect to the MicroSave API.');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!request?.merchant_id) return;
    let active = true;
    (async () => {
      try {
        const [invoiceRows, trends] = await Promise.all([
          api<ConfirmedInvoice[]>(`/api/v1/microsave/invoices/${encodeURIComponent(request.merchant_id)}`),
          api<MerchantInsights>(`/api/v1/microsave/insights/${encodeURIComponent(request.merchant_id)}`),
        ]);
        if (active) { setConfirmedInvoices(invoiceRows); setMerchantInsights(trends); }
      } catch (err) {
        if (active) setInvoiceError(err instanceof Error ? err.message : 'Could not load purchase insights.');
      }
    })();
    return () => { active = false; };
  }, [request?.merchant_id]);

  const activeReserve = Math.min(selectedReserve, evaluation?.recommended_reserve ?? 0);
  const totalReserved = useMemo(() => ledger.reduce((sum, row) => sum + row.executed_amount, 0), [ledger]);
  const maxForecastBalance = useMemo(
    () => Math.max(1, ...(evaluation?.forecast.map((day) => day.projected_closing_balance) || [1])),
    [evaluation],
  );

  const updateAndEvaluate = async (next: EvaluationRequest) => {
    setRequest(next);
    try { await runEvaluation(next); } catch { /* error shown by runEvaluation */ }
  };

  const setStressScenario = async (kind: 'normal' | 'slow' | 'outflow' | 'stale') => {
    if (!request) return;
    const base = await api<EvaluationRequest>('/api/v1/microsave/demo-data');
    let next = { ...base, data_sources: base.data_sources.map((source) => ({ ...source })), recent_cashflows: base.recent_cashflows.map((row) => ({ ...row })) };
    if (kind === 'slow') {
      next.recent_cashflows = next.recent_cashflows.map((row, index) => index >= next.recent_cashflows.length - 7 ? { ...row, upi_inflow: Math.round(row.upi_inflow * 0.38) } : row);
      next.shop_name = 'Sri Murugan Departmental Store · Slow sales stress test';
    } else if (kind === 'outflow') {
      next.recent_cashflows = next.recent_cashflows.map((row, index) => index >= next.recent_cashflows.length - 7 ? { ...row, outflow: Math.round(row.outflow * 2.1) } : row);
      next.shop_name = 'Sri Murugan Departmental Store · High outflow stress test';
    } else if (kind === 'stale') {
      next.data_sources = next.data_sources.map((source, index) => index === 1 ? { ...source, status: 'STALE', last_synced_minutes_ago: 360 } : source);
      next.shop_name = 'Sri Murugan Departmental Store · Stale data stress test';
    }
    setScenario(kind);
    await updateAndEvaluate(next);
  };

  const syncDemoData = async () => {
    if (!request) return;
    const base = await api<EvaluationRequest>('/api/v1/microsave/demo-data');
    setScenario('normal');
    await updateAndEvaluate(base);
    setSuccess('Demo data refreshed. No external Paytm or bank connection was made.');
  };

  const addLiability = async (event: FormEvent) => {
    event.preventDefault();
    if (!request || !newTitle.trim() || Number(newAmount) <= 0) return;
    const item: Liability = {
      id: `merchant-${Date.now()}`,
      title: newTitle.trim(),
      category: newCategory,
      amount: Number(newAmount),
      due_in_days: Number(newDue),
      recurrence: 'one_time',
      priority: newCategory === 'supplier' || newCategory === 'rent' ? 'critical' : 'medium',
    };
    const next = { ...request, liabilities: [...request.liabilities, item] };
    setNewTitle(''); setNewAmount('');
    await updateAndEvaluate(next);
  };

  const removeLiability = async (id: string) => {
    if (!request) return;
    await updateAndEvaluate({ ...request, liabilities: request.liabilities.filter((item) => item.id !== id) });
  };

  const extractInvoice = async () => {
    if (!invoiceFile || !request) return;
    setInvoiceBusy(true); setInvoiceError(''); setInvoiceMessage(''); setInvoiceDraft(null);
    try {
      if (!['image/jpeg', 'image/png', 'image/webp', 'application/pdf'].includes(invoiceFile.type)) {
        throw new Error('Choose a JPG, PNG, WEBP or PDF invoice.');
      }
      if (invoiceFile.size > 5 * 1024 * 1024) throw new Error('Invoice image must be 5 MB or smaller.');
      const bytes = new Uint8Array(await invoiceFile.arrayBuffer());
      let binary = '';
      for (let index = 0; index < bytes.length; index += 1) binary += String.fromCharCode(bytes[index]);
      const encoded = btoa(binary);
      const result = await api<{ draft: InvoiceDraft; model: string }>('/api/v1/microsave/invoices/extract', {
        method: 'POST',
        body: JSON.stringify({ merchant_id: request.merchant_id, filename: invoiceFile.name, mime_type: invoiceFile.type, image_base64: encoded }),
      });
      setInvoiceDraft(result.draft); setInvoiceModel(result.model);
      setInvoiceMessage('Invoice extracted. Review every field before confirming it.');
    } catch (err) {
      setInvoiceError(err instanceof Error ? err.message : 'Invoice extraction failed.');
    } finally { setInvoiceBusy(false); }
  };

  const updateInvoiceDraft = (patch: Partial<InvoiceDraft>) => {
    setInvoiceDraft((current) => current ? { ...current, ...patch } : current);
  };

  const updateInvoiceItem = (index: number, patch: Partial<InvoiceLineItem>) => {
    setInvoiceDraft((current) => current ? {
      ...current,
      items: current.items.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item),
    } : current);
  };

  const confirmInvoice = async () => {
    if (!request || !invoiceDraft) return;
    setInvoiceSaving(true); setInvoiceError(''); setInvoiceMessage('');
    try {
      const confirmed = await api<ConfirmedInvoice>('/api/v1/microsave/invoices/confirm', {
        method: 'POST', body: JSON.stringify({ merchant_id: request.merchant_id, invoice: invoiceDraft }),
      });
      setInvoiceDraft(null); setInvoiceFile(null);
      setInvoiceMessage(`Invoice ${confirmed.invoice_id} saved after merchant confirmation.`);

      const outstanding = Math.max(0, Number(invoiceDraft.total_amount || 0) - Number(invoiceDraft.amount_paid || 0));
      if (outstanding > 0 && invoiceDraft.due_date) {
        const dueDate = new Date(`${invoiceDraft.due_date}T00:00:00`);
        const today = new Date(); today.setHours(0, 0, 0, 0);
        const dueInDays = Math.max(0, Math.ceil((dueDate.getTime() - today.getTime()) / 86400000));
        const liability: Liability = {
          id: confirmed.invoice_id,
          title: `Supplier ${invoiceDraft.supplier_name || 'invoice'} · ${invoiceDraft.invoice_number || confirmed.invoice_id}`,
          category: 'supplier', amount: outstanding, due_in_days: dueInDays,
          recurrence: 'one_time', priority: 'critical',
        };
        const next = { ...request, liabilities: [...request.liabilities.filter((item) => item.id !== liability.id), liability] };
        await updateAndEvaluate(next);
        setInvoiceMessage(`Invoice saved. Outstanding ${money(outstanding)} has been added to the forecast using the extracted due date.`);
      } else if (outstanding > 0) {
        setInvoiceMessage(`Invoice saved. ${money(outstanding)} remains unpaid, but no due date was found. Add its due date as a supplier liability before relying on the reserve estimate.`);
      }
      await loadPurchaseInsights(request.merchant_id);
    } catch (err) {
      setInvoiceError(err instanceof Error ? err.message : 'Could not confirm the invoice.');
    } finally { setInvoiceSaving(false); }
  };

  const recordSale = async (event: FormEvent) => {
    event.preventDefault();
    if (!request || !salesProduct.trim() || Number(salesQuantity) <= 0 || Number(salesPrice) <= 0) return;
    setSalesBusy(true); setInvoiceError(''); setInvoiceMessage('');
    try {
      await api('/api/v1/microsave/sales', {
        method: 'POST',
        body: JSON.stringify({
          merchant_id: request.merchant_id, product_name: salesProduct.trim(),
          normalized_product_name: salesProduct.trim(), quantity: Number(salesQuantity),
          unit: salesUnit, unit_selling_price: Number(salesPrice),
          sale_date: (() => { const now = new Date(); return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10); })(), source: 'manual',
        }),
      });
      setSalesProduct(''); setSalesQuantity(''); setSalesPrice('');
      await loadPurchaseInsights(request.merchant_id);
      setInvoiceMessage('Item-level sale recorded. Purchase and sales trends refreshed.');
    } catch (err) {
      setInvoiceError(err instanceof Error ? err.message : 'Could not record the sale.');
    } finally { setSalesBusy(false); }
  };

  const commitDecision = async (action: 'APPROVED' | 'MODIFIED_APPROVED' | 'SKIPPED') => {
    if (!request || !evaluation) return;
    const amount = action === 'SKIPPED' ? 0 : activeReserve;
    setCommitting(true); setError(''); setSuccess('');
    try {
      const entry = await api<LedgerEntry>('/api/v1/microsave/ledger/commit', {
        method: 'POST',
        body: JSON.stringify({ evaluation_request: request, action, requested_amount: amount }),
      });
      setLedger((previous) => [entry, ...previous]);
      if (entry.executed_amount > 0) {
        const next = { ...request, available_balance: Math.max(0, request.available_balance - entry.executed_amount) };
        setScenario('normal');
        await runEvaluation(next, false);
        setSuccess(`${money(entry.executed_amount)} added to the simulated reserve ledger. No real money was moved.`);
      } else {
        setSuccess('Decision recorded. No reserve transfer was simulated.');
      }
      setSelectedReserve(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not record this reserve decision.');
    } finally {
      setCommitting(false);
    }
  };

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-50"><div className="flex items-center gap-3 rounded-xl bg-white px-5 py-4 shadow-sm"><LoaderCircle className="animate-spin text-sky-600" /> <span className="text-sm font-semibold text-slate-700">Loading MicroSave demo…</span></div></div>;
  }
  if (!request || !evaluation) {
    return <div className="min-h-screen bg-slate-50 p-8"><div className="mx-auto max-w-xl rounded-2xl border border-red-200 bg-white p-6"><h1 className="text-lg font-bold">MicroSave API is not reachable</h1><p className="mt-2 text-sm text-slate-600">Start the FastAPI backend, then refresh this page.</p><p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error || 'No response from API.'}</p><button onClick={() => window.location.reload()} className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white">Retry</button></div></div>;
  }

  const isPaused = evaluation.recommended_reserve <= 0;
  const statusLabel: Record<Evaluation['reserve_status'], string> = {
    READY_TO_RESERVE: 'Ready to reserve',
    CAUTIOUS_RESERVE: 'Cautious reserve',
    PAUSE_RECOMMENDED: 'Reserve paused',
    DATA_STALE_HOLD: 'Stale data hold',
    DATA_INSUFFICIENT_HOLD: 'Insufficient data hold',
  };

  return (
    <div className="min-h-screen bg-[#F4F7FB] text-slate-900">
      <header className="bg-[#002970] text-white shadow-lg">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-white px-2.5 py-1.5 text-lg font-black tracking-tight"><span className="text-[#002970]">Pay</span><span className="text-[#00BAF2]">tm</span></div>
            <div><div className="flex flex-wrap items-center gap-2"><h1 className="text-lg font-extrabold">Merchant MicroSave</h1><span className="rounded-full border border-sky-300/50 bg-sky-400/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-sky-200">Hackathon prototype</span></div><p className="text-xs text-blue-200">{request.shop_name.split(' · ')[0]} · {request.merchant_id}</p></div>
          </div>
          <div className="flex items-center gap-5"><div className="hidden text-right sm:block"><p className="text-[10px] font-semibold uppercase tracking-widest text-blue-200">Simulated reserve ledger</p><p className="text-xl font-extrabold text-[#00BAF2]">{money(totalReserved)}</p></div><div className="rounded-full border border-amber-300/40 bg-amber-400/10 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-amber-200">Demo data · No live banking</div></div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-6 sm:px-6 lg:px-8">
        <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end"><div><p className="text-xs font-bold uppercase tracking-[0.18em] text-sky-700">Merchant financial resilience</p><h2 className="mt-1 text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">Protect today's cash. Plan for tomorrow.</h2><p className="mt-1 max-w-2xl text-sm text-slate-600">The engine forecasts cash flow, reserves upcoming liabilities and recommends only the surplus above a protected operating buffer.</p></div><button onClick={syncDemoData} disabled={evaluating} className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50"><RefreshCw size={15} className={evaluating ? 'animate-spin' : ''}/> Reset demo data</button></div>

        {(error || success) && <div className={`flex items-start gap-2 rounded-xl border p-3 text-sm ${error ? 'border-red-200 bg-red-50 text-red-800' : 'border-emerald-200 bg-emerald-50 text-emerald-800'}`}>{error ? <AlertTriangle size={17} className="mt-0.5 shrink-0"/> : <CheckCircle2 size={17} className="mt-0.5 shrink-0"/>}<span>{error || success}</span><button onClick={() => { setError(''); setSuccess(''); }} className="ml-auto text-xs font-bold">Dismiss</button></div>}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Card className="p-4"><div className="flex items-center justify-between"><span className="text-xs font-semibold text-slate-500">Available balance</span><Wallet size={17} className="text-sky-700"/></div><p className="mt-2 text-2xl font-black tracking-tight">{money(request.available_balance)}</p><p className="mt-1 text-[11px] text-slate-500">Demo settled-balance snapshot</p></Card>
          <Card className="p-4"><div className="flex items-center justify-between"><span className="text-xs font-semibold text-slate-500">Upcoming liabilities</span><CalendarClock size={17} className="text-amber-600"/></div><p className="mt-2 text-2xl font-black tracking-tight">{money(evaluation.total_horizon_liabilities)}</p><p className="mt-1 text-[11px] text-slate-500">Due within {request.horizon_days} days</p></Card>
          <Card className="p-4"><div className="flex items-center justify-between"><span className="text-xs font-semibold text-slate-500">Protected working capital</span><ShieldCheck size={17} className="text-emerald-700"/></div><p className="mt-2 text-2xl font-black tracking-tight">{money(evaluation.working_capital_buffer)}</p><p className="mt-1 text-[11px] text-slate-500">Never reduced by merchant override</p></Card>
          <Card className="border-sky-200 bg-sky-50/70 p-4"><div className="flex items-center justify-between"><span className="text-xs font-semibold text-sky-800">Safe-to-reserve surplus</span><Sparkles size={17} className="text-sky-700"/></div><p className="mt-2 text-2xl font-black tracking-tight text-sky-950">{money(evaluation.safe_surplus)}</p><p className="mt-1 text-[11px] text-sky-800">After forecast and protected cash floor</p></Card>
        </div>

        <div className="grid items-start gap-5 xl:grid-cols-[1.08fr_.92fr]">
          <div className="space-y-5">
            <Card className="p-5">
              <SectionTitle icon={Database} eyebrow="Data integrity gate" title="Connected data sources" right={<span className={`rounded-full px-2.5 py-1 text-[10px] font-extrabold ${evaluation.freshness_grade === 'HIGH_TRUST' ? 'bg-emerald-100 text-emerald-800' : evaluation.freshness_grade === 'DEGRADED_STALE' ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800'}`}>{evaluation.freshness_grade.replaceAll('_', ' ')}</span>}/>
              <div className="mt-4 grid gap-2 sm:grid-cols-3">{request.data_sources.map((source) => <div key={source.source_type} className="rounded-xl border border-slate-200 bg-slate-50 p-3"><div className="flex items-center justify-between gap-2"><span className="truncate text-xs font-bold text-slate-800">{source.source_name}</span><span className={`h-2 w-2 shrink-0 rounded-full ${source.status === 'FRESH' ? 'bg-emerald-500' : source.status === 'STALE' ? 'bg-amber-500' : 'bg-red-500'}`}/></div><p className="mt-2 text-[11px] text-slate-500">Synced {source.last_synced_minutes_ago} min ago</p><p className="mt-1 line-clamp-2 text-[10px] leading-relaxed text-slate-400">{source.coverage_note}</p></div>)}</div>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2"><span className="text-xs text-slate-600">Data quality score <strong className="text-slate-900">{evaluation.data_quality_score}/100</strong> · {evaluation.history_days} distinct history days</span><span className="text-[10px] font-semibold text-slate-500">Oldest feed: {evaluation.max_stale_minutes} min</span></div>
            </Card>

            <Card className="p-5">
              <SectionTitle icon={Activity} eyebrow="Conservative projection" title={`${request.horizon_days}-day liquidity forecast`} right={<span className="text-[10px] font-semibold text-slate-500">Planning scenario · not a guarantee</span>}/>
              <div className="mt-4 grid grid-cols-2 gap-3"><div className="rounded-xl bg-slate-50 p-3"><p className="text-[11px] text-slate-500">Conservative daily inflow</p><p className="mt-1 text-lg font-extrabold text-emerald-700">{money(evaluation.p20_daily_inflow)}</p><p className="text-[10px] text-slate-400">P20, trend-adjusted</p></div><div className="rounded-xl bg-slate-50 p-3"><p className="text-[11px] text-slate-500">Stressed operating outflow</p><p className="mt-1 text-lg font-extrabold text-rose-700">{money(evaluation.p80_daily_operating_outflow)}</p><p className="text-[10px] text-slate-400">P80 or recent 7-day average</p></div></div>
              <div className="mt-5 space-y-3">{evaluation.forecast.slice(0, 14).map((day) => <div key={day.day} className="grid grid-cols-[48px_1fr_92px] items-center gap-3"><span className="text-[10px] font-semibold text-slate-500">{shortDate(day.date)}</span><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${day.projected_closing_balance < evaluation.working_capital_buffer ? 'bg-rose-500' : 'bg-sky-500'}`} style={{ width: `${Math.max(2, Math.min(100, (Math.max(0, day.projected_closing_balance) / maxForecastBalance) * 100))}%` }}/></div><span className={`text-right text-[11px] font-bold tabular-nums ${day.projected_closing_balance < evaluation.working_capital_buffer ? 'text-rose-700' : 'text-slate-700'}`}>{money(day.projected_closing_balance)}</span></div>)}</div>
              <div className="mt-4 flex flex-wrap gap-2 text-[10px] text-slate-500"><span className="rounded-md bg-slate-100 px-2 py-1">Lowest projected balance: <strong className="text-slate-800">{money(evaluation.projected_min_balance)}</strong></span><span className="rounded-md bg-slate-100 px-2 py-1">Planning surplus range: <strong className="text-slate-800">{evaluation.uncertainty_band}</strong></span></div>
            </Card>

            <Card className="p-5">
              <SectionTitle icon={FileText} eyebrow="Obligation calendar" title="Upcoming business liabilities" right={<span className="text-xs font-bold text-slate-500">{request.liabilities.length} items</span>}/>
              <div className="mt-4 divide-y divide-slate-100">{request.liabilities.map((item) => <div key={item.id} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"><div className="min-w-0"><p className="truncate text-sm font-bold text-slate-800">{item.title}</p><p className="mt-0.5 text-[11px] capitalize text-slate-500">{item.category} · {item.due_in_days === 0 ? 'Due today' : `Due in ${item.due_in_days} days`}{item.recurrence === 'weekly' ? ' · Weekly' : ''}</p></div><div className="flex items-center gap-3"><span className="text-sm font-extrabold tabular-nums">{money(item.amount)}</span><button onClick={() => removeLiability(item.id)} title="Remove liability" className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"><XCircle size={15}/></button></div></div>)}</div>
              <form onSubmit={addLiability} className="mt-4 grid gap-2 rounded-xl bg-slate-50 p-3 sm:grid-cols-[1.4fr_.8fr_.8fr_auto]"><input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} required placeholder="Add supplier bill / expense" className="min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs outline-none focus:border-sky-400"/><input value={newAmount} onChange={(e) => setNewAmount(e.target.value)} type="number" min="1" required placeholder="Amount ₹" className="min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs outline-none focus:border-sky-400"/><select value={newDue} onChange={(e) => setNewDue(e.target.value)} className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-xs"><option value="0">Due today</option><option value="2">In 2 days</option><option value="5">In 5 days</option><option value="10">In 10 days</option><option value="20">In 20 days</option></select><button className="inline-flex items-center justify-center gap-1 rounded-lg bg-[#002970] px-3 py-2 text-xs font-bold text-white hover:bg-blue-950"><Plus size={14}/> Add</button><select value={newCategory} onChange={(e) => setNewCategory(e.target.value as Liability['category'])} className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-xs sm:col-span-2"><option value="supplier">Supplier</option><option value="rent">Rent</option><option value="payroll">Payroll</option><option value="utilities">Utilities</option><option value="emi">EMI</option><option value="tax">Tax</option><option value="other">Other</option></select></form>
            </Card>
          </div>

          <div className="space-y-5 xl:sticky xl:top-5">
            <Card className="overflow-hidden border-sky-200">
              <div className="bg-gradient-to-br from-[#002970] to-[#064B91] p-5 text-white"><div className="flex items-start justify-between gap-3"><div><p className="text-[10px] font-bold uppercase tracking-[0.17em] text-sky-200">Safe-to-Reserve Engine</p><h3 className="mt-1 text-xl font-extrabold">{isPaused ? 'Keep your cash protected' : 'A reserve you can afford'}</h3></div><div className="rounded-xl bg-white/10 p-2.5">{isPaused ? <CirclePause size={21}/> : <ShieldCheck size={21}/>}</div></div><p className="mt-2 text-sm leading-relaxed text-blue-100">{evaluation.decision_explanation}</p><div className="mt-4 flex items-end justify-between gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-wider text-blue-200">Recommended reserve</p><p className="mt-1 text-4xl font-black tracking-tight">{money(evaluation.recommended_reserve)}</p></div><span className="mb-1 rounded-full border border-white/20 bg-white/10 px-2.5 py-1 text-[10px] font-bold">{statusLabel[evaluation.reserve_status]}</span></div></div>
              <div className="space-y-4 p-5">
                <div className="grid grid-cols-2 gap-2"><div className="rounded-xl bg-slate-50 p-3"><p className="text-[10px] text-slate-500">Liabilities protected</p><p className="mt-1 text-lg font-extrabold">{money(evaluation.total_horizon_liabilities)}</p></div><div className="rounded-xl bg-slate-50 p-3"><p className="text-[10px] text-slate-500">Safe surplus</p><p className="mt-1 text-lg font-extrabold text-emerald-700">{money(evaluation.safe_surplus)}</p></div></div>
                {!isPaused && <div><div className="flex items-center justify-between gap-2"><label htmlFor="reserve-slider" className="text-xs font-bold text-slate-700">Adjust amount (you can reduce it)</label><span className="text-sm font-extrabold text-sky-800">{money(activeReserve)}</span></div><input id="reserve-slider" type="range" min="0" max={evaluation.recommended_reserve} step="100" value={activeReserve} onChange={(e) => setSelectedReserve(Number(e.target.value))} className="mt-3 w-full accent-sky-600"/><div className="flex justify-between text-[10px] text-slate-400"><span>₹0</span><span>Engine cap {money(evaluation.recommended_reserve)}</span></div></div>}
                <div className="flex flex-col gap-2 sm:flex-row"><button onClick={() => commitDecision(activeReserve < evaluation.recommended_reserve ? 'MODIFIED_APPROVED' : 'APPROVED')} disabled={isPaused || activeReserve <= 0 || committing || evaluating} className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-[#002970] px-4 py-3 text-sm font-extrabold text-white shadow-sm hover:bg-blue-950 disabled:cursor-not-allowed disabled:bg-slate-300">{committing ? <LoaderCircle className="animate-spin" size={16}/> : <CheckCircle2 size={16}/>} Approve {money(activeReserve)}</button><button onClick={() => commitDecision('SKIPPED')} disabled={committing || evaluating} className="rounded-xl border border-slate-300 px-4 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50">Skip today</button></div>
                <p className="text-center text-[10px] leading-relaxed text-slate-400">Approval writes to a local simulated ledger only. It does not debit a bank account, buy gold, or transfer real funds.</p>
                <div className="border-t border-slate-100 pt-3"><div className="flex items-center justify-between"><p className="text-xs font-bold text-slate-700">Why this recommendation?</p><span className="text-[10px] font-bold text-slate-500">Data quality {evaluation.data_quality_score}/100</span></div><div className="mt-2 space-y-2">{evaluation.reasoning_steps.map((step, index) => <div key={index} className="flex gap-2 text-[11px] leading-relaxed text-slate-600"><ChevronRight size={13} className="mt-0.5 shrink-0 text-sky-600"/>{step}</div>)}</div></div>
                {evaluation.risk_flags.length > 0 && <div className="rounded-xl border border-amber-200 bg-amber-50 p-3"><div className="flex items-center gap-2 text-xs font-bold text-amber-900"><ShieldAlert size={14}/> Data and risk warnings</div><ul className="mt-2 space-y-1.5">{evaluation.risk_flags.map((flag, index) => <li key={index} className="flex gap-2 text-[11px] leading-relaxed text-amber-800"><span>•</span><span>{flag}</span></li>)}</ul></div>}
              </div>
            </Card>

            <Card className="p-5"><SectionTitle icon={Activity} eyebrow="Judge showcase controls" title="Test changing business conditions"/><p className="mt-2 text-xs text-slate-500">Switch between synthetic data scenarios to show how the engine responds.</p><div className="mt-4 grid grid-cols-2 gap-2"><button onClick={() => setStressScenario('normal')} className={`rounded-xl border p-3 text-left text-xs font-bold ${scenario === 'normal' ? 'border-sky-300 bg-sky-50 text-sky-900' : 'border-slate-200 hover:bg-slate-50'}`}><span className="mb-1 block text-emerald-600"><CheckCircle2 size={16}/></span>Normal trading</button><button onClick={() => setStressScenario('slow')} className={`rounded-xl border p-3 text-left text-xs font-bold ${scenario === 'slow' ? 'border-amber-300 bg-amber-50 text-amber-900' : 'border-slate-200 hover:bg-slate-50'}`}><span className="mb-1 block text-amber-600"><ArrowDownRight size={16}/></span>Slow sales week</button><button onClick={() => setStressScenario('outflow')} className={`rounded-xl border p-3 text-left text-xs font-bold ${scenario === 'outflow' ? 'border-rose-300 bg-rose-50 text-rose-900' : 'border-slate-200 hover:bg-slate-50'}`}><span className="mb-1 block text-rose-600"><ArrowUpRight size={16}/></span>Expense spike</button><button onClick={() => setStressScenario('stale')} className={`rounded-xl border p-3 text-left text-xs font-bold ${scenario === 'stale' ? 'border-slate-400 bg-slate-100 text-slate-900' : 'border-slate-200 hover:bg-slate-50'}`}><span className="mb-1 block text-slate-600"><Clock3 size={16}/></span>Stale data feed</button></div><div className="mt-3 flex items-start gap-2 rounded-lg bg-slate-50 p-2.5 text-[10px] leading-relaxed text-slate-500"><Info size={13} className="mt-0.5 shrink-0"/>These are controlled stress tests, not live Paytm transactions or predictions about an actual merchant.</div></Card>

            <Card className="p-5"><SectionTitle icon={History} eyebrow="Persistent audit trail" title="Reserve decision ledger" right={<span className="text-[10px] font-semibold text-slate-500">{ledger.length} records</span>}/>{ledger.length === 0 ? <div className="mt-4 rounded-xl bg-slate-50 p-5 text-center"><Banknote className="mx-auto text-slate-300" size={25}/><p className="mt-2 text-sm font-bold text-slate-700">No decisions yet</p><p className="mt-1 text-xs text-slate-500">Approve or skip a recommendation to create the first ledger entry.</p></div> : <div className="mt-3 max-h-72 space-y-2 overflow-y-auto">{ledger.map((entry) => <div key={entry.entry_id} className="rounded-xl border border-slate-200 p-3"><div className="flex items-center justify-between gap-2"><span className="text-[10px] font-extrabold text-slate-800">{entry.entry_id}</span><span className={`rounded-full px-2 py-0.5 text-[9px] font-extrabold ${entry.executed_amount > 0 ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'}`}>{entry.action.replaceAll('_', ' ')}</span></div><div className="mt-1 flex items-end justify-between gap-2"><div><p className="text-[10px] text-slate-500">{new Date(entry.timestamp).toLocaleString('en-IN')}</p><p className="mt-0.5 text-[9px] text-slate-400">{entry.settlement_ref} · Simulated</p></div><p className="text-sm font-extrabold tabular-nums">{money(entry.executed_amount)}</p></div></div>)}</div>}</Card>
          </div>
        </div>

        <section className="grid gap-5 xl:grid-cols-[1.05fr_.95fr]">
          <Card className="p-5">
            <SectionTitle icon={Upload} eyebrow="Gemma 4 31B · Sarvam AI" title="Supplier invoice intelligence" right={<span className="rounded-full bg-violet-50 px-2.5 py-1 text-[10px] font-bold text-violet-800">AI extraction · human confirmation</span>}/>
            <p className="mt-2 text-xs leading-relaxed text-slate-500">Upload a supplier invoice image. Gemma extracts supplier, invoice, item, quantity and price details. Nothing is saved to the purchase ledger until you review and confirm it.</p>
            <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
              <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf,.pdf" onChange={(event) => { setInvoiceFile(event.target.files?.[0] || null); setInvoiceDraft(null); setInvoiceError(''); setInvoiceMessage(''); }} className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs file:mr-3 file:rounded-md file:border-0 file:bg-white file:px-2 file:py-1 file:text-xs file:font-bold"/>
              <button onClick={extractInvoice} disabled={!invoiceFile || invoiceBusy} className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#002970] px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50">{invoiceBusy ? <LoaderCircle size={15} className="animate-spin"/> : <BrainCircuit size={15}/>} Extract invoice</button>
            </div>
            <p className="mt-1 text-[10px] text-slate-400">JPG, PNG, WEBP or PDF · maximum 5 MB · first three PDF pages are processed.</p>
            {(invoiceError || invoiceMessage) && <div className={`mt-3 rounded-lg p-2.5 text-xs ${invoiceError ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-800'}`}>{invoiceError || invoiceMessage}</div>}
            {invoiceDraft && <div className="mt-4 space-y-3 rounded-xl border border-violet-200 bg-violet-50/40 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-extrabold text-slate-800">Review extracted invoice</p><span className="rounded-full bg-violet-100 px-2 py-1 text-[10px] font-bold text-violet-800">{invoiceModel} · draft only</span></div>
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="text-[10px] font-semibold text-slate-600">Supplier name<input value={invoiceDraft.supplier_name || ''} onChange={(e) => updateInvoiceDraft({ supplier_name: e.target.value })} className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"/></label>
                <label className="text-[10px] font-semibold text-slate-600">Invoice number<input value={invoiceDraft.invoice_number || ''} onChange={(e) => updateInvoiceDraft({ invoice_number: e.target.value })} className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"/></label>
                <label className="text-[10px] font-semibold text-slate-600">Invoice date<input type="date" value={invoiceDraft.invoice_date || ''} onChange={(e) => updateInvoiceDraft({ invoice_date: e.target.value || null })} className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"/></label>
                <label className="text-[10px] font-semibold text-slate-600">Payment due date<input type="date" value={invoiceDraft.due_date || ''} onChange={(e) => updateInvoiceDraft({ due_date: e.target.value || null })} className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"/></label>
                <label className="text-[10px] font-semibold text-slate-600">Invoice total (₹)<input type="number" min="0" step="0.01" value={invoiceDraft.total_amount ?? ''} onChange={(e) => updateInvoiceDraft({ total_amount: e.target.value === '' ? null : Number(e.target.value) })} className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"/></label>
                <label className="text-[10px] font-semibold text-slate-600">Amount already paid (₹)<input type="number" min="0" step="0.01" value={invoiceDraft.amount_paid ?? ''} onChange={(e) => updateInvoiceDraft({ amount_paid: e.target.value === '' ? null : Number(e.target.value) })} className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"/></label>
              </div>
              <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white"><table className="w-full min-w-[540px] text-left text-[10px]"><thead className="bg-slate-50 text-slate-500"><tr><th className="p-2">Product</th><th className="p-2">Qty</th><th className="p-2">Unit</th><th className="p-2">Unit price</th><th className="p-2">Line total</th></tr></thead><tbody>{invoiceDraft.items.map((item, index) => <tr key={`${index}-${item.product_name}`} className="border-t border-slate-100"><td className="p-2"><input value={item.product_name} onChange={(e) => updateInvoiceItem(index, { product_name: e.target.value, normalized_product_name: e.target.value })} className="w-40 rounded border border-slate-200 px-2 py-1 text-[10px]"/></td><td className="p-2"><input type="number" min="0" value={item.quantity ?? ''} onChange={(e) => updateInvoiceItem(index, { quantity: e.target.value === '' ? null : Number(e.target.value) })} className="w-16 rounded border border-slate-200 px-2 py-1 text-[10px]"/></td><td className="p-2"><input value={item.unit || ''} onChange={(e) => updateInvoiceItem(index, { unit: e.target.value })} className="w-16 rounded border border-slate-200 px-2 py-1 text-[10px]"/></td><td className="p-2"><input type="number" min="0" value={item.unit_price ?? ''} onChange={(e) => updateInvoiceItem(index, { unit_price: e.target.value === '' ? null : Number(e.target.value) })} className="w-20 rounded border border-slate-200 px-2 py-1 text-[10px]"/></td><td className="p-2 tabular-nums">{item.line_total == null ? '—' : money(item.line_total)}</td></tr>)}</tbody></table></div>
              {invoiceDraft.warnings.length > 0 && <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-[10px] text-amber-800"><strong>Check these extraction warnings:</strong><ul className="mt-1 list-disc pl-4">{invoiceDraft.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}
              <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-[10px] text-slate-500">Review totals, paid amount, units and dates against the original invoice. Enter the amount already paid when it is not printed.</p><button onClick={confirmInvoice} disabled={invoiceSaving || !invoiceDraft.supplier_name?.trim() || !invoiceDraft.total_amount || invoiceDraft.amount_paid == null || invoiceDraft.items.length === 0 || invoiceDraft.items.some((item) => item.quantity == null || item.quantity <= 0 || !item.unit?.trim() || (item.unit_price == null && item.line_total == null))} className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-3 py-2 text-xs font-bold text-white disabled:opacity-50">{invoiceSaving ? <LoaderCircle size={14} className="animate-spin"/> : <CheckCircle2 size={14}/>} Confirm and save invoice</button></div>
            </div>}
            <div className="mt-5 border-t border-slate-100 pt-4"><div className="flex items-center justify-between"><p className="text-xs font-bold text-slate-800">Confirmed supplier invoices</p><span className="text-[10px] text-slate-500">{confirmedInvoices.length} records</span></div>{confirmedInvoices.length === 0 ? <p className="mt-2 rounded-lg bg-slate-50 p-3 text-[11px] text-slate-500">No invoices recorded yet. Upload an invoice to start building purchase history.</p> : <div className="mt-2 max-h-40 space-y-2 overflow-y-auto">{confirmedInvoices.slice(0, 5).map((entry) => <div key={entry.invoice_id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 p-2"><div className="min-w-0"><p className="truncate text-[11px] font-bold text-slate-800">{entry.invoice.supplier_name} · {entry.invoice.invoice_number || entry.invoice_id}</p><p className="text-[10px] text-slate-500">{entry.invoice.invoice_date || 'Date not captured'} · {entry.invoice.items.length} line items</p></div><p className="shrink-0 text-xs font-extrabold">{money(entry.invoice.total_amount || 0)}</p></div>)}</div>}</div>
          </Card>

          <Card className="p-5">
            <SectionTitle icon={PackageSearch} eyebrow="Purchase + sales intelligence" title="Product trends" right={<button onClick={() => request && loadPurchaseInsights(request.merchant_id).catch((err) => setInvoiceError(err instanceof Error ? err.message : 'Refresh failed.'))} className="text-[10px] font-bold text-sky-700">Refresh</button>}/>
            <div className="mt-3 rounded-xl bg-slate-50 p-3"><div className="flex items-center gap-2"><BrainCircuit size={15} className="text-violet-700"/><p className="text-[10px] font-extrabold uppercase tracking-wide text-violet-800">Gemma 4 31B merchant explanation</p><span className={`ml-auto rounded-full px-2 py-0.5 text-[9px] font-bold ${merchantInsights?.llm_status === 'GENERATED' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>{merchantInsights?.llm_status || 'LOADING'}</span></div><p className="mt-2 text-xs leading-relaxed text-slate-700">{merchantInsights?.llm_narrative || 'Record confirmed invoices and item-level sales to generate merchant insights.'}</p><p className="mt-2 text-[9px] text-slate-400">Model: {merchantInsights?.llm_model || 'gemma4'} · LLM explains observed facts; deterministic code calculates all numeric metrics.</p></div>
            <div className="mt-4"><p className="text-xs font-bold text-slate-800">Purchase price history</p>{!merchantInsights?.purchase_trends.length ? <p className="mt-2 rounded-lg bg-slate-50 p-3 text-[11px] text-slate-500">No confirmed line-item purchase history yet.</p> : <div className="mt-2 overflow-x-auto"><table className="w-full min-w-[380px] text-left text-[10px]"><thead className="text-slate-500"><tr><th className="py-2">Product</th><th className="py-2">Latest price</th><th className="py-2">Change</th><th className="py-2">Qty recorded</th></tr></thead><tbody>{merchantInsights.purchase_trends.map((item) => <tr key={`${item.product_name}-${item.unit}`} className="border-t border-slate-100"><td className="py-2 pr-2"><p className="font-bold text-slate-800">{item.product_name}</p><p className="text-slate-400">per {item.unit}</p></td><td className="py-2 font-semibold">{item.latest_observed_unit_price == null ? '—' : money(item.latest_observed_unit_price)}</td><td className={`py-2 font-bold ${item.price_change_pct != null && item.price_change_pct > 0 ? 'text-rose-700' : 'text-emerald-700'}`}>{item.price_change_pct == null ? '—' : `${item.price_change_pct > 0 ? '+' : ''}${item.price_change_pct}%`}</td><td className="py-2">{item.total_recorded_quantity} {item.unit}</td></tr>)}</tbody></table></div>}</div>
            <div className="mt-4 border-t border-slate-100 pt-4"><p className="text-xs font-bold text-slate-800">Capture item-level sales</p><p className="mt-1 text-[10px] text-slate-500">Use manual entry for the prototype or import POS line-item records through the API. A QR payment alone does not identify the products sold.</p><form onSubmit={recordSale} className="mt-2 grid grid-cols-2 gap-2"><input value={salesProduct} onChange={(e) => setSalesProduct(e.target.value)} required placeholder="Product name" className="col-span-2 rounded-lg border border-slate-200 px-2.5 py-2 text-xs"/><input value={salesQuantity} onChange={(e) => setSalesQuantity(e.target.value)} required type="number" min="0.001" step="0.001" placeholder="Quantity sold" className="rounded-lg border border-slate-200 px-2.5 py-2 text-xs"/><input value={salesUnit} onChange={(e) => setSalesUnit(e.target.value)} required placeholder="Unit (kg/pack)" className="rounded-lg border border-slate-200 px-2.5 py-2 text-xs"/><input value={salesPrice} onChange={(e) => setSalesPrice(e.target.value)} required type="number" min="0.01" step="0.01" placeholder="Selling price per unit ₹" className="col-span-2 rounded-lg border border-slate-200 px-2.5 py-2 text-xs"/><button disabled={salesBusy} className="col-span-2 inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-700 disabled:opacity-50">{salesBusy ? <LoaderCircle size={14} className="animate-spin"/> : <Plus size={14}/>} Record item sale</button></form></div>
            <div className="mt-4"><p className="text-xs font-bold text-slate-800">Recorded sales · last 30 days</p>{!merchantInsights?.sales_trends_30d.length ? <p className="mt-2 rounded-lg bg-slate-50 p-3 text-[11px] text-slate-500">No item-level sales captured. Demand trends will remain unavailable until POS import or manual sales entry is connected.</p> : <div className="mt-2 space-y-2">{merchantInsights.sales_trends_30d.slice(0, 4).map((item) => <div key={`${item.product_name}-${item.unit}`} className="flex items-center justify-between rounded-lg border border-slate-100 p-2"><span className="text-[11px] font-semibold text-slate-700">{item.product_name}</span><span className="text-[10px] font-bold text-slate-600">{item.quantity_sold_30d} {item.unit} sold</span></div>)}</div>}</div>
            {merchantInsights?.data_limitations && <p className="mt-4 text-[9px] leading-relaxed text-slate-400">{merchantInsights.data_limitations.join(' ')}</p>}
          </Card>
        </section>

        <footer className="flex flex-col justify-between gap-2 border-t border-slate-200 py-4 text-[10px] text-slate-400 sm:flex-row"><span>Merchant MicroSave · Hackathon demonstration prototype</span><span>All bundled collections, balances, liabilities and reserve entries are synthetic. No live Paytm, bank, Account Aggregator or investment integration.</span></footer>
      </main>
    </div>
  );
}
