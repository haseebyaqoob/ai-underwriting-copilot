import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { SectionHeader } from "@/components/yaqeen/primitives";
import { useState } from "react";
import { useCreateApplication, useDocumentQueue, useSubmitApplication, useUploadDocument } from "@/lib/yaqeen-queries";
import { UploadCloud, CheckCircle2 } from "lucide-react";

export const Route = createFileRoute("/applicant/applications/new")({ component: NewApp });

const steps = ["Business", "Loan", "Evidence", "Review"];

interface FormState {
  businessName: string;
  businessType: string;
  ownerName: string;
  cnicNumber: string;
  city: string;
  yearsOperating: string;
  employeeCount: string;
  registrationStatus: "registered" | "unregistered";
  ntn: string;
  strn: string;
  amountPkr: string;
  tenorMonths: string;
  purpose: string;
  preferredRepayment: string;
  monthlyEstimatedRevenuePkr: string;
  monthlyEstimatedExpensesPkr: string;
}

const EMPTY: FormState = {
  businessName: "", businessType: "", ownerName: "", cnicNumber: "", city: "",
  yearsOperating: "", employeeCount: "", registrationStatus: "unregistered", ntn: "", strn: "",
  amountPkr: "", tenorMonths: "", purpose: "", preferredRepayment: "",
  monthlyEstimatedRevenuePkr: "", monthlyEstimatedExpensesPkr: "",
};

