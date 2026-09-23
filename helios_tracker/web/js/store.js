// Settings remembered in localStorage ("helios.<key>", JSON). Never throws: private mode, blocked
// storage or Node (the offline check) just get the defaults.
export const store = {
  get(k, d) { try { const v = localStorage.getItem("helios." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("helios." + k, JSON.stringify(v)); } catch { /* private mode */ } },
};
