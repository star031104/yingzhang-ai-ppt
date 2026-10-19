import { create } from "zustand";

export type ToastTone = "info" | "success" | "error";
export type Toast = { id: number; text: string; tone: ToastTone };

type ToastState = {
  toasts: Toast[];
  push: (text: string, tone?: ToastTone) => void;
  dismiss: (id: number) => void;
};

let nextId = 1;

export const useToasts = create<ToastState>((set, get) => ({
  toasts: [],
  push: (text, tone = "info") => {
    const id = nextId++;
    set({ toasts: [...get().toasts.slice(-3), { id, text, tone }] });
    window.setTimeout(() => get().dismiss(id), tone === "error" ? 7000 : 4500);
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((toast) => toast.id !== id) }),
}));

export const toast = (text: string, tone?: ToastTone) => useToasts.getState().push(text, tone);
