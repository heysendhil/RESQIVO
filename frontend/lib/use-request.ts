"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, type FieldError } from "@/lib/api";

export type RequestState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | {
      status: "error";
      message: string;
      fieldErrors: FieldError[];
      /** HTTP status of a failed API call; absent for browser-side failures. */
      httpStatus?: number | null;
      /** The backend reported that AI features are not configured. */
      notConfigured?: boolean;
    };

/** Run one API call at a time. A newer call aborts the previous one, and the
 * result of an aborted or superseded call is ignored. */
export function useRequest<T>() {
  const [state, setState] = useState<RequestState<T>>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  const run = useCallback(async (call: (signal: AbortSignal) => Promise<T>) => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setState({ status: "loading" });
    try {
      const data = await call(current.signal);
      if (!current.signal.aborted) setState({ status: "success", data });
    } catch (error) {
      if (current.signal.aborted) return;
      setState({
        status: "error",
        message:
          error instanceof ApiError
            ? error.message
            : "An unexpected error occurred in the browser.",
        fieldErrors: error instanceof ApiError ? error.fieldErrors : [],
        httpStatus: error instanceof ApiError ? error.status : null,
        notConfigured: error instanceof ApiError && error.notConfigured,
      });
    }
  }, []);

  const reset = useCallback(() => {
    controller.current?.abort();
    setState({ status: "idle" });
  }, []);

  return { state, run, reset };
}
