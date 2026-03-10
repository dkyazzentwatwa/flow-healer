"use client";

import { PropsWithChildren, useEffect } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface ModalProps {
  isOpen: boolean;
  title: string;
  onClose: () => void;
  className?: string;
}

export function Modal({ isOpen, title, onClose, className, children }: PropsWithChildren<ModalProps>) {
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-2 sm:px-4">
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />
      <div
        className={cn(
          "relative z-10 w-full max-w-3xl rounded-xl sm:rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl max-h-[90vh] overflow-hidden",
          className
        )}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <h3 className="text-lg font-semibold text-zinc-100">{title}</h3>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-4 sm:p-5 overflow-y-auto max-h-[calc(90vh-72px)]">
          {children}
        </div>
      </div>
    </div>
  );
}
