"use client";

import { useTradingStore } from "@/lib/store";
import { AlertTriangle, X, RefreshCw } from "lucide-react";

export function ErrorBanner() {
  const { error, clearError, isConnected, checkConnection } = useTradingStore();

  if (!error && isConnected) return null;

  return (
    <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <h3 className="font-medium text-red-400">
            {!isConnected ? "Connection Error" : "Error"}
          </h3>
          <p className="text-sm text-red-300/80 mt-1">
            {!isConnected
              ? "Cannot connect to the trading API. Make sure the Python server is running on http://localhost:8000"
              : error}
          </p>
          {!isConnected && (
            <div className="mt-3 space-y-2 text-sm text-zinc-400">
              <p>To start the server, run:</p>
              <code className="block bg-zinc-900 px-3 py-2 rounded text-green-400 font-mono text-xs">
                python -m uvicorn api.main:app --reload --port 8000
              </code>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={checkConnection}
            className="p-2 hover:bg-zinc-800 rounded-lg transition-colors"
            title="Retry connection"
          >
            <RefreshCw className="w-4 h-4 text-zinc-400" />
          </button>
          {error && (
            <button
              onClick={clearError}
              className="p-2 hover:bg-zinc-800 rounded-lg transition-colors"
            >
              <X className="w-4 h-4 text-zinc-400" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
