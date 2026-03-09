import { useState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import {
  MessageCircle, Calendar, Users, BarChart3, ArrowRight,
  CheckCircle2, Star, Zap, Globe, Shield, X as XIcon,
} from "lucide-react";
import { PLANS, PLAN_KEYS, COMPARISON_FEATURES, type PlanKey } from "@/lib/plans";

/* ─── NAVBAR ─── */
const Navbar = () => (
  <nav className="fixed top-0 z-50 w-full border-b bg-background/80 backdrop-blur-md">
    <div className="container mx-auto flex h-16 items-center justify-between px-4">
      <a href="/" className="flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-foreground">
          <MessageCircle className="h-4 w-4 text-background" />
        </div>
        <span className="text-sm font-semibold tracking-tight">LocalAI</span>
      </a>
      <div className="hidden items-center gap-8 md:flex">
        <a href="#features" className="text-sm text-muted-foreground transition-colors hover:text-foreground">Features</a>
        <a href="#how-it-works" className="text-sm text-muted-foreground transition-colors hover:text-foreground">How It Works</a>
        <a href="#pricing" className="text-sm text-muted-foreground transition-colors hover:text-foreground">Pricing</a>
      </div>
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <a href="/auth">Log In</a>
        </Button>
        <Button size="sm" asChild>
          <a href="/auth?signup=true">Sign Up</a>
        </Button>
      </div>
    </div>
  </nav>
);

/* ─── HERO ─── */
const Hero = () => (
  <section className="relative overflow-hidden pt-32 pb-24">
    <div className="absolute inset-0 dot-grid opacity-40" />
    <div className="container relative mx-auto px-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mx-auto max-w-3xl text-center"
      >
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-blue" />
          AI-Powered Front Desk
        </div>
        <h1 className="mb-6 text-5xl font-bold leading-[1.08] tracking-tight sm:text-6xl lg:text-7xl">
          Your 24/7 AI Receptionist
        </h1>
        <p className="mx-auto mb-10 max-w-xl text-lg text-muted-foreground">
          Answer FAQs, capture leads, and book appointments automatically.
          Embed a smart chat widget on your site and never miss a customer again.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-4">
          <Button size="xl" asChild>
            <a href="/auth?signup=true">
              Get Started <ArrowRight className="ml-1 h-4 w-4" />
            </a>
          </Button>
          <Button variant="outline" size="xl" asChild>
            <a href="#demo">Live Demo</a>
          </Button>
        </div>
        <div className="mt-8 flex items-center justify-center gap-6 text-sm text-muted-foreground">
          <span>No credit card required</span>
          <span className="h-1 w-1 rounded-full bg-border" />
          <span>5-minute setup</span>
        </div>
      </motion.div>
    </div>
  </section>
);

/* ─── FEATURES ─── */
const features = [
  { icon: MessageCircle, title: "Smart Chat Widget", description: "Embed a branded chat widget on your site. Handles FAQs, captures leads, and books appointments 24/7." },
  { icon: Calendar, title: "Calendar Integration", description: "Connects to Google Calendar. Shows real availability, respects buffer times, and creates events instantly." },
  { icon: Users, title: "Lead Capture", description: "Automatically collects contact info, service interest, and urgency. Routes hot leads to your inbox." },
  { icon: BarChart3, title: "Analytics Dashboard", description: "Track leads captured, appointments booked, peak hours, and estimated revenue at a glance." },
];

const Features = () => (
  <section className="border-t py-24" id="features">
    <div className="container mx-auto px-4">
      <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="mx-auto mb-16 max-w-2xl text-center">
        <h2 className="mb-4 text-3xl font-bold tracking-tight sm:text-4xl">Everything Your Front Desk Needs</h2>
        <p className="text-muted-foreground">From answering common questions to booking appointments, your AI receptionist handles it all.</p>
      </motion.div>
      <div className="grid gap-px overflow-hidden rounded-lg border bg-border md:grid-cols-2 lg:grid-cols-4">
        {features.map((f, i) => (
          <motion.div
            key={f.title}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.1 }}
            className="bg-card p-8 transition-colors hover:bg-secondary/50"
          >
            <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-md border">
              <f.icon className="h-5 w-5" />
            </div>
            <h3 className="mb-2 font-semibold">{f.title}</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">{f.description}</p>
          </motion.div>
        ))}
      </div>
    </div>
  </section>
);

