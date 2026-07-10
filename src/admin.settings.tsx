import { createFileRoute, Link } from "@tanstack/react-router";
import { motion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";
import { ArrowRight, ShieldCheck, Sparkles, FileText, Wallet, ScanLine, CheckCircle2, Building2 } from "lucide-react";
import { Logo } from "@/components/yaqeen/Logo";
import { Chip, ScoreRing } from "@/components/yaqeen/primitives";
import heroImg from "@/assets/hero-khata.jpg";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Yaqeen — AI Underwriting Copilot for Pakistani Banks" },
      { name: "description", content: "Explainable SME credit decisions from khata, wallet statements, utility bills and invoices. Yaqeen is the underwriting copilot loan officers trust." },
    ],
  }),
  component: Landing,
});

function Landing() {
  return (
    <div className="min-h-screen">
      <TopBar />
      <Hero />
      <Trust />
      <StoryScene />
      <Extract />
      <Score />
      <Officer />
      <Decision />
      <CTA />
      <Footer />
    </div>
  );
}

function TopBar() {
  return (
    <div className="sticky top-0 z-40 border-b border-border/60 bg-background/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center px-6">
        <Logo />
        <nav className="ml-10 hidden items-center gap-8 text-sm text-foreground/70 md:flex">
          <a href="#how" className="hover:text-foreground">How it works</a>
          <a href="#evidence" className="hover:text-foreground">Evidence</a>
          <a href="#workspace" className="hover:text-foreground">Workspace</a>
          <a href="#trust" className="hover:text-foreground">Trust</a>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <Link to="/login" className="rounded-lg px-3 py-1.5 text-sm text-foreground/80 hover:bg-muted">Sign in</Link>
          <Link to="/signup" className="group inline-flex items-center gap-1.5 rounded-lg bg-navy px-3.5 py-1.5 text-sm text-paper shadow-elegant hover:opacity-95">
            Get started <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
          </Link>
        </div>
      </div>
    </div>
  );
}

function Hero() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [0, -80]);
  const o = useTransform(scrollYProgress, [0, 1], [1, 0.3]);
  return (
    <section ref={ref} className="relative overflow-hidden">
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-16 px-6 pb-24 pt-16 md:grid-cols-12 md:pt-24">
        <motion.div style={{ y, opacity: o }} className="md:col-span-6 md:pt-8">
          <Chip tone="gold" className="mb-6"><Sparkles className="h-3 w-3" /> AI Underwriting Copilot · Beta</Chip>
          <h1 className="font-serif text-5xl leading-[1.02] tracking-tight md:text-[68px]">
            Turn a handwritten <span className="italic text-navy-soft">khata</span> into an underwriting decision.
          </h1>
          <p className="mt-6 max-w-xl text-lg text-muted-foreground">
            Yaqeen reads the evidence Pakistani SMEs actually keep — ledgers, Easypaisa, JazzCash, utility bills — and gives loan officers explainable credit decisions in minutes, not weeks.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link to="/signup" className="group inline-flex items-center gap-2 rounded-xl bg-navy px-5 py-3 text-paper shadow-lift hover:opacity-95">
              Get started <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
            </Link>
            <Link to="/login" className="rounded-xl border border-border bg-card/60 px-5 py-3 text-sm hover:bg-muted">Sign in</Link>
          </div>
          <div className="mt-10 flex items-center gap-6 text-xs text-muted-foreground">
            <div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4" /> SBP-aligned controls</div>
            <div className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4" /> Human-in-the-loop</div>
          </div>
        </motion.div>

        <div className="md:col-span-6">
          <HeroVisual />
        </div>
      </div>
    </section>
  );
}

