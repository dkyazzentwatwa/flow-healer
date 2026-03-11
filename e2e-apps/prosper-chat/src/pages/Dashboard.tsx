import { useState } from "react";
import { Routes, Route, Link, useLocation } from "react-router-dom";
import {
  LayoutDashboard, MessageCircle, Calendar, Users, Settings,
  FileText, Menu, Briefcase, LogOut, Shield, Building2, UserCog, LayoutTemplate, CreditCard, BarChart3, Bot,
  Plus, Check, ChevronsUpDown, HelpCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent,
  SidebarGroupLabel, SidebarHeader, SidebarInset, SidebarMenu, SidebarMenuButton,
  SidebarMenuItem, SidebarProvider, SidebarRail, SidebarTrigger, useSidebar,
} from "@/components/ui/sidebar";
import { NavLink } from "@/components/NavLink";
import { useAuth } from "@/contexts/AuthContext";
import { BusinessProvider, useActiveBusiness } from "@/contexts/BusinessContext";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { PLANS } from "@/lib/plans";
import DashboardHome from "@/components/dashboard/DashboardHome";
import ServicesPage from "@/components/dashboard/ServicesPage";
import LeadsPage from "@/components/dashboard/LeadsPage";
import AppointmentsPage from "@/components/dashboard/AppointmentsPage";
import FaqsPage from "@/components/dashboard/FaqsPage";
import SettingsPage from "@/components/dashboard/SettingsPage";
import TemplatesPage from "@/components/dashboard/TemplatesPage";
import ConversationsPage from "@/components/dashboard/ConversationsPage";
import BillingPage from "@/components/dashboard/BillingPage";
import AnalyticsPage from "@/components/dashboard/AnalyticsPage";
import AdminOverview from "@/components/dashboard/admin/AdminOverview";
import AdminBusinesses from "@/components/dashboard/admin/AdminBusinesses";
import AdminUsers from "@/components/dashboard/admin/AdminUsers";
import BotsPage from "@/components/dashboard/BotsPage";
import HelpPage from "@/components/dashboard/HelpPage";
import type { TablesInsert } from "@/integrations/supabase/types";

const navItems = [
  { path: "/dashboard", icon: LayoutDashboard, label: "Overview" },
  { path: "/dashboard/services", icon: Briefcase, label: "Services" },
  { path: "/dashboard/faqs", icon: FileText, label: "FAQs" },
  { path: "/dashboard/templates", icon: LayoutTemplate, label: "Templates" },
  { path: "/dashboard/bots", icon: Bot, label: "Bots" },
  { path: "/dashboard/leads", icon: Users, label: "Leads" },
  { path: "/dashboard/appointments", icon: Calendar, label: "Appointments" },
  { path: "/dashboard/conversations", icon: MessageCircle, label: "Conversations" },
  { path: "/dashboard/analytics", icon: BarChart3, label: "Analytics" },
  { path: "/dashboard/billing", icon: CreditCard, label: "Usage & Billing" },
  { path: "/dashboard/settings", icon: Settings, label: "Settings" },
  { path: "/dashboard/help", icon: HelpCircle, label: "Help & Guide" },
];

const adminNavItems = [
  { path: "/dashboard/admin", icon: Shield, label: "Admin Overview" },
  { path: "/dashboard/admin/businesses", icon: Building2, label: "All Businesses" },
  { path: "/dashboard/admin/users", icon: UserCog, label: "All Users" },
];

function getErrorMessage(error: unknown, fallback: string): string {
  return typeof error === "object" && error && "message" in error && typeof error.message === "string"
    ? error.message
    : fallback;
}