/* ─── HOW IT WORKS ─── */
const howSteps = [
  { num: "01", title: "Sign Up & Configure", desc: "Create your account, add services, FAQs, and business hours in minutes.", icon: Zap },
  { num: "02", title: "Embed the Widget", desc: "Copy a single line of code and paste it into your website. Works on any platform.", icon: Globe },
  { num: "03", title: "Start Capturing Leads", desc: "Your AI receptionist answers questions, books appointments, and captures leads 24/7.", icon: Shield },
];

const HowItWorks = () => (
  <section className="border-t py-24" id="how-it-works">
    <div className="container mx-auto px-4">
      <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="mx-auto mb-16 max-w-2xl text-center">
        <h2 className="mb-4 text-3xl font-bold tracking-tight sm:text-4xl">Up and Running in 3 Steps</h2>
        <p className="text-muted-foreground">No coding required. No complicated setup. Just results.</p>
      </motion.div>
      <div className="mx-auto grid max-w-4xl gap-12 md:grid-cols-3">
        {howSteps.map((s, i) => (
          <motion.div key={s.num} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.15 }} className="text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full border-2 border-foreground text-lg font-bold">
              {s.num}
            </div>
            <h3 className="mb-2 font-semibold">{s.title}</h3>
            <p className="text-sm text-muted-foreground">{s.desc}</p>
          </motion.div>
        ))}
      </div>
    </div>
  </section>
);

/* ─── TESTIMONIALS ─── */
const testimonials = [
  { name: "Sarah M.", role: "Owner, Glow Wellness", text: "We booked 40% more appointments in the first month. The widget basically pays for itself.", rating: 5 },
  { name: "Dr. James K.", role: "Dental Practice", text: "Patients love being able to ask questions at midnight. Our front desk staff can now focus on in-office care.", rating: 5 },
  { name: "Lisa T.", role: "Hair Studio Owner", text: "Setup took 5 minutes. My clients can book anytime and I get instant lead notifications.", rating: 5 },
];

