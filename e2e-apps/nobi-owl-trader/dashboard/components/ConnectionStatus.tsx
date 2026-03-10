"use client";

import { useEffect } from "react";
import { useTradingStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Wifi, WifiOff } from "lucide-react";

export function ConnectionStatus() {
  const { isConnected, exchange, isPaperTrading, error, checkConnection } =
    useTradingStore();

  useEffect(() => {
    checkConnection();
    // Check connection every 30 seconds
    const interval = setInterval(checkConnection, 30000);
    return () => clearInterval(interval);
  }, [checkConnection]);

  return (
    <div className="flex items-center gap-4">
      <div
        className={cn(
          "flex items-center gap-2 px-3 py-1.5 rounded-full text-sm",
          isConnected
            ? "bg-green-400/10 text-green-400"
            : "bg-red-400/10 text-red-400"
        )}
      >
        {isConnected ? (
          <Wifi className="w-4 h-4" />
        ) : (
          <WifiOff className="w-4 h-4" />
        )}
        {isConnected ? "Connected" : "Disconnected"}
      </div>

      {isConnected && (
        <>
          <span className="text-zinc-500">|</span>
          <span className="text-sm text-zinc-400 capitalize">{exchange}</span>
          {isPaperTrading && (
            <span className="px-2 py-0.5 text-xs bg-yellow-400/10 text-yellow-400 rounded">
              Paper
            </span>
          )}
        </>
      )}

      {error && (
        <span className="text-sm text-red-400 ml-2">{error}</span>
      )}
    </div>
  );
}
