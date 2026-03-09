import { Navbar, Hero, Features, HowItWorks, Testimonials, Pricing, Footer } from "@/components/landing/LandingSections";
import ChatWidget from "@/components/chat/ChatWidget";

const Index = () => {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <Hero />
      <Features />
      <HowItWorks />

      {/* Demo section */}
      <section className="border-t py-24" id="demo">
        <div className="container mx-auto px-4 text-center">
          <h2 className="mb-4 text-3xl font-bold tracking-tight sm:text-4xl">Try the Live Demo</h2>
          <p className="mb-8 text-muted-foreground max-w-xl mx-auto">
            Click the chat bubble in the bottom-right corner to experience the AI receptionist as your visitors would.
          </p>
          <div className="inline-flex items-center gap-2 rounded-full border px-5 py-2 text-sm text-muted-foreground">
            <span className="h-2 w-2 rounded-full bg-blue animate-pulse" />
            Widget is live — try it now
          </div>
        </div>
      </section>

      <Testimonials />
      <Pricing />
      <Footer />
      <ChatWidget />
    </div>
  );
};

export default Index;
