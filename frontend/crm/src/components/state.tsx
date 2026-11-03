import type { UseQueryResult } from "@tanstack/react-query";
import { errorText } from "@xedu/shared/lib";
import { Button, Notice, Spinner } from "@xedu/shared/ui";
import type { ReactNode } from "react";

export function Loading({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <div className={className ?? "flex min-h-40 items-center justify-center"}>
      <Spinner label={label} />
    </div>
  );
}

export function LoadError({ error, retry, what }: { error: unknown; retry?: () => void; what?: string }) {
  return (
    <Notice
      tone="bad"
      title={what ? `Could not load ${what}` : "Could not load this"}
      action={
        retry ? (
          <Button size="sm" onClick={retry}>
            Try again
          </Button>
        ) : undefined
      }
    >
      {errorText(error)}
    </Notice>
  );
}

/** Shows a spinner while the first answer is on its way, an error with a retry, or the content. */
export function QueryView<T>({
  query,
  children,
  what,
  loading,
}: {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  what?: string;
  loading?: ReactNode;
}) {
  if (query.isPending) return <>{loading ?? <Loading label={what ? `Loading ${what}` : "Loading"} />}</>;
  if (query.isError) return <LoadError error={query.error} retry={() => void query.refetch()} what={what} />;
  return <>{children(query.data)}</>;
}
