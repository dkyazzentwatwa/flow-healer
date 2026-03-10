"use client";

import { useState } from "react";
import { cn, getSignalColorClass, formatNumber } from "@/lib/utils";
import { Modal } from "@/components/Modal";
import type { Indicator } from "@/lib/types";

interface SignalCardProps {
  indicator: Indicator;
}

export function SignalCard({ indicator }: SignalCardProps) {
  const signalClass = getSignalColorClass(indicator.signal);
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <div className="card cursor-pointer hover:bg-zinc-900/60 transition-colors" onClick={() => setIsOpen(true)}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-medium text-zinc-200">{indicator.name}</h3>
        <span
          className={cn(
            "px-2 py-0.5 rounded text-xs font-medium uppercase",
            signalClass
          )}
        >
          {indicator.signal.replace("_", " ")}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-zinc-500">Value:</span>
          <span className="ml-2 text-zinc-300">
            {formatNumber(indicator.value, 4)}
          </span>
        </div>
        <div>
          <span className="text-zinc-500">Score:</span>
          <span
            className={cn(
              "ml-2",
              indicator.score > 0
                ? "text-green-400"
                : indicator.score < 0
                ? "text-red-400"
                : "text-zinc-400"
            )}
          >
            {indicator.score > 0 ? "+" : ""}
            {indicator.score}
          </span>
        </div>
      </div>

      {indicator.details && Object.keys(indicator.details).length > 0 && (
        <div className="mt-2 pt-2 border-t border-zinc-800">
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
            {Object.entries(indicator.details).map(([key, value]) => (
              <span key={key}>
                {key}: {formatNumber(value as number, 2)}
              </span>
            ))}
          </div>
        </div>
      )}
      </div>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        title={`Indicator • ${indicator.name}`}
      >
        <div className="space-y-4 text-sm">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-zinc-500">Signal</p>
              <p className="text-zinc-100 uppercase">{indicator.signal}</p>
            </div>
            <div>
              <p className="text-zinc-500">Score</p>
              <p className={cn(
                "font-mono",
                indicator.score > 0
                  ? "text-green-400"
                  : indicator.score < 0
                  ? "text-red-400"
                  : "text-zinc-400"
              )}>
                {indicator.score > 0 ? "+" : ""}
                {indicator.score}
              </p>
            </div>
            <div>
              <p className="text-zinc-500">Value</p>
              <p className="text-zinc-100 font-mono">
                {formatNumber(indicator.value, 6)}
              </p>
            </div>
          </div>
          <div>
            <p className="text-zinc-500">Details</p>
            <pre className="text-xs text-zinc-300 bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 overflow-x-auto">
              {indicator.details
                ? JSON.stringify(indicator.details, null, 2)
                : "—"}
            </pre>
          </div>
        </div>
      </Modal>
    </>
  );
}
