import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useActiveBusiness } from "@/contexts/BusinessContext";
import { MessageCircle, AlertTriangle } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Json, Tables } from "@/integrations/supabase/types";

interface ConversationMessage {
  role: string;
  content: string;
}

type ConversationLead = Pick<Tables<"leads">, "first_name" | "email">;
type ConversationRow = Tables<"conversations"> & {
  leads: ConversationLead | null;
};

const ConversationsPage = () => {
  const { activeBusiness: business } = useActiveBusiness();
  const [selected, setSelected] = useState<ConversationRow | null>(null);

  const { data: conversations, isLoading } = useQuery({
    queryKey: ["conversations", business?.id],
    queryFn: async () => {
      const { data } = await supabase
        .from("conversations")
        .select("*, leads(first_name, email)")
        .eq("business_id", business!.id)
        .order("created_at", { ascending: false })
        .limit(50);
      return (data || []) as ConversationRow[];
    },
    enabled: !!business,
  });

  const getMessages = (msgs: Json | null): ConversationMessage[] => {
    if (!msgs || !Array.isArray(msgs)) return [];
    return msgs as unknown as ConversationMessage[];
  };

  const getPreview = (msgs: Json | null): string => {
    const parsed = getMessages(msgs);
    if (!parsed.length) return "No messages";
    const last = parsed[parsed.length - 1];
    const text = typeof last === "object" && last && "content" in last ? String(last.content) : "";
    return text.length > 80 ? text.slice(0, 80) + "…" : text;
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Conversations</h1>
        <p className="text-sm text-muted-foreground">Chat transcripts from your widget visitors</p>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-lg" />
          ))}
        </div>
      ) : !conversations?.length ? (
        <div className="rounded-lg border p-12 text-center">
          <p className="text-muted-foreground">No conversations yet. They'll appear here when visitors chat with your widget.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {conversations.map((c) => {
            const msgs = getMessages(c.messages);
            return (
              <div
                key={c.id}
                onClick={() => setSelected(c)}
                className="flex items-center gap-4 rounded-lg border p-4 cursor-pointer hover:bg-secondary/30 transition-colors"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-md bg-secondary shrink-0">
                  <MessageCircle className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium truncate">
                      {c.leads?.first_name || "Anonymous"}
                    </p>
                    {c.escalated && (
                      <span className="flex items-center gap-1 text-xs text-destructive">
                        <AlertTriangle className="h-3 w-3" /> Escalated
                      </span>
                    )}
                    {c.intent && (
                      <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                        {c.intent}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground truncate mt-0.5">{getPreview(c.messages)}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-xs text-muted-foreground">{new Date(c.created_at).toLocaleDateString()}</p>
                  <p className="text-xs text-muted-foreground">{msgs.length} msgs</p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Transcript Dialog */}
      <Dialog open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              Conversation with {selected?.leads?.first_name || "Anonymous"}
            </DialogTitle>
            <DialogDescription>
              {selected && new Date(selected.created_at).toLocaleString()}
              {selected?.intent && ` • Intent: ${selected.intent}`}
              {selected?.escalated && " • Escalated"}
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="max-h-[400px]">
            <div className="space-y-3 p-1">
              {selected && getMessages(selected.messages).map((msg, i) => (
                <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[85%] rounded-lg px-3.5 py-2.5 text-sm ${
                      msg.role === "user"
                        ? "bg-foreground text-background"
                        : "bg-secondary text-foreground"
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              ))}
              {selected && getMessages(selected.messages).length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-4">No messages in this conversation.</p>
              )}
            </div>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ConversationsPage;