const AppSidebar = () => {
  const location = useLocation();
  const { isAdmin, signOut, user } = useAuth();
  const { businesses, activeBusiness, setActiveBusinessId, refetchBusinesses } = useActiveBusiness();
  const { state } = useSidebar();
  const collapsed = state === "collapsed";

  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [newBizName, setNewBizName] = useState("");
  const [newBizEmail, setNewBizEmail] = useState("");
  const [newBizPhone, setNewBizPhone] = useState("");
  const [addingBiz, setAddingBiz] = useState(false);

  const subscriptionBusinessId = activeBusiness?.id ?? businesses[0]?.id;

  const { data: subscription } = useQuery({
    queryKey: ["subscription", subscriptionBusinessId],
    queryFn: async () => {
      const { data } = await supabase
        .from("subscriptions")
        .select("plan")
        .eq("business_id", subscriptionBusinessId!)
        .single();
      return data;
    },
    enabled: !!subscriptionBusinessId,
  });

  const currentPlan = subscription?.plan ?? "free";
  const maxBusinesses = PLANS[currentPlan as keyof typeof PLANS]?.limits.businesses ?? 1;
  const canAddBusiness = currentPlan === "agency" && businesses.length < maxBusinesses;

  const handleAddBusiness = async () => {
    if (!user || !newBizName.trim()) return;
    setAddingBiz(true);
    try {
      const { data: newBiz, error } = await supabase
        .from("businesses")
        .insert({
          owner_id: user.id,
          name: newBizName.trim(),
          email: newBizEmail || null,
          phone: newBizPhone || null,
          onboarding_completed: true,
        })
        .select()
        .single();
      if (error) throw error;

      const subscriptionInsert: TablesInsert<"subscriptions"> = {
        business_id: newBiz.id,
        plan: "agency",
        status: "active",
      };
      await supabase.from("subscriptions").insert(subscriptionInsert);

      await refetchBusinesses();
      setActiveBusinessId(newBiz.id);
      setAddDialogOpen(false);
      setNewBizName("");
      setNewBizEmail("");
      setNewBizPhone("");
    } catch (e: unknown) {
      console.error("Failed to add business:", e);
      const message = getErrorMessage(e, "Could not add business");
      console.error(message);
    } finally {
      setAddingBiz(false);
    }
  };

  const isActive = (path: string) => location.pathname === path;

  return (
    <>
      <Sidebar collapsible="icon" side="left">
        <SidebarHeader className="border-b">
          <Link to="/" className="flex items-center gap-2 px-1 py-1">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-foreground">
              <MessageCircle className="h-3.5 w-3.5 text-background" />
            </div>
            {!collapsed && <span className="text-sm font-semibold tracking-tight">LocalAI</span>}
          </Link>
        </SidebarHeader>

        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                {navItems.map((item) => (
                  <SidebarMenuItem key={item.path}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive(item.path)}
                      tooltip={item.label}
                    >
                      <NavLink to={item.path} end={item.path === "/dashboard"}>
                        <item.icon className="h-4 w-4" />
                        <span>{item.label}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          {isAdmin && (
            <SidebarGroup>
              <SidebarGroupLabel>Admin</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {adminNavItems.map((item) => (
                    <SidebarMenuItem key={item.path}>
                      <SidebarMenuButton
                        asChild
                        isActive={isActive(item.path)}
                        tooltip={item.label}
                      >
                        <NavLink to={item.path} end={item.path === "/dashboard/admin"}>
                          <item.icon className="h-4 w-4" />
                          <span>{item.label}</span>
                        </NavLink>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          )}
        </SidebarContent>

        <SidebarFooter>
          {/* Business Switcher */}
          {businesses.length > 1 ? (
            <Popover open={switcherOpen} onOpenChange={setSwitcherOpen}>
              <PopoverTrigger asChild>
                <button className="flex w-full items-center justify-between rounded-md border p-2.5 hover:bg-sidebar-accent transition-colors">
                  <div className="text-left min-w-0">
                    {collapsed ? (
                      <Building2 className="h-4 w-4" />
                    ) : (
                      <>
                        <p className="text-xs font-medium truncate">{activeBusiness?.name || "My Business"}</p>
                        <p className="text-[10px] text-muted-foreground mt-0.5 font-mono truncate">{activeBusiness?.widget_key || "..."}</p>
                      </>
                    )}
                  </div>
                  {!collapsed && <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
                </button>
              </PopoverTrigger>
              <PopoverContent className="w-56 p-1" align="start" side="top">
                {businesses.map((b) => (
                  <button
                    key={b.id}
                    onClick={() => { setActiveBusinessId(b.id); setSwitcherOpen(false); }}
                    className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-sidebar-accent transition-colors"
                  >
                    <div className="flex-1 text-left min-w-0">
                      <p className="text-xs font-medium truncate">{b.name}</p>
                      <p className="text-[10px] text-muted-foreground font-mono truncate">{b.widget_key}</p>
                    </div>
                    {b.id === activeBusiness?.id && <Check className="h-3.5 w-3.5 shrink-0" />}
                  </button>
                ))}
                {canAddBusiness && (
                  <>
                    <div className="my-1 h-px bg-border" />
                    <button
                      onClick={() => { setSwitcherOpen(false); setAddDialogOpen(true); }}
                      className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-sidebar-accent hover:text-foreground transition-colors"
                    >
                      <Plus className="h-3.5 w-3.5" /> Add Business
                    </button>
                  </>
                )}
              </PopoverContent>
            </Popover>
          ) : (
            <div className="rounded-md border p-2.5">
              {collapsed ? (
                <Building2 className="h-4 w-4 mx-auto" />
              ) : (
                <>
                  <p className="text-xs font-medium">{activeBusiness?.name || "My Business"}</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5 font-mono">{activeBusiness?.widget_key || "..."}</p>
                </>
              )}
            </div>
          )}

          {canAddBusiness && businesses.length <= 1 && !collapsed && (
            <SidebarMenuButton onClick={() => setAddDialogOpen(true)} tooltip="Add Business">
              <Plus className="h-4 w-4" />
              <span>Add Business</span>
            </SidebarMenuButton>
          )}

          <SidebarMenuButton onClick={signOut} tooltip="Sign out">
            <LogOut className="h-4 w-4" />
            <span>Sign out</span>
          </SidebarMenuButton>
        </SidebarFooter>

        <SidebarRail />
      </Sidebar>

      {/* Add Business Dialog */}
      <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add a New Business</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Business Name *</Label>
              <Input value={newBizName} onChange={(e) => setNewBizName(e.target.value)} placeholder="Acme Clinic" />
            </div>
            <div className="space-y-1.5">
              <Label>Email</Label>
              <Input type="email" value={newBizEmail} onChange={(e) => setNewBizEmail(e.target.value)} placeholder="hello@acme.com" />
            </div>
            <div className="space-y-1.5">
              <Label>Phone</Label>
              <Input value={newBizPhone} onChange={(e) => setNewBizPhone(e.target.value)} placeholder="(555) 123-4567" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleAddBusiness} disabled={addingBiz || !newBizName.trim()}>
              {addingBiz ? "Creating..." : "Create Business"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

const DashboardInner = () => {
  const { activeBusiness } = useActiveBusiness();

  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full">
        <AppSidebar />

        <SidebarInset>
          <header className="flex h-14 items-center gap-4 border-b px-4 md:px-6">
            <SidebarTrigger />
            <div className="flex-1" />
            <Button size="sm" className="hidden sm:inline-flex" onClick={() => window.open(`/widget/${activeBusiness?.widget_key}`, '_blank')}>
              <MessageCircle className="h-4 w-4 mr-1" /> Test Widget
            </Button>
            <Button size="icon" variant="outline" className="sm:hidden" onClick={() => window.open(`/widget/${activeBusiness?.widget_key}`, '_blank')}>
              <MessageCircle className="h-4 w-4" />
            </Button>
          </header>

          <div className="flex-1 p-4 md:p-6 overflow-auto">
            <Routes>
              <Route index element={<DashboardHome />} />
              <Route path="services" element={<ServicesPage />} />
              <Route path="faqs" element={<FaqsPage />} />
              <Route path="templates" element={<TemplatesPage />} />
              <Route path="bots" element={<BotsPage />} />
              <Route path="leads" element={<LeadsPage />} />
              <Route path="appointments" element={<AppointmentsPage />} />
              <Route path="conversations" element={<ConversationsPage />} />
              <Route path="analytics" element={<AnalyticsPage />} />
              <Route path="billing" element={<BillingPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="help" element={<HelpPage />} />
              <Route path="admin" element={<AdminOverview />} />
              <Route path="admin/businesses" element={<AdminBusinesses />} />
              <Route path="admin/users" element={<AdminUsers />} />
            </Routes>
          </div>
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
};

const Dashboard = () => (
  <BusinessProvider>
    <DashboardInner />
  </BusinessProvider>
);

export default Dashboard;
