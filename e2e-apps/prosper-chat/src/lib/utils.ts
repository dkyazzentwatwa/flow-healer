import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function mergeClasses(className: string) {
  return twMerge(className);
}

export function cn(...inputs: ClassValue[]) {
  return mergeClasses(clsx(inputs));
}
