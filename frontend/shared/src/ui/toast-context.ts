import { createContext, useContext } from "react";

export interface ToastItem {
  id: number;
  tone: "good" | "bad" | "info";
  text: string;
}

export const ToastContext = createContext<((t: Omit<ToastItem, "id">) => void) | null>(null);

/** Shows a short confirmation ("Saved", "Email sent"). Errors that need attention belong in the page as a Notice. */
export function useToast() {
  const show = useContext(ToastContext);
  if (!show) throw new Error("useToast must be used inside ToastProvider");
  return show;
}