function HeroVisual() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [30, -30]);
  const rot = useTransform(scrollYProgress, [0, 1], [-1.5, 1.5]);
  return (
    <div ref={ref} className="relative">
      <motion.div style={{ y, rotate: rot }} className="relative overflow-hidden rounded-3xl border border-border shadow-lift">
        <img
          src={heroImg}
          alt="Handwritten Urdu khata ledger beside a Yaqeen dashboard on a smartphone showing a credit score"
          width={1408}
          height={1200}
          className="block h-auto w-full object-cover"
        />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/25 via-transparent to-transparent" />
      </motion.div>
      <motion.div
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
        className="absolute -left-4 bottom-6 hidden md:block"
      >
        <div className="paper-card px-4 py-3 shadow-lift backdrop-blur">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Extracted</div>
          <div className="font-serif text-sm">March revenue · PKR 486,000</div>
          <div className="mt-1 text-[11px] text-sage">94% ledger–wallet match</div>
        </div>
      </motion.div>
      <motion.div
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}
        className="absolute -right-4 top-8 hidden md:block"
      >
        <div className="paper-card px-4 py-3 shadow-lift backdrop-blur">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Yaqeen Score</div>
          <div className="font-serif text-lg text-navy">742 · Well-qualified</div>
        </div>
      </motion.div>
    </div>
  );
}

function Trust() {
  const banks = ["Bank Alfa", "Meezan Trust", "HBL Nexus", "UBL Sarmaya", "JS Growth", "Askari SME"];
  return (
    <section id="trust" className="border-y border-border/60 bg-paper-deep/40">
      <div className="mx-auto max-w-7xl px-6 py-10">
        <div className="text-center text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Pilots with tier-1 Pakistani banks</div>
        <div className="mt-6 grid grid-cols-2 gap-6 opacity-70 md:grid-cols-6">
          {banks.map((b) => (
            <div key={b} className="text-center font-serif text-lg text-navy/70">{b}</div>
          ))}
        </div>
      </div>
    </section>
  );
}