const Testimonials = () => (
  <section className="border-t py-24" id="testimonials">
    <div className="container mx-auto px-4">
      <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="mx-auto mb-16 max-w-2xl text-center">
        <h2 className="mb-4 text-3xl font-bold tracking-tight sm:text-4xl">Loved by Local Businesses</h2>
        <p className="text-muted-foreground">See what business owners are saying about their AI receptionist.</p>
      </motion.div>
      <div className="mx-auto grid max-w-5xl gap-6 md:grid-cols-3">
        {testimonials.map((t, i) => (
          <motion.div key={t.name} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.1 }} className="rounded-lg border p-6">
            <div className="mb-3 flex gap-0.5">
              {Array.from({ length: t.rating }).map((_, j) => (
                <Star key={j} className="h-4 w-4 fill-foreground text-foreground" />
              ))}
            </div>
            <p className="mb-4 text-sm text-muted-foreground leading-relaxed">"{t.text}"</p>
            <div>
              <p className="text-sm font-medium">{t.name}</p>
              <p className="text-xs text-muted-foreground">{t.role}</p>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  </section>
);

/* ─── PRICING ─── */
const Pricing = () => {
  const [annual, setAnnual] = useState(false);

  return (
    <section className="border-t py-24" id="pricing">
      <div className="container mx-auto px-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mx-auto mb-12 max-w-2xl text-center"
        >
          <h2 className="mb-4 text-3xl font-bold tracking-tight sm:text-4xl">Simple, Transparent Pricing</h2>
          <p className="text-muted-foreground mb-6">Start free. Upgrade when you're ready.</p>

          {/* Billing toggle */}
          <div className="inline-flex items-center gap-3 rounded-full border p-1">
            <button
              onClick={() => setAnnual(false)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                !annual ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Monthly
            </button>
            <button
              onClick={() => setAnnual(true)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                annual ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Annual <span className="ml-1 text-xs opacity-70">Save 2 months</span>
            </button>
          </div>
        </motion.div>

        {/* Plan Cards */}
        <div className="mx-auto grid max-w-5xl gap-6 md:grid-cols-3">
          {PLAN_KEYS.map((key, i) => {
            const plan = PLANS[key];
            const price = annual ? Math.round(plan.annualPrice / 12) : plan.monthlyPrice;
            return (
              <motion.div
                key={key}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className={`relative rounded-xl border p-8 transition-shadow ${
                  plan.popular
                    ? "border-foreground ring-1 ring-foreground shadow-xl scale-[1.03]"
                    : "hover:shadow-md"
                }`}
              >
                {plan.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-foreground px-4 py-1 text-xs font-semibold text-background">
                    Most Popular
                  </div>
                )}
                <h3 className="text-lg font-semibold">{plan.name}</h3>
                <p className="text-sm text-muted-foreground">{plan.description}</p>
                <div className="my-6">
                  <span className="text-5xl font-bold tracking-tight">
                    {price === 0 ? "Free" : `$${price}`}
                  </span>
                  {price > 0 && <span className="text-sm text-muted-foreground ml-1">/mo</span>}
                  {annual && plan.annualPrice > 0 && (
                    <p className="text-xs text-muted-foreground mt-1">
                      ${plan.annualPrice} billed annually
                    </p>
                  )}
                </div>

                {/* Limits highlight */}
                <div className="mb-4 rounded-md bg-secondary/50 p-3 space-y-1">
                  <p className="text-xs font-medium">
                    {plan.limits.chats === null ? "Unlimited chats" : `${plan.limits.chats} chats / mo`}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {plan.limits.leads === null ? "Unlimited leads" : `${plan.limits.leads} leads / mo`}
                    {" · "}
                    {plan.limits.businesses} business{plan.limits.businesses > 1 ? "es" : ""}
                  </p>
                </div>

                <ul className="mb-6 space-y-2.5 text-sm">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-muted-foreground">
                      <CheckCircle2 className="h-4 w-4 text-foreground shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Button variant={plan.popular ? "default" : "outline"} className="w-full" size="lg" asChild>
                  <a href="/auth?signup=true">{plan.cta}</a>
                </Button>
              </motion.div>
            );
          })}
        </div>

        {/* Feature Comparison Table */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mx-auto mt-16 max-w-4xl"
        >
          <h3 className="mb-6 text-center text-lg font-semibold">Feature Comparison</h3>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-secondary/30">
                  <th className="px-4 py-3 text-left font-medium">Feature</th>
                  {PLAN_KEYS.map((key) => (
                    <th key={key} className="px-4 py-3 text-center font-medium">{PLANS[key].name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARISON_FEATURES.map((row, i) => (
                  <tr key={row.label} className={i % 2 === 0 ? "" : "bg-secondary/20"}>
                    <td className="px-4 py-3 text-muted-foreground">{row.label}</td>
                    {(["free", "pro", "agency"] as PlanKey[]).map((key) => {
                      const val = row[key];
                      return (
                        <td key={key} className="px-4 py-3 text-center">
                          {typeof val === "boolean" ? (
                            val ? (
                              <CheckCircle2 className="mx-auto h-4 w-4 text-foreground" />
                            ) : (
                              <XIcon className="mx-auto h-4 w-4 text-muted-foreground/30" />
                            )
                          ) : (
                            <span className="font-medium">{val}</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      </div>
    </section>
  );
};

/* ─── FOOTER ─── */
const Footer = () => (
  <footer className="border-t py-8">
    <div className="container mx-auto px-4">
      <div className="flex flex-col items-center justify-between gap-4 md:flex-row">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded bg-foreground">
            <MessageCircle className="h-3 w-3 text-background" />
          </div>
          <span className="text-sm font-medium">LocalAI Receptionist</span>
        </div>
        <p className="text-sm text-muted-foreground">© 2026 LocalAI Receptionist. All rights reserved.</p>
      </div>
    </div>
  </footer>
);

export { Navbar, Hero, Features, HowItWorks, Testimonials, Pricing, Footer };
