import type { ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { ApiRequestError } from "../api";
import { t } from "../i18n";

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const code = error instanceof ApiRequestError ? error.code : "generic";
  const known = t.errors as Record<string, { title: string; body: string }>;
  const msg = known[code] ?? {
    title: t.errors.generic.title,
    body: error instanceof ApiRequestError ? error.message : t.errors.generic.body,
  };
  return (
    <div role="alert" className="callout callout-error">
      <p className="callout-title">
        <span aria-hidden="true">✖ </span>
        {t.status.error}: {msg.title}
      </p>
      <p>{msg.body}</p>
      {onRetry && (
        <button type="button" onClick={onRetry}>
          {t.retry}
        </button>
      )}
    </div>
  );
}

/** Renders loading / error states, then children with the data. */
export function QueryState<T>({
  query,
  children,
}: {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending)
    return (
      <p role="status" className="muted">
        {t.loading}
      </p>
    );
  if (query.isError) return <ErrorBox error={query.error} onRetry={() => void query.refetch()} />;
  return <>{children(query.data)}</>;
}
