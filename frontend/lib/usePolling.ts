"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Loads data and re-fetches every `intervalMs` while `shouldPoll(data)` is
 * true — e.g. while a document is still in the processing queue.
 */
export function usePolling<T>(load: () => Promise<T>, shouldPoll: (data: T) => boolean, intervalMs = 2000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load; // always call the latest loader without re-creating `refresh`
  });

  const refresh = useCallback(async () => {
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (data === null || !shouldPoll(data)) return;
    const timer = setTimeout(() => void refresh(), intervalMs);
    return () => clearTimeout(timer);
  }, [data, shouldPoll, intervalMs, refresh]);

  return { data, error, refresh, setData };
}
