import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  Bot,
  Briefcase,
  FileText,
  Users,
  Calendar,
  MessageCircle,
  Code,
  CreditCard,
  Settings,
  BarChart3,
  LayoutDashboard,
  ArrowRight,
  HelpCircle,
  Rocket,
} from "lucide-react";

const sections = [
  {
    id: "getting-started",
    icon: Rocket,
    title: "Getting Started",
    content: [
      {
        q: "How do I set up my business?",
        a: "When you first sign up you're guided through a 4-step onboarding wizard: 1) Enter your Business Profile (name, phone, address, timezone), 2) Add your Services (e.g. haircut, consultation), 3) Add FAQs visitors commonly ask, and 4) Copy the widget embed code for your website. You can revisit any of these from the dashboard at any time.",
      },
      {
        q: "What is the Dashboard Overview?",
        a: "The Overview page is your home base. It shows key stats (leads, appointments, conversations, active services), a setup progress checklist, and your most recent leads. If you're approaching your chat limit you'll also see a usage warning banner.",
      },
      {
        q: "How do I navigate the dashboard?",
        a: "Use the sidebar on the left to jump between sections. On mobile, tap the menu icon in the top-left corner. The sidebar collapses to icons for more space — hover over an icon to see its label.",
      },
    ],
  },
  {
    id: "bots",
    icon: Bot,
    title: "Managing Bots",
    content: [
      {
        q: "What is a Bot?",
        a: "A bot is a chat assistant that responds to visitors on your website. Each bot has its own welcome message, personality (system prompt), and scoped knowledge base (which FAQs and services it can reference). This means you can create specialized bots for different purposes — e.g. a 'Sales Bot' and a 'Support Bot'.",
      },
      {
        q: "How do I create a new bot?",
        a: "Go to the Bots page and click '+ New Bot'. Give it a name, write a welcome message, optionally customise the system prompt, and select which services and FAQs it should know about. Save, and your bot is live.",
      },
      {
        q: "How many bots can I have?",
        a: "This depends on your plan. Starter plans get 1 bot, Pro plans get up to 5, and Agency plans get unlimited bots.",
      },
      {
        q: "How do I embed a specific bot on my site?",
        a: "Each bot has a unique widget key. On the Bots page, click the code icon next to the bot to copy its embed snippet. Paste the snippet into your website's HTML where you want the chat bubble to appear.",
      },
      {
        q: "Can I change which FAQs and services a bot uses?",
        a: "Yes. Open the bot you want to edit, scroll to the Knowledge section, and toggle the FAQs and services on or off. Changes take effect immediately.",
      },
    ],
  },
  {
    id: "services",
    icon: Briefcase,
    title: "Services",
    content: [
      {
        q: "What are Services?",
        a: "Services represent the offerings your business provides — e.g. 'Deep Tissue Massage (60 min)' or 'Free Consultation'. Each service has a name, description, duration, and optional price text. The chatbot references these when visitors ask what you offer or want to book an appointment.",
      },
      {
        q: "How do I add or edit a service?",
        a: "Go to the Services page and click '+ Add Service'. Fill in the details and save. To edit an existing service, click on it to open the detail modal and update any field.",
      },
      {
        q: "How are services grouped?",
        a: "Services are organised by bot. If a service is assigned to a specific bot it appears under that bot's section. Unassigned services appear in a 'Shared / Unassigned' group.",
      },
    ],
  },
  {
    id: "faqs",
    icon: FileText,
    title: "FAQs",
    content: [
      {
        q: "What are FAQs used for?",
        a: "FAQs feed your chatbot's knowledge base. When a visitor asks a question, the bot checks its assigned FAQs and responds with the matching answer. The better your FAQs, the more helpful your bot will be.",
      },
      {
        q: "How do I manage FAQs?",
        a: "Go to the FAQs page. You can add new question-answer pairs, edit existing ones, and toggle them active/inactive. Like services, FAQs are grouped by bot so you can scope knowledge per bot.",
      },
      {
        q: "Any tips for writing good FAQs?",
        a: "Keep answers concise but thorough. Cover topics visitors ask most — pricing, hours, location, booking process, cancellation policy. Use natural language since the bot may paraphrase the answer.",
      },
    ],
  },
  {
    id: "templates",
    icon: LayoutDashboard,
    title: "Templates",
    content: [
      {
        q: "What are Templates?",
        a: "Templates are pre-built sets of services and FAQs tailored for specific industries (e.g. dental clinic, hair salon, law firm). Applying a template instantly populates your business with relevant content so you don't have to start from scratch.",
      },
      {
        q: "Can I customise a template after applying it?",
        a: "Absolutely. Templates are just a starting point. After applying one, you can add, edit, or remove any services and FAQs to match your business perfectly.",
      },
    ],
  },
  {
    id: "leads",
    icon: Users,
    title: "Leads",
    content: [
      {
        q: "How are leads captured?",
        a: "When a visitor interacts with your chat widget and provides their name, email, or phone number, a lead record is automatically created. The bot can also prompt visitors for contact details during conversation.",
      },
      {
        q: "What do the lead statuses mean?",
        a: "• New — just captured, not yet reviewed\n• Contacted — you've reached out\n• Qualified — a promising prospect\n• Converted — became a customer\n• Lost — didn't convert. You can update a lead's status by clicking on it in the Leads page.",
      },
      {
        q: "Can I export leads?",
        a: "Currently leads are viewable in the dashboard. Export functionality is on the roadmap.",
      },
    ],
  },
  {
    id: "appointments",
    icon: Calendar,
    title: "Appointments",
    content: [
      {
        q: "How does appointment booking work?",
        a: "Visitors can book appointments through the chat widget. The bot checks your business hours and existing appointments for availability, then creates a booking. You can set a buffer time between appointments in Settings.",
      },
      {
        q: "How do I manage appointment statuses?",
        a: "Go to the Appointments page. Each appointment can be marked as pending, confirmed, cancelled, completed, or no-show. Click on an appointment to update its status or add notes.",
      },
      {
        q: "How do I set my business hours?",
        a: "Go to Settings → Business Hours. Toggle each day on/off and set the open and close times. The chat widget uses these hours to offer available time slots.",
      },
    ],
  },
  {
    id: "conversations",
    icon: MessageCircle,
    title: "Conversations",
    content: [
      {
        q: "Where can I see chat transcripts?",
        a: "The Conversations page lists every conversation your bots have had. Click on any conversation to read the full transcript, see if it was escalated, and view the detected intent.",
      },
      {
        q: "What does 'escalated' mean?",
        a: "If the bot can't handle a query, it flags the conversation as escalated. You can set an escalation email and phone in Settings so you're notified when this happens.",
      },
    ],
  },
  {
    id: "widget",
    icon: Code,
    title: "Embedding the Widget",
    content: [
      {
        q: "How do I add the chat widget to my website?",
        a: 'Copy the embed snippet from the Bots page (or from the onboarding wizard). Paste it into your website\'s HTML just before the closing </body> tag. The widget will appear as a chat bubble in the bottom-right corner.',
      },
      {
        q: "Can I test the widget without embedding it?",
        a: "Yes! Click the 'Test Widget' button in the dashboard header to open the widget in a new tab and see exactly what your visitors will experience.",
      },
      {
        q: "Does the widget work on all devices?",
        a: "Yes. The widget is fully responsive and works on desktop, tablet, and mobile browsers.",
      },
    ],
  },
  {
    id: "analytics",
    icon: BarChart3,
    title: "Analytics",
    content: [
      {
        q: "What analytics are available?",
        a: "The Analytics page shows charts for conversations over time, lead capture rates, appointment bookings, and chat usage against your plan limits. Use this to understand how your bots are performing.",
      },
    ],
  },
  {
    id: "billing",
    icon: CreditCard,
    title: "Usage & Billing",
    content: [
      {
        q: "What plans are available?",
        a: "• Free — limited chats/month, 1 bot, basic features\n• Pro — higher chat limits, up to 5 bots, analytics\n• Agency — unlimited chats and bots, multi-business support, priority features.",
      },
      {
        q: "How do I upgrade my plan?",
        a: "Go to Usage & Billing and click 'Upgrade' on the plan you want. You'll be redirected to a secure checkout. Your new limits take effect immediately.",
      },
      {
        q: "What happens if I hit my chat limit?",
        a: "A warning banner appears when you reach 80% of your monthly chats. At 100%, the widget stops accepting new conversations until your next billing cycle or until you upgrade.",
      },
    ],
  },
  {
    id: "settings",
    icon: Settings,
    title: "Settings",
    content: [
      {
        q: "What can I configure in Settings?",
        a: "The Settings page lets you update your business profile (name, email, phone, address), set business hours and timezone, configure a buffer between appointments, set escalation contacts, and manage privacy preferences (transcript storage, data retention).",
      },
      {
        q: "What is the 'buffer minutes' setting?",
        a: "Buffer minutes add a gap between consecutive appointments. For example, a 15-minute buffer means if one appointment ends at 2:00 PM, the next available slot starts at 2:15 PM. This gives you breathing room between clients.",
      },
      {
        q: "How do privacy settings work?",
        a: "You can toggle whether conversation transcripts are stored and set a data retention period (in days). After the retention period, transcripts are automatically purged.",
      },
    ],
  },
];

