import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessageCircle, X, Send, Calendar, HelpCircle, Clock, User, RotateCcw, Phone, Mail, Loader2, ChevronLeft, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ReactMarkdown from "react-markdown";

type Intent = "book" | "faq" | "existing" | "other" | null;
type Step = "intent" | "booking-service" | "booking-date" | "booking-slots" | "booking-form" | "booking-confirm" | "booking-calendly" | "faq-list" | "contact-options" | "conversation";

interface Message {
  id: string;
  role: "bot" | "user";
  text: string;
}

interface ServiceItem {
  id?: string;
  name: string;
  duration_minutes: number;
  price_text: string | null;
}

interface ChatWidgetProps {
  embedded?: boolean;
  botId?: string;
  businessId?: string;
  widgetToken?: string;
  businessName?: string;
  welcomeMessage?: string;
  disclaimerText?: string;
  systemPrompt?: string;
  businessPhone?: string;
  businessEmail?: string;
  businessAddress?: string;
  faqs?: { question: string; answer: string }[];
  services?: ServiceItem[];
  calendlyUrl?: string;
}

const DEFAULT_FAQS = [
  { question: "What are your hours?", answer: "We're open Monday–Friday 9 AM to 6 PM, and Saturday 10 AM to 3 PM." },
  { question: "Do you accept walk-ins?", answer: "Yes! Walk-ins are welcome, but we recommend booking ahead for shorter wait times." },
  { question: "What forms of payment do you accept?", answer: "We accept cash, all major credit cards, and digital wallets like Apple Pay." },
  { question: "Where are you located?", answer: "We're at 123 Main Street, Suite 4, Downtown. Free parking is available behind the building." },
];

const intentOptions = [
  { id: "book" as Intent, icon: Calendar, label: "Book Appointment", desc: "Schedule a visit" },
  { id: "faq" as Intent, icon: HelpCircle, label: "Ask a Question", desc: "Browse FAQs" },
  { id: "existing" as Intent, icon: Clock, label: "My Appointment", desc: "Check or change" },
  { id: "other" as Intent, icon: User, label: "Contact Us", desc: "Call or email" },
];

const CHAT_URL = `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/chat-widget`;
const AVAILABILITY_URL = `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/check-availability`;
const BOOK_URL = `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/book-appointment`;

function formatTime(time: string): string {
  const [h, m] = time.split(":").map(Number);
  const ampm = h >= 12 ? "PM" : "AM";
  const hour = h % 12 || 12;
  return `${hour}:${m.toString().padStart(2, "0")} ${ampm}`;
}

function formatDate(dateStr: string): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

