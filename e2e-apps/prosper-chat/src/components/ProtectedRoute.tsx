import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  // Fetch the first business to check onboarding status
  const { data: firstBusiness, isLoading: bizLoading } = useQuery({
    queryKey: ["first-business", user?.id],
    queryFn: async () => {
      const { data } = await supabase
        .from("businesses")
        .select("id, onboarding_completed")
        .eq("owner_id", user!.id)
        .order("created_at", { ascending: true })
        .limit(1)
        .single();
      return data;
    },
    enabled: !!user,
  });

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  if (!user) return <Navigate to="/auth" replace />;

  if (bizLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  const isOnboarding = location.pathname === "/onboarding";
  if (firstBusiness && !firstBusiness.onboarding_completed && !isOnboarding) {
    return <Navigate to="/onboarding" replace />;
  }

  if (firstBusiness?.onboarding_completed && isOnboarding) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
};

export default ProtectedRoute;
