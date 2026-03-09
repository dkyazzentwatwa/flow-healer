import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/contexts/AuthContext";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Tables } from "@/integrations/supabase/types";

interface BusinessContextType {
  businesses: Tables<"businesses">[];
  activeBusiness: Tables<"businesses"> | null;
  setActiveBusinessId: (id: string) => void;
  refetchBusinesses: () => Promise<void>;
  isLoading: boolean;
}

const BusinessContext = createContext<BusinessContextType | undefined>(undefined);

const STORAGE_KEY = "localai_active_business_id";

export const BusinessProvider = ({ children }: { children: ReactNode }) => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(() => localStorage.getItem(STORAGE_KEY));

  const { data: businesses = [], isLoading } = useQuery({
    queryKey: ["businesses", user?.id],
    queryFn: async () => {
      if (!user) return [];
      const { data, error } = await supabase
        .from("businesses")
        .select("*")
        .eq("owner_id", user.id)
        .order("created_at", { ascending: true });
      if (error) throw error;
      return data;
    },
    enabled: !!user,
  });

  const activeBusiness = businesses.find((b) => b.id === activeId) ?? businesses[0] ?? null;

  useEffect(() => {
    if (activeBusiness && activeBusiness.id !== activeId) {
      setActiveId(activeBusiness.id);
      localStorage.setItem(STORAGE_KEY, activeBusiness.id);
    }
  }, [activeBusiness, activeId]);

  const setActiveBusinessId = useCallback((id: string) => {
    setActiveId(id);
    localStorage.setItem(STORAGE_KEY, id);
  }, []);

  const refetchBusinesses = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["businesses", user?.id] });
  }, [queryClient, user?.id]);

  return (
    <BusinessContext.Provider value={{ businesses, activeBusiness, setActiveBusinessId, refetchBusinesses, isLoading }}>
      {children}
    </BusinessContext.Provider>
  );
};

export const useActiveBusiness = () => {
  const ctx = useContext(BusinessContext);
  if (!ctx) throw new Error("useActiveBusiness must be used within BusinessProvider");
  return ctx;
};