async function streamChat({
  messages,
  businessContext,
  onDelta,
  onDone,
  onError,
}: {
  messages: { role: string; content: string }[];
  businessContext: Record<string, any>;
  onDelta: (text: string) => void;
  onDone: () => void;
  onError: (msg: string) => void;
}) {
  try {
    const resp = await fetch(CHAT_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY}`,
      },
      body: JSON.stringify({ messages, businessContext }),
    });

    if (!resp.ok) {
      if (resp.status === 429) {
        onError("I'm getting a lot of questions right now! Please try again in a moment. 😊");
        return;
      }
      if (resp.status === 402) {
        onError("I'm temporarily unavailable. Please try again later or contact us directly.");
        return;
      }
      onError("Sorry, something went wrong. Please try again or contact us directly.");
      return;
    }

    if (!resp.body) {
      onError("Sorry, I couldn't process that. Please try again.");
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let textBuffer = "";
    let streamDone = false;

    while (!streamDone) {
      const { done, value } = await reader.read();
      if (done) break;
      textBuffer += decoder.decode(value, { stream: true });

      let newlineIndex: number;
      while ((newlineIndex = textBuffer.indexOf("\n")) !== -1) {
        let line = textBuffer.slice(0, newlineIndex);
        textBuffer = textBuffer.slice(newlineIndex + 1);

        if (line.endsWith("\r")) line = line.slice(0, -1);
        if (line.startsWith(":") || line.trim() === "") continue;
        if (!line.startsWith("data: ")) continue;

        const jsonStr = line.slice(6).trim();
        if (jsonStr === "[DONE]") {
          streamDone = true;
          break;
        }

        try {
          const parsed = JSON.parse(jsonStr);
          const content = parsed.choices?.[0]?.delta?.content as string | undefined;
          if (content) onDelta(content);
        } catch {
          textBuffer = line + "\n" + textBuffer;
          break;
        }
      }
    }

    // Final flush
    if (textBuffer.trim()) {
      for (let raw of textBuffer.split("\n")) {
        if (!raw) continue;
        if (raw.endsWith("\r")) raw = raw.slice(0, -1);
        if (raw.startsWith(":") || raw.trim() === "") continue;
        if (!raw.startsWith("data: ")) continue;
        const jsonStr = raw.slice(6).trim();
        if (jsonStr === "[DONE]") continue;
        try {
          const parsed = JSON.parse(jsonStr);
          const content = parsed.choices?.[0]?.delta?.content as string | undefined;
          if (content) onDelta(content);
        } catch { /* ignore */ }
      }
    }

    onDone();
  } catch (e) {
    console.error("Stream error:", e);
    onError("Connection lost. Please try again.");
  }
}

const ChatWidget = ({
  embedded = false,
  botId,
  businessId,
  widgetToken,
  businessName = "Glow Wellness Studio",
  welcomeMessage,
  disclaimerText = "Please don't share sensitive personal, medical, or payment information here.",
  systemPrompt,
  businessPhone = "(555) 123-4567",
  businessEmail = "hello@glowwellness.com",
  businessAddress,
  faqs,
  services,
  calendlyUrl,
}: ChatWidgetProps) => {
  const [open, setOpen] = useState(embedded);
  const [step, setStep] = useState<Step>("intent");
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Booking state
  const [selectedService, setSelectedService] = useState<ServiceItem | null>(null);
  const [selectedDate, setSelectedDate] = useState("");
  const [availableSlots, setAvailableSlots] = useState<string[]>([]);
  const [selectedSlot, setSelectedSlot] = useState("");
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [bookingName, setBookingName] = useState("");
  const [bookingEmail, setBookingEmail] = useState("");
  const [bookingPhone, setBookingPhone] = useState("");
  const [isBooking, setIsBooking] = useState(false);
  const [bookingResult, setBookingResult] = useState<{ service_name: string; start_time: string } | null>(null);

  const activeFaqs = faqs && faqs.length > 0 ? faqs : DEFAULT_FAQS;
  const activeServices = services && services.length > 0
    ? services
    : [
        { name: "Deep Tissue Massage", duration_minutes: 60, price_text: null },
        { name: "Swedish Relaxation", duration_minutes: 45, price_text: null },
        { name: "Facial Treatment", duration_minutes: 30, price_text: null },
        { name: "Consultation", duration_minutes: 15, price_text: null },
      ];

  const businessContext = {
    id: businessId,
    name: businessName,
    services: activeServices,
    faqs: activeFaqs,
    phone: businessPhone,
    email: businessEmail,
    address: businessAddress,
    botId,
    systemPrompt,
    widgetToken,
  };

  const greeting = welcomeMessage || `👋 Hi! I'm the virtual receptionist for ${businessName}. How can I help you today?`;

  const [messages, setMessages] = useState<Message[]>([
    { id: "1", role: "bot", text: greeting },
  ]);
  const [input, setInput] = useState("");

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, step]);

  const addMessage = (role: "bot" | "user", text: string) => {
    setMessages((prev) => [...prev, { id: Date.now().toString(), role, text }]);
  };

  const toApiMessages = useCallback((msgs: Message[]) => {
    return msgs
      .filter((m) => m.id !== "1")
      .map((m) => ({
        role: m.role === "bot" ? "assistant" : "user",
        content: m.text,
      }));
  }, []);

  const sendToAI = useCallback(
    async (allMessages: Message[]) => {
      setIsStreaming(true);
      let assistantSoFar = "";
      const assistantId = Date.now().toString();

      setMessages((prev) => [...prev, { id: assistantId, role: "bot", text: "" }]);

      await streamChat({
        messages: toApiMessages(allMessages),
        businessContext,
        onDelta: (chunk) => {
          assistantSoFar += chunk;
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, text: assistantSoFar } : m))
          );
        },
        onDone: () => setIsStreaming(false),
        onError: (errorMsg) => {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, text: errorMsg } : m))
          );
          setIsStreaming(false);
        },
      });
    },
    [businessContext, toApiMessages]
  );

  const resetToMenu = () => {
    setSelectedService(null);
    setSelectedDate("");
    setAvailableSlots([]);
    setSelectedSlot("");
    setBookingName("");
    setBookingEmail("");
    setBookingPhone("");
    setBookingResult(null);
    addMessage("bot", "No problem! What else can I help you with?");
    setStep("intent");
  };

  const handleIntent = (intent: Intent) => {
    if (intent === "book") {
      // If Calendly is configured, use the embed
      if (calendlyUrl) {
        addMessage("user", "I'd like to book an appointment");
        addMessage("bot", "Sure! You can pick a time right here:");
        setStep("booking-calendly");
        return;
      }
      if (!widgetToken || !activeServices.some((s) => (s as any).id)) {
        const userMsg: Message = { id: Date.now().toString(), role: "user", text: "I'd like to book an appointment" };
        setMessages((prev) => [...prev, userMsg]);
        setStep("conversation");
        setTimeout(() => sendToAI([...messages, userMsg]), 100);
        return;
      }
      addMessage("user", "I'd like to book an appointment");
      addMessage("bot", "Great! Which service are you interested in?");
      setStep("booking-service");
    } else if (intent === "faq") {
      addMessage("user", "I have a question");
      setTimeout(() => {
        addMessage("bot", "Sure! Here are some common questions, or you can type your own:");
        setStep("faq-list");
      }, 500);
    } else if (intent === "existing") {
      const userMsg: Message = { id: Date.now().toString(), role: "user", text: "I want to check on my appointment" };
      setMessages((prev) => [...prev, userMsg]);
      setStep("conversation");
      setTimeout(() => sendToAI([...messages, userMsg]), 100);
    } else {
      addMessage("user", "I'd like to contact someone");
      setTimeout(() => {
        addMessage("bot", "Sure! How would you like to reach us?");
        setStep("contact-options");
      }, 500);
    }
  };

  const handleServiceSelect = (service: ServiceItem) => {
    setSelectedService(service);
    addMessage("user", service.name);
    addMessage("bot", "Pick a date for your appointment:");
    setStep("booking-date");
  };

  const handleDateSelect = async (dateStr: string) => {
    setSelectedDate(dateStr);
    addMessage("user", formatDate(dateStr));
    setLoadingSlots(true);
    setStep("booking-slots");

    try {
      const resp = await fetch(AVAILABILITY_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY}`,
        },
        body: JSON.stringify({
          widget_token: widgetToken,
          service_id: (selectedService as any)?.id,
          date: dateStr,
        }),
      });

      const data = await resp.json();

      if (!resp.ok) {
        const errorMessage = typeof data?.error === "string" ? data.error : data?.error?.message;
        addMessage("bot", errorMessage || "Couldn't check availability. Please try again.");
        setStep("booking-date");
        return;
      }

      if (!data.slots || data.slots.length === 0) {
        addMessage("bot", data.message || "No available slots on this date. Please pick another day.");
        setStep("booking-date");
        return;
      }

      setAvailableSlots(data.slots);
      addMessage("bot", `I found ${data.slots.length} available time${data.slots.length > 1 ? "s" : ""}. Pick one:`);
    } catch {
      addMessage("bot", "Something went wrong checking availability. Please try again.");
      setStep("booking-date");
    } finally {
      setLoadingSlots(false);
    }
  };

  const handleSlotSelect = (slot: string) => {
    setSelectedSlot(slot);
    addMessage("user", formatTime(slot));
    addMessage("bot", "Almost there! Please enter your details:");
    setStep("booking-form");
  };

  const handleBookSubmit = async () => {
    if (!bookingName.trim() || !bookingEmail.trim()) return;
    setIsBooking(true);

    try {
      const [h, m] = selectedSlot.split(":").map(Number);
      const startTime = new Date(`${selectedDate}T${selectedSlot}:00`);

      const resp = await fetch(BOOK_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY}`,
        },
        body: JSON.stringify({
          widget_token: widgetToken,
          service_id: (selectedService as any)?.id,
          start_time: startTime.toISOString(),
          name: bookingName.trim(),
          email: bookingEmail.trim(),
          phone: bookingPhone.trim() || undefined,
        }),
      });

      const data = await resp.json();

      if (!resp.ok) {
        const errorMessage = typeof data?.error === "string" ? data.error : data?.error?.message;
        addMessage("bot", errorMessage || "Booking failed. Please try again.");
        if (resp.status === 409) {
          setStep("booking-slots");
        }
        return;
      }

      setBookingResult({ service_name: data.service_name, start_time: data.start_time });
      setStep("booking-confirm");
    } catch {
      addMessage("bot", "Something went wrong. Please try again.");
    } finally {
      setIsBooking(false);
    }
  };

  const handleFaq = (faq: { question: string; answer: string }) => {
    addMessage("user", faq.question);
    setTimeout(() => addMessage("bot", faq.answer), 400);
  };

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    const userMsg: Message = { id: Date.now().toString(), role: "user", text: input.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");

    if (step === "intent" || step === "faq-list" || step === "contact-options") {
      setStep("conversation");
    }

    setTimeout(() => sendToAI([...messages, userMsg]), 100);
  };

  // Generate next 14 days for date picker
  const dateOptions = Array.from({ length: 14 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() + i);
    return {
      value: `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, "0")}-${d.getDate().toString().padStart(2, "0")}`,
      label: d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }),
    };
  });

  const chatPanel = (
    <motion.div
      initial={embedded ? false : { opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 20, scale: 0.95 }}
      transition={{ type: "spring", damping: 25, stiffness: 300 }}
      className={
        embedded
          ? "flex h-full w-full flex-col overflow-hidden bg-background"
          : "fixed bottom-6 right-6 z-50 flex h-[520px] w-[380px] flex-col overflow-hidden rounded-lg border bg-background shadow-lg"
      }
    >
      {/* Header */}
      <div className="flex items-center justify-between bg-foreground px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-background/20">
            <MessageCircle className="h-4 w-4 text-background" />
          </div>
          <div>
            <p className="text-sm font-medium text-background">{businessName}</p>
            <p className="text-xs text-background/60">
              {isStreaming ? "Typing…" : "Online • Replies instantly"}
            </p>
          </div>
        </div>
        {!embedded && (
          <button onClick={() => setOpen(false)} className="rounded p-1 text-background/60 hover:text-background">
            <X className="h-5 w-5" />
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            {msg.text === "" && msg.role === "bot" ? (
              <div className="flex items-center gap-1.5 rounded-lg bg-secondary px-3.5 py-2.5">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                <span className="text-xs text-muted-foreground">Thinking…</span>
              </div>
            ) : (
              <div
                className={`max-w-[85%] rounded-lg px-3.5 py-2.5 text-sm ${
                  msg.role === "user"
                    ? "bg-foreground text-background whitespace-pre-line"
                    : "bg-secondary text-foreground"
                }`}
              >
                {msg.role === "bot" ? (
                  <div className="prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0.5">
                    <ReactMarkdown>{msg.text}</ReactMarkdown>
                  </div>
                ) : (
                  msg.text
                )}
              </div>
            )}
          </div>
        ))}

        {/* Intent menu */}
        {step === "intent" && (
          <div className="grid grid-cols-2 gap-2 pt-2">
            {intentOptions.map((opt) => (
              <button
                key={opt.id}
                onClick={() => handleIntent(opt.id)}
                className="flex flex-col items-center gap-1.5 rounded-lg border p-3 text-center transition-colors hover:bg-secondary"
              >
                <opt.icon className="h-4 w-4" />
                <span className="text-xs font-medium">{opt.label}</span>
                <span className="text-[10px] text-muted-foreground">{opt.desc}</span>
              </button>
            ))}
          </div>
        )}

        {/* Service selection */}
        {step === "booking-service" && (
          <div className="flex flex-col gap-2 pt-1">
            {activeServices.map((svc) => (
              <button
                key={svc.name}
                onClick={() => handleServiceSelect(svc)}
                className="flex items-center justify-between rounded-lg border px-3 py-2.5 text-left text-sm transition-colors hover:bg-secondary"
              >
                <div>
                  <p className="font-medium">{svc.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {svc.duration_minutes} min{svc.price_text ? ` • ${svc.price_text}` : ""}
                  </p>
                </div>
                <Calendar className="h-4 w-4 text-muted-foreground" />
              </button>
            ))}
          </div>
        )}

        {/* Date selection */}
        {step === "booking-date" && (
          <div className="flex flex-col gap-1.5 pt-1 max-h-48 overflow-y-auto">
            {dateOptions.map((d) => (
              <button
                key={d.value}
                onClick={() => handleDateSelect(d.value)}
                className="rounded-lg border px-3 py-2 text-left text-sm transition-colors hover:bg-secondary"
              >
                {d.label}
              </button>
            ))}
          </div>
        )}

        {/* Slot selection */}
        {step === "booking-slots" && (
          <>
            {loadingSlots ? (
              <div className="flex items-center gap-2 py-4 justify-center">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Checking availability…</span>
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-1.5 pt-1 max-h-48 overflow-y-auto">
                {availableSlots.map((slot) => (
                  <button
                    key={slot}
                    onClick={() => handleSlotSelect(slot)}
                    className="rounded-md border px-2 py-1.5 text-xs font-medium transition-colors hover:bg-secondary"
                  >
                    {formatTime(slot)}
                  </button>
                ))}
              </div>
            )}
          </>
        )}

        {/* Booking form */}
        {step === "booking-form" && (
          <div className="rounded-lg border p-3 space-y-3 pt-1">
            <div>
              <Label className="text-xs">Name *</Label>
              <Input
                value={bookingName}
                onChange={(e) => setBookingName(e.target.value)}
                placeholder="Your name"
                className="mt-1 h-8 text-sm"
              />
            </div>
            <div>
              <Label className="text-xs">Email *</Label>
              <Input
                type="email"
                value={bookingEmail}
                onChange={(e) => setBookingEmail(e.target.value)}
                placeholder="you@email.com"
                className="mt-1 h-8 text-sm"
              />
            </div>
            <div>
              <Label className="text-xs">Phone (optional)</Label>
              <Input
                value={bookingPhone}
                onChange={(e) => setBookingPhone(e.target.value)}
                placeholder="(555) 123-4567"
                className="mt-1 h-8 text-sm"
              />
            </div>
            <Button
              size="sm"
              className="w-full"
              onClick={handleBookSubmit}
              disabled={isBooking || !bookingName.trim() || !bookingEmail.trim()}
            >
              {isBooking ? (
                <><Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> Booking…</>
              ) : (
                "Confirm Booking"
              )}
            </Button>
          </div>
        )}

        {/* Booking confirmation */}
        {step === "booking-confirm" && bookingResult && (
          <div className="rounded-lg border border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950 p-4 text-center space-y-2">
            <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-green-100 dark:bg-green-900">
              <Check className="h-5 w-5 text-green-600 dark:text-green-400" />
            </div>
            <p className="text-sm font-medium text-green-800 dark:text-green-200">Appointment Booked!</p>
            <p className="text-xs text-green-700 dark:text-green-300">
              {bookingResult.service_name} on{" "}
              {new Date(bookingResult.start_time).toLocaleDateString("en-US", {
                weekday: "short",
                month: "short",
                day: "numeric",
              })}{" "}
              at{" "}
              {new Date(bookingResult.start_time).toLocaleTimeString("en-US", {
                hour: "numeric",
                minute: "2-digit",
              })}
            </p>
            <p className="text-[10px] text-green-600 dark:text-green-400">
              You'll receive a confirmation shortly. We look forward to seeing you!
            </p>
          </div>
        )}

        {/* Calendly embed */}
        {step === "booking-calendly" && calendlyUrl && (
          <div className="rounded-lg border overflow-hidden" style={{ height: 500 }}>
            <iframe
              src={`${calendlyUrl}?embed_type=inline&hide_gdpr_banner=1`}
              width="100%"
              height="100%"
              frameBorder="0"
              title="Book an appointment"
              className="bg-background"
            />
          </div>
        )}

        {/* FAQ list */}
        {step === "faq-list" && (
          <div className="flex flex-col gap-2 pt-1">
            {activeFaqs.map((faq) => (
              <button
                key={faq.question}
                onClick={() => handleFaq(faq)}
                className="rounded-lg border px-3 py-2 text-left text-sm transition-colors hover:bg-secondary"
              >
                {faq.question}
              </button>
            ))}
          </div>
        )}

        {/* Contact options */}
        {step === "contact-options" && (
          <div className="flex flex-col gap-2 pt-1">
            <a
              href={`tel:${businessPhone.replace(/\D/g, "")}`}
              className="flex items-center gap-3 rounded-lg border px-4 py-3 text-sm transition-colors hover:bg-secondary"
            >
              <Phone className="h-4 w-4" />
              <div>
                <p className="font-medium">Call Us</p>
                <p className="text-xs text-muted-foreground">{businessPhone}</p>
              </div>
            </a>
            <a
              href={`mailto:${businessEmail}`}
              className="flex items-center gap-3 rounded-lg border px-4 py-3 text-sm transition-colors hover:bg-secondary"
            >
              <Mail className="h-4 w-4" />
              <div>
                <p className="font-medium">Email Us</p>
                <p className="text-xs text-muted-foreground">{businessEmail}</p>
              </div>
            </a>
            <button
              onClick={() => {
                addMessage("user", "I'll leave a message here instead");
                setTimeout(() => {
                  addMessage("bot", "Sure! Please type your message and we'll get back to you as soon as possible.");
                  setStep("conversation");
                }, 400);
              }}
              className="flex items-center gap-3 rounded-lg border px-4 py-3 text-sm transition-colors hover:bg-secondary"
            >
              <MessageCircle className="h-4 w-4" />
              <div className="text-left">
                <p className="font-medium">Leave a Message</p>
                <p className="text-xs text-muted-foreground">We'll get back to you</p>
              </div>
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Disclaimer */}
      {disclaimerText && (
        <div className="px-4 py-1">
          <p className="text-center text-[10px] text-muted-foreground">{disclaimerText}</p>
        </div>
      )}

      {/* Input + Back to Menu */}
      <div className="border-t p-3 space-y-2">
        {step !== "intent" && (
          <button
            onClick={resetToMenu}
            className="flex w-full items-center justify-center gap-1.5 rounded-md py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          >
            <RotateCcw className="h-3 w-3" />
            Back to main menu
          </button>
        )}
        <div className="flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Type a message..."
            disabled={isStreaming}
            className="flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring disabled:opacity-50"
          />
          <Button size="icon" onClick={handleSend} disabled={isStreaming} className="h-9 w-9">
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </motion.div>
  );

  if (embedded) return chatPanel;

  return (
    <>
      <AnimatePresence>
        {!open && (
          <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }} className="fixed bottom-6 right-6 z-50">
            <button
              onClick={() => setOpen(true)}
              className="flex h-12 w-12 items-center justify-center rounded-full bg-foreground shadow-lg transition-transform hover:scale-105"
            >
              <MessageCircle className="h-5 w-5 text-background" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>{open && chatPanel}</AnimatePresence>
    </>
  );
};

export default ChatWidget;
