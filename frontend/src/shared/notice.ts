import { create } from "zustand";

interface Notice {
  message: { text: string; error: boolean } | null;
  report: (text: string, error?: boolean) => void;
  clear: () => void;
}

/** Keep workflow feedback visible across feature boundaries without prop forwarding */
export const useNotice = create<Notice>((set) => ({
  message: null,
  report: (text, error = false) => set({ message: { text, error } }),
  clear: () => set({ message: null }),
}));
