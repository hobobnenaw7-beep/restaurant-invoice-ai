// Lightweight event bus for cross-page data synchronization.
// When any page mutates data (create/update/delete), it calls emit().
// The dashboard (or any listener) re-fetches fresh data on the next event.

const listeners = new Set();

export const dataEvents = {
  subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
  emit() {
    listeners.forEach(fn => fn());
  },
};