function StoryScene() {
  const items = [
    { icon: <FileText className="h-4 w-4" />, t: "Ingest", b: "Applicant uploads khata, wallet statements, bills and invoices — from phone or shop counter." },
    { icon: <ScanLine className="h-4 w-4" />, t: "Extract", b: "Yaqeen OCR reads Urdu/English handwriting and structures every line into a ledger." },
    { icon: <Wallet className="h-4 w-4" />, t: "Cross-validate", b: "Wallet inflows, utility usage and supplier invoices are triangulated against the ledger." },
    { icon: <Sparkles className="h-4 w-4" />, t: "Score", b: "A Yaqeen Score is assembled with a full evidence trail — no black boxes." },
  ];
  return (
    <section id="how" className="mx-auto max-w-7xl px-6 py-28">
      <div className="grid gap-12 md:grid-cols-12">
        <div className="md:col-span-5">
          <div className="text-xs uppercase tracking-[0.22em] text-muted-foreground">How it works</div>
          <h2 className="mt-3 font-serif text-4xl leading-tight md:text-5xl">Every number, traceable to the page it came from.</h2>
          <p className="mt-4 max-w-lg text-muted-foreground">Underwriting is a story about evidence. Yaqeen keeps that story intact — every extracted figure links back to the exact page, transaction, or invoice it originated from.</p>
        </div>
        <div className="md:col-span-7">
          <div className="grid gap-4 sm:grid-cols-2">
            {items.map((it, i) => (
              <motion.div key={it.t} initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.08 }}
                className="paper-card p-5">
                <div className="flex items-center gap-2 text-navy">
                  <span className="grid h-8 w-8 place-items-center rounded-md bg-gold-soft/60 text-navy">{it.icon}</span>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">Step {i + 1}</div>
                </div>
                <div className="mt-3 font-serif text-xl">{it.t}</div>
                <p className="mt-1 text-sm text-muted-foreground">{it.b}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function Extract() {
  return (
    <section id="evidence" className="border-y border-border/60 bg-paper-deep/40">
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-12 px-6 py-24 md:grid-cols-2 md:items-center">
        <div>
          <Chip tone="navy" className="mb-4">Evidence-first</Chip>
          <h2 className="font-serif text-4xl leading-tight md:text-5xl">Structured tables born from handwritten pages.</h2>
          <p className="mt-4 text-muted-foreground">Yaqeen doesn't just OCR. It parses semantics — supplier names, item lines, udhaar entries — and reconciles them across every document.</p>
          <ul className="mt-6 space-y-3 text-sm">
            {["Handles Urdu, Roman Urdu, English", "Auto-detects Easypaisa & JazzCash statement formats", "Flags mismatched business names across evidence", "Suggests missing supporting documents"].map((l) => (
              <li key={l} className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 text-sage" />{l}</li>
            ))}
          </ul>
        </div>
        <div className="paper-card overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-4 py-2 text-xs text-muted-foreground">
            <span>Extracted · Al-Madina Kiryana · March 2024</span>
            <Chip tone="sage">Reconciled</Chip>
          </div>
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
              <tr><th className="px-4 py-2">Date</th><th className="px-4 py-2">Source</th><th className="px-4 py-2">Description</th><th className="px-4 py-2 text-right">Amount</th></tr>
            </thead>
            <tbody className="[&_tr]:border-t [&_tr]:border-border/60">
              {[
                ["03/03","Khata p.4","Cash sale · 8,650 PKR", "8,650"],
                ["07/03","Invoice #221","Ghee supplier payout","-22,000"],
                ["12/03","K-Electric","Shop electricity","-4,180"],
                ["19/03","Easypaisa","Wholesale inflow","41,000"],
                ["23/03","JazzCash","Supplier payout","-18,400"],
                ["28/03","Khata p.7","Cash sale","6,150"],
              ].map((r) => (
                <tr key={r[0]+r[2]} className="text-navy">
                  <td className="px-4 py-2 text-muted-foreground">{r[0]}</td>
                  <td className="px-4 py-2"><Chip tone="muted">{r[1]}</Chip></td>
                  <td className="px-4 py-2">{r[2]}</td>
                  <td className="px-4 py-2 text-right font-mono">{r[3]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function Score() {
  return (
    <section className="mx-auto max-w-7xl px-6 py-28">
      <div className="grid grid-cols-1 gap-12 md:grid-cols-2 md:items-center">
        <div className="order-2 md:order-1 paper-card p-8">
          <div className="flex items-center gap-8">
            <ScoreRing value={742} />
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">Yaqeen Score</div>
              <div className="mt-1 font-serif text-3xl">Well-qualified</div>
              <div className="mt-1 text-sm text-muted-foreground">Consistent revenue, low volatility, matched evidence.</div>
              <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <Contribution label="Cash-flow stability" pct={86} />
                <Contribution label="Evidence coverage" pct={92} />
                <Contribution label="Ledger–wallet match" pct={94} />
                <Contribution label="Filing history" pct={64} />
              </div>
            </div>
          </div>
        </div>
        <div className="order-1 md:order-2">
          <Chip tone="gold" className="mb-4">Explainable score</Chip>
          <h2 className="font-serif text-4xl leading-tight md:text-5xl">A credit score that shows its work.</h2>
          <p className="mt-4 max-w-lg text-muted-foreground">Every contribution to the Yaqeen Score is traceable, weighted, and reversible — so officers, auditors and regulators can follow the reasoning end to end.</p>
        </div>
      </div>
    </section>
  );
}

function Contribution({ label, pct }: { label: string; pct: number }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground"><span>{label}</span><span>{pct}%</span></div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full bg-navy" style={{ width: pct + "%" }} /></div>
    </div>
  );
}

function Officer() {
  return (
    <section id="workspace" className="border-t border-border/60 bg-paper-deep/40">
      <div className="mx-auto max-w-7xl px-6 py-28">
        <div className="mb-12 max-w-2xl">
          <Chip tone="navy" className="mb-3">Officer workspace</Chip>
          <h2 className="font-serif text-4xl leading-tight md:text-5xl">Built for the officer who signs the decision.</h2>
          <p className="mt-3 text-muted-foreground">A Bloomberg-terminal density paired with Mercury calm. Every application, evidence and decision in one canvas.</p>
        </div>
        <div className="paper-card overflow-hidden">
          <div className="grid grid-cols-12">
            <div className="col-span-3 border-r border-border bg-sidebar/60 p-4">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Queue · 12</div>
              <ul className="mt-3 space-y-2 text-sm">
                {["Al-Madina Kiryana","Bismillah Fabrics","Rehman Electronics","Butt Sweets","Iqbal Tailors"].map((n,i)=>(
                  <li key={n} className={"flex items-center justify-between rounded-md px-2 py-1.5 " + (i===0?"bg-navy text-paper":"hover:bg-muted")}>
                    <span className="truncate">{n}</span>
                    <span className="text-[10px] opacity-70">PKR {(400 + i*180)}K</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="col-span-6 p-5">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs text-muted-foreground">YQN-01042 · Karachi</div>
                  <div className="font-serif text-xl">Al-Madina Kiryana</div>
                </div>
                <Chip tone="gold">In Review</Chip>
              </div>
              <div className="mt-4 grid grid-cols-4 gap-3">
                {[["Revenue","486K"],["Margin","35.8%"],["Runway","4.6 mo"],["Requested","1.2M"]].map(([l,v])=>(
                  <div key={l} className="rounded-lg border border-border p-3">
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{l}</div>
                    <div className="mt-1 font-serif text-base">{v}</div>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-lg border border-border p-3">
                <div className="text-xs text-muted-foreground">AI Underwriting Report — excerpt</div>
                <p className="mt-1 text-sm text-navy">
                  Cash-flow is consistent across ledger and Easypaisa (94% match). Supplier concentration risk moderate — 42% of outflows to a single supplier. Recommend approval with covenant on monthly reporting.
                </p>
              </div>
            </div>
            <div className="col-span-3 border-l border-border p-4">
              <ScoreRing value={742} size={140} />
              <div className="mt-3 space-y-2">
                <button className="w-full rounded-md bg-sage/90 py-2 text-sm text-paper">Approve</button>
                <button className="w-full rounded-md border border-border py-2 text-sm">Request docs</button>
                <button className="w-full rounded-md border border-border py-2 text-sm text-destructive">Reject</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Decision() {
  return (
    <section className="mx-auto max-w-7xl px-6 py-28">
      <div className="grid grid-cols-1 gap-10 md:grid-cols-3">
        {[
          { t: "For Applicants", b: "Guided upload. Camera-first. Feedback while you shoot the page.", to: "/signup" },
          { t: "For Loan Officers", b: "Evidence, score and audit trail in one focused canvas.", to: "/login" },
          { t: "For Administrators", b: "Portfolio, model usage, permissions and audit — one pane.", to: "/login" },
        ].map((c) => (
          <Link key={c.t} to={c.to} className="paper-card group p-6 transition hover:shadow-lift">
            <Building2 className="h-5 w-5 text-navy" />
            <div className="mt-4 font-serif text-2xl">{c.t}</div>
            <p className="mt-2 text-sm text-muted-foreground">{c.b}</p>
            <div className="mt-4 inline-flex items-center gap-1 text-sm text-navy">Open workspace <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" /></div>
          </Link>
        ))}
      </div>
    </section>
  );
}

function CTA() {
  return (
    <section className="mx-auto max-w-6xl px-6 pb-28">
      <div className="ink-gradient relative overflow-hidden rounded-3xl p-12 text-paper md:p-16">
        <div className="absolute -right-20 -top-20 h-72 w-72 rounded-full bg-gold/30 blur-3xl" />
        <div className="relative">
          <h3 className="font-serif text-4xl md:text-5xl">Underwriting the 90% that banks miss.</h3>
          <p className="mt-4 max-w-xl text-paper/80">Yaqeen brings evidence-based credit to the SMEs that keep Pakistan running — and to the officers who fund them.</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/signup" className="rounded-xl bg-gold px-5 py-3 text-navy shadow-lift hover:opacity-95">Get started</Link>
            <Link to="/login" className="rounded-xl border border-paper/30 px-5 py-3 text-paper hover:bg-paper/10">Sign in</Link>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-border/60">
      <div className="mx-auto flex max-w-7xl flex-col items-start gap-4 px-6 py-10 text-sm text-muted-foreground md:flex-row md:items-center">
        <Logo />
        <div className="md:ml-6">© {new Date().getFullYear()} Yaqeen Underwriting Systems · Karachi</div>
        <div className="md:ml-auto flex gap-5">
          <a href="#" className="hover:text-foreground">Security</a>
          <a href="#" className="hover:text-foreground">Compliance</a>
          <a href="#" className="hover:text-foreground">Contact</a>
        </div>
      </div>
    </footer>
  );
}