const HelpPage = () => {
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <HelpCircle className="h-5 w-5 text-muted-foreground" />
          <h1 className="text-2xl font-semibold tracking-tight">Help Center</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Everything you need to know about setting up and managing your chatbots.
        </p>
      </div>

      {/* Quick-links */}
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {sections.map((s) => (
          <a
            key={s.id}
            href={`#${s.id}`}
            className="flex items-center gap-2.5 rounded-lg border p-3 text-sm hover:bg-accent/50 transition-colors group"
          >
            <s.icon className="h-4 w-4 text-muted-foreground group-hover:text-foreground transition-colors" />
            <span className="font-medium">{s.title}</span>
            <ArrowRight className="ml-auto h-3.5 w-3.5 text-muted-foreground/40 group-hover:text-foreground transition-colors" />
          </a>
        ))}
      </div>

      {/* Sections */}
      <div className="space-y-6">
        {sections.map((section) => (
          <div key={section.id} id={section.id} className="scroll-mt-20">
            <div className="flex items-center gap-2 mb-3">
              <section.icon className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-lg font-medium">{section.title}</h2>
            </div>

            <Accordion type="multiple" className="rounded-lg border">
              {section.content.map((item, idx) => (
                <AccordionItem key={idx} value={`${section.id}-${idx}`} className="px-4 last:border-b-0">
                  <AccordionTrigger className="text-sm text-left">
                    {item.q}
                  </AccordionTrigger>
                  <AccordionContent className="text-sm text-muted-foreground whitespace-pre-line">
                    {item.a}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        ))}
      </div>

      <div className="rounded-lg border p-5 text-center">
        <p className="text-sm text-muted-foreground">
          Still have questions? Reach out to us at{" "}
          <a href="mailto:support@prosperchat.com" className="underline hover:text-foreground">
            support@prosperchat.com
          </a>
        </p>
      </div>
    </div>
  );
};

export default HelpPage;