function NewApp() {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [applicationId, setApplicationId] = useState<string | null>(null);
  const [displayId, setDisplayId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const nav = useNavigate();

  const createMutation = useCreateApplication();
  const submitMutation = useSubmitApplication();
  const uploadMutation = useUploadDocument();
  const { data: queue } = useDocumentQueue(applicationId ?? undefined, { enabled: !!applicationId });

  const set = (k: keyof FormState) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const goNext = async () => {
    setErr(null);
    if (step === 0) {
      if (!form.businessName || !form.businessType || !form.ownerName || !form.city || !form.yearsOperating || !form.employeeCount) {
        setErr("Please complete every field in this step.");
        return;
      }
      if (form.cnicNumber && !/^\d{5}-?\d{7}-?\d{1}$/.test(form.cnicNumber.replace(/\s/g, ""))) {
        setErr("CNIC should be 13 digits (e.g. 42101-1234567-1).");
        return;
      }
      if (form.ntn && !/^\d{7}(-\d)?$/.test(form.ntn.trim())) {
        setErr("NTN should be 7 digits (optionally with a check digit, e.g. 1234567-8).");
        return;
      }
      if (form.strn && !/^\d{2}-\d{2}-\d{4}-\d{3}-\d{2}$|^\d{13}$/.test(form.strn.trim())) {
        setErr("STRN doesn't look right — check the format on your registration certificate.");
        return;
      }
      setStep(1);
      return;
    }
    if (step === 1) {
      if (!form.amountPkr || !form.tenorMonths || !form.purpose || !form.preferredRepayment) {
        setErr("Please complete every field in this step.");
        return;
      }
      if (Number(form.amountPkr) <= 0) {
        setErr("Requested amount must be greater than zero.");
        return;
      }
      if (Number(form.tenorMonths) < 1 || Number(form.tenorMonths) > 120) {
        setErr("Loan tenure should be between 1 and 120 months.");
        return;
      }
      if (form.monthlyEstimatedRevenuePkr && form.monthlyEstimatedExpensesPkr && Number(form.monthlyEstimatedExpensesPkr) > Number(form.monthlyEstimatedRevenuePkr) * 3) {
        setErr("Estimated expenses look unusually high compared to estimated revenue — please double-check.");
        return;
      }
      // Creates the application in DRAFT (see app/services/state_machine.py) --
      // it isn't visible to any officer until the applicant explicitly
      // submits it in step 2 below. Evidence/CNIC upload targets this
      // real application_id while it's still a draft.
      try {
        const created = await createMutation.mutateAsync({
          businessName: form.businessName,
          businessType: form.businessType,
          ownerName: form.ownerName,
          city: form.city,
          yearsOperating: Number(form.yearsOperating),
          employeeCount: Number(form.employeeCount),
          registrationStatus: form.registrationStatus,
          ntn: form.ntn || null,
          strn: form.strn || null,
          amountPkr: Number(form.amountPkr),
          tenorMonths: Number(form.tenorMonths),
          purpose: form.purpose,
          preferredRepayment: form.preferredRepayment,
          cnicNumber: form.cnicNumber || null,
          monthlyEstimatedRevenuePkr: form.monthlyEstimatedRevenuePkr ? Number(form.monthlyEstimatedRevenuePkr) : null,
          monthlyEstimatedExpensesPkr: form.monthlyEstimatedExpensesPkr ? Number(form.monthlyEstimatedExpensesPkr) : null,
        });
        setApplicationId(created.id);
        setDisplayId(created.displayId);
        setStep(2);
      } catch (e) {
        setErr((e as Error).message);
      }
      return;
    }
    if (step === 2) {
      setStep(3);
      return;
    }
    setStep(Math.min(steps.length - 1, step + 1));
  };

  const handleSubmit = async () => {
    if (!applicationId) return;
    setErr(null);
    try {
      await submitMutation.mutateAsync(applicationId);
      // AI Processing page redesign: submitting no longer just flips a
      // flag in this wizard -- it hands off to a dedicated page that
      // shows real per-step progress (see workflow_stage_service.py /
      // routes/applicant.applications.$id.processing.tsx) rather than
      // an instant "Submitted" confirmation, per the product brief.
      nav({ to: "/applicant/applications/$id/processing", params: { id: applicationId } });
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Start" title="New loan application" sub="It takes about 6 minutes. Yaqeen guides you through each step." />

      <div className="flex items-center gap-2">
        {steps.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div className={`grid h-7 w-7 place-items-center rounded-full text-xs ${i <= step ? "bg-navy text-paper" : "bg-muted text-muted-foreground"}`}>{i + 1}</div>
            <span className={i <= step ? "text-foreground" : "text-muted-foreground"}>{s}</span>
            {i < steps.length - 1 && <div className={`mx-2 h-px w-10 ${i < step ? "bg-navy" : "bg-border"}`} />}
          </div>
        ))}
      </div>

      <div className="paper-card p-6">
        {step === 0 && (
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Business name" placeholder="e.g. Al-Madina Kiryana" value={form.businessName} onChange={set("businessName")} />
            <Field label="Business type" placeholder="Kiryana / Retail / Fabrics" value={form.businessType} onChange={set("businessType")} />
            <Field label="Registered owner (CNIC name)" placeholder="Adnan Rehman" value={form.ownerName} onChange={set("ownerName")} />
            <Field label="CNIC number" placeholder="42101-1234567-1" value={form.cnicNumber} onChange={set("cnicNumber")} hint="13 digits, with or without dashes. You can add the CNIC photo in the Evidence step." />
            <Field label="City" placeholder="Karachi" value={form.city} onChange={set("city")} />
            <Field label="Years in operation" placeholder="4" type="number" value={form.yearsOperating} onChange={set("yearsOperating")} />
            <Field label="Employees" placeholder="3" type="number" value={form.employeeCount} onChange={set("employeeCount")} />

            <div className="md:col-span-2 mt-2 border-t border-border/60 pt-4">
              <span className="mb-2 block text-xs font-medium text-foreground/80">Business registration status</span>
              <div className="flex gap-3">
                {(["unregistered", "registered"] as const).map((opt) => (
                  <label key={opt} className={`flex-1 cursor-pointer rounded-lg border px-4 py-3 text-sm ${form.registrationStatus === opt ? "border-navy bg-navy/5" : "border-border"}`}>
                    <input type="radio" name="registrationStatus" className="mr-2" checked={form.registrationStatus === opt} onChange={() => set("registrationStatus")(opt)} />
                    {opt === "registered" ? "Registered business" : "Unregistered / informal business"}
                  </label>
                ))}
              </div>
              <p className="mt-1.5 text-[11px] text-muted-foreground">
                Not registered yet? That's fine — Yaqeen supports traditional and alternative evidence either way. Registration doesn't affect eligibility.
              </p>
            </div>
            <Field label="NTN (optional)" placeholder="1234567-8" value={form.ntn} onChange={set("ntn")} />
            <Field label="STRN (optional)" placeholder="03-11-1234-123-45" value={form.strn} onChange={set("strn")} />
          </div>
        )}
        {step === 1 && (
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Requested amount (PKR)" placeholder="1200000" type="number" value={form.amountPkr} onChange={set("amountPkr")} />
            <Field label="Loan tenure (months)" placeholder="18" type="number" value={form.tenorMonths} onChange={set("tenorMonths")} />
            <Field label="Purpose" placeholder="Inventory expansion" value={form.purpose} onChange={set("purpose")} />
            <Field label="Repayment preference" placeholder="Monthly · Easypaisa" value={form.preferredRepayment} onChange={set("preferredRepayment")} />

            <div className="md:col-span-2 mt-2 border-t border-border/60 pt-4">
              <span className="mb-1 block text-xs font-medium text-foreground/80">Your own estimate (optional)</span>
              <p className="mb-3 text-[11px] text-muted-foreground">
                Not sure of exact numbers? Leave these blank — Yaqeen will estimate your revenue and expenses from the evidence you upload next.
              </p>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Monthly estimated revenue (PKR)" placeholder="350000" type="number" value={form.monthlyEstimatedRevenuePkr} onChange={set("monthlyEstimatedRevenuePkr")} />
                <Field label="Monthly estimated expenses (PKR)" placeholder="220000" type="number" value={form.monthlyEstimatedExpensesPkr} onChange={set("monthlyEstimatedExpensesPkr")} />
              </div>
            </div>
          </div>
        )}
        {step === 2 && applicationId && (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground">
              Application <span className="font-mono text-foreground">{displayId}</span> is a draft. Add your CNIC photo and a document or two now — you can add more evidence types (utility bills, wallet statements, business photos, etc) any time from the full{" "}
              <a href="/applicant/upload" className="underline underline-offset-4">Evidence Checklist</a>.
            </div>
            <EvidenceUploader applicationId={applicationId} subtype="cnic_front" label="CNIC front" mutation={uploadMutation} />
            <EvidenceUploader applicationId={applicationId} subtype="cnic_back" label="CNIC back" mutation={uploadMutation} />
            <EvidenceUploader applicationId={applicationId} subtype="khata" label="Khata / ledger" mutation={uploadMutation} />
            <EvidenceUploader applicationId={applicationId} subtype="electricity_bill" label="Electricity bill" mutation={uploadMutation} />
            {queue && queue.items.length > 0 && (
              <ul className="divide-y divide-border/60 rounded-lg border border-border">
                {queue.items.map((it) => (
                  <li key={it.documentVersionId} className="flex items-center justify-between px-4 py-2 text-sm">
                    <span className="truncate">{it.originalFilename} · {it.type}</span>
                    <span className="text-xs text-muted-foreground">{it.note}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {step === 3 && (
          <div className="space-y-5">
            <div className="text-sm text-muted-foreground">Review everything before you submit. Officers can't see this application until you submit it.</div>
            <ReviewSection title="Business">
              <ReviewRow label="Business name" value={form.businessName} />
              <ReviewRow label="Type" value={form.businessType} />
              <ReviewRow label="Owner (CNIC name)" value={form.ownerName} />
              <ReviewRow label="City" value={form.city} />
              <ReviewRow label="Years operating / employees" value={`${form.yearsOperating} yrs · ${form.employeeCount} employees`} />
              <ReviewRow label="Registration" value={form.registrationStatus === "registered" ? "Registered" : "Unregistered"} />
              {(form.ntn || form.strn) && <ReviewRow label="NTN / STRN" value={`${form.ntn || "—"} / ${form.strn || "—"}`} />}
            </ReviewSection>
            <ReviewSection title="Loan">
              <ReviewRow label="Requested amount" value={`PKR ${Number(form.amountPkr).toLocaleString()}`} />
              <ReviewRow label="Tenure" value={`${form.tenorMonths} months`} />
              <ReviewRow label="Purpose" value={form.purpose} />
              <ReviewRow label="Repayment preference" value={form.preferredRepayment} />
              {(form.monthlyEstimatedRevenuePkr || form.monthlyEstimatedExpensesPkr) && (
                <ReviewRow label="Your estimate" value={`Revenue PKR ${form.monthlyEstimatedRevenuePkr || "—"} · Expenses PKR ${form.monthlyEstimatedExpensesPkr || "—"}`} />
              )}
            </ReviewSection>
            <ReviewSection title="Evidence">
              {queue && queue.items.length > 0 ? (
                <span className="text-sm text-foreground">{queue.items.length} document(s) uploaded so far.</span>
              ) : (
                <span className="text-sm text-clay">No evidence uploaded yet — you can still submit and add evidence afterward, but a faster decision needs at least your CNIC and shop photos.</span>
              )}
            </ReviewSection>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <CheckCircle2 className="h-4 w-4 text-sage" /> By submitting, you confirm the information above is accurate to the best of your knowledge.
            </div>
          </div>
        )}

        {err && <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">{err}</div>}
      </div>

      <div className="flex justify-between">
        <button className="rounded-lg border border-border px-4 py-2 text-sm disabled:opacity-40" disabled={step === 0} onClick={() => setStep(Math.max(0, step - 1))}>Back</button>
        {step < 3 ? (
          <button className="rounded-lg bg-navy px-4 py-2 text-sm text-paper disabled:opacity-60" disabled={createMutation.isPending} onClick={goNext}>
            {createMutation.isPending ? "Creating…" : step === 1 ? "Create draft →" : "Continue"}
          </button>
        ) : (
          <button className="rounded-lg bg-navy px-4 py-2 text-sm text-paper disabled:opacity-60" disabled={submitMutation.isPending} onClick={handleSubmit}>
            {submitMutation.isPending ? "Submitting…" : "Submit application →"}
          </button>
        )}
      </div>
    </div>
  );
}

function ReviewSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border/70 p-4">
      <div className="mb-2 font-serif text-sm text-foreground">{title}</div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-foreground">{value || "—"}</span>
    </div>
  );
}

function Field({ label, placeholder, value, onChange, type = "text", hint }: { label: string; placeholder?: string; value: string; onChange: (v: string) => void; type?: string; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-foreground/80">{label}</span>
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-input bg-card/70 px-3 py-2.5 text-sm outline-none focus:border-navy focus:ring-2 focus:ring-gold/40"
      />
      {hint && <span className="mt-1 block text-[11px] text-muted-foreground">{hint}</span>}
    </label>
  );
}

function EvidenceUploader({ applicationId, subtype, label, mutation }: {
  applicationId: string;
  subtype: string;
  label: string;
  mutation: ReturnType<typeof useUploadDocument>;
}) {
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">("idle");

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setStatus("uploading");
    try {
      await mutation.mutateAsync({ applicationId, documentType: "other", subtype, file });
      setStatus("done");
    } catch {
      setStatus("error");
    }
  };

  return (
    <label className="flex cursor-pointer items-center justify-between rounded-lg border border-dashed border-border p-3 hover:bg-muted/40">
      <span className="flex items-center gap-2 text-sm"><UploadCloud className="h-4 w-4 text-navy" /> {label}</span>
      <span className="text-xs text-muted-foreground">
        {status === "idle" && "PDF, JPG, PNG, HEIC · up to 25MB"}
        {status === "uploading" && "Uploading…"}
        {status === "done" && "Uploaded ✓"}
        {status === "error" && "Upload failed — try again"}
      </span>
      <input type="file" accept=".pdf,.jpg,.jpeg,.png,.heic,.heif" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
    </label>
  );
}
