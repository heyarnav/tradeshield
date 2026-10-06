"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";

interface State<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
}

/** GET a JSON endpoint and re-fetch whenever `path` changes or reload() is called. */
export function useApi<T>(path: string | null) {
  const [state, setState] = useState<State<T>>({
    data: null,
    error: null,
    loading: path !== null,
  });
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    if (!path) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true, error: null }));
    api<T>(path)
      .then((data) => {
        if (!cancelled) setState({ data, error: null, loading: false });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState({
          data: null,
          error: error instanceof ApiError ? error : new ApiError(0, "UNKNOWN", String(error)),
          loading: false,
        });
      });
    return () => {
      cancelled = true;
    };
  }, [path, nonce]);

  return { ...state, reload };
}
