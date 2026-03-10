"use client";

import { useEffect, useRef, useState } from "react";
import { useTradingStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { Modal } from "@/components/Modal";
import { 
  Terminal, 
  Trash2, 
  RefreshCw, 
  Clock,
  AlertCircle,
  Zap,
  Info
} from "lucide-react";

export function LogViewer() {
  const { logs, fetchLogs, clearLogs, isLoading } = useTradingStore();
  const [levelFilter, setLevelFilter] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [selectedLog, setSelectedLog] = useState<any | null>(null);

  useEffect(() => {
    fetchLogs(100, levelFilter || undefined);
    const interval = setInterval(() => {
      fetchLogs(100, levelFilter || undefined);
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchLogs, levelFilter]);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const formatTimestamp = (ts: number) => {
    return new Date(ts).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const getLevelStyles = (level: string) => {
    switch (level.toUpperCase()) {
      case "ERROR": return "text-red-400";
      case "WARNING": return "text-yellow-400";
      case "TRADE": return "text-green-400 font-bold";
      case "INFO": return "text-blue-400";
      default: return "text-zinc-400";
    }
  };

  const getLevelIcon = (level: string) => {
    switch (level.toUpperCase()) {
      case "ERROR": return <AlertCircle className="w-3.5 h-3.5" />;
      case "WARNING": return <AlertCircle className="w-3.5 h-3.5 text-yellow-500" />;
      case "TRADE": return <Zap className="w-3.5 h-3.5 text-green-500" />;
      case "INFO": return <Info className="w-3.5 h-3.5 text-blue-500" />;
      default: return null;
    }
  };

  return (
    <CollapsibleSection
      title="Execution Logs"
      icon={<Terminal className="w-4 h-4 text-zinc-400" />}
      className="p-0 overflow-hidden border-zinc-800 bg-zinc-950"
      headerClassName="px-4 py-3 border-b border-zinc-800 bg-zinc-900/50 flex-col gap-2 sm:flex-row"
      bodyClassName="p-0"
      headerRight={
        <div className="flex flex-wrap items-center gap-2">
          {isLoading.logs && (
            <RefreshCw className="w-3 h-3 animate-spin text-zinc-500" />
          )}
          <select 
            value={levelFilter || ""}
            onChange={(e) => setLevelFilter(e.target.value || null)}
            className="bg-zinc-800 text-xs text-zinc-300 border border-zinc-700 rounded px-2 py-1 outline-none"
          >
            <option value="">All Levels</option>
            <option value="INFO">Info</option>
            <option value="TRADE">Trades</option>
            <option value="WARNING">Warnings</option>
            <option value="ERROR">Errors</option>
          </select>
          
          <button 
            onClick={() => setAutoScroll(!autoScroll)}
            className={cn(
              "px-2 py-1 text-xs rounded transition-colors",
              autoScroll ? "bg-green-500/10 text-green-500" : "bg-zinc-800 text-zinc-500"
            )}
          >
            Auto-scroll
          </button>
          
          <button 
            onClick={() => { if(confirm("Clear logs?")) clearLogs(); }}
            className="p-1.5 hover:bg-red-500/10 hover:text-red-400 text-zinc-500 rounded transition-all"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      }
    >
      <div 
        ref={scrollRef}
        className="h-[360px] sm:h-[500px] overflow-y-auto p-3 sm:p-4 font-mono text-sm space-y-1.5 scrollbar-thin scrollbar-thumb-zinc-800"
      >
        {logs.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-zinc-600">
            <Clock className="w-8 h-8 mb-2 opacity-20" />
            <p>No execution logs found</p>
          </div>
        ) : (
          logs.slice().reverse().map((log) => (
            <div
              key={log.id}
              className="flex gap-3 hover:bg-zinc-900/50 transition-colors py-0.5 px-1 rounded cursor-pointer"
              onClick={() => setSelectedLog(log)}
            >
              <span className="text-zinc-600 shrink-0">[{formatTimestamp(log.timestamp)}]</span>
              <span className={cn("shrink-0 uppercase w-16 text-[10px] mt-0.5 flex items-center gap-1", getLevelStyles(log.level))}>
                {getLevelIcon(log.level)}
                {log.level}
              </span>
              <span className="text-zinc-300 break-all">{log.message}</span>
              {log.symbol && (
                <span className="text-zinc-500 text-[10px] border border-zinc-800 px-1 rounded shrink-0 h-4 mt-0.5">
                  {log.symbol}
                </span>
              )}
            </div>
          ))
        )}
      </div>

      <Modal
        isOpen={!!selectedLog}
        onClose={() => setSelectedLog(null)}
        title={`Log Details${selectedLog?.id ? ` • #${selectedLog.id}` : ""}`}
      >
        {selectedLog && (
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-zinc-500">Time</p>
                <p className="text-zinc-100 font-mono">
                  {new Date(selectedLog.timestamp).toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">Level</p>
                <p className="text-zinc-100 uppercase">{selectedLog.level}</p>
              </div>
              <div>
                <p className="text-zinc-500">Symbol</p>
                <p className="text-zinc-100">{selectedLog.symbol || "—"}</p>
              </div>
              <div>
                <p className="text-zinc-500">Rule</p>
                <p className="text-zinc-100">{selectedLog.ruleId || "—"}</p>
              </div>
            </div>
            <div>
              <p className="text-zinc-500">Message</p>
              <p className="text-zinc-100">{selectedLog.message}</p>
            </div>
            <div>
              <p className="text-zinc-500">Details</p>
              <pre className="text-xs text-zinc-300 bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 overflow-x-auto">
                {selectedLog.details
                  ? typeof selectedLog.details === "string"
                    ? selectedLog.details
                    : JSON.stringify(selectedLog.details, null, 2)
                  : "—"}
              </pre>
            </div>
          </div>
        )}
      </Modal>
    </CollapsibleSection>
  );
}
