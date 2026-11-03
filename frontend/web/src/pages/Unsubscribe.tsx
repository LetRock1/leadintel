import { useMutation } from "@tanstack/react-query";
import { errorText } from "@xedu/shared/lib";
import { Button, buttonClass, Notice } from "@xedu/shared/ui";
import { Link, useSearchParams } from "react-router";
import { api } from "../api/client";
import { AuthFrame } from "../components/AuthFrame";

/** The one-click unsubscribe link from every marketing email (/unsubscribe?t=<token>). */
export default function Unsubscribe() {
  const [params] = useSearchParams();
  const token = params.get("t") ?? "";
  const unsubscribe = useMutation({ mutationFn: () => api.post<{ message: string }>("/email/unsubscribe", { token }) });
  if (!token) {
    return (
      <AuthFrame
        title="Unsubscribe"
        description="This page needs the link from one of our emails. You can also switch emails off in your settings."
      >
        <Link to="/settings" className={buttonClass("primary", "lg")}>
          Open my settings
        </Link>
      </AuthFrame>
    );
  }
  return (
    <AuthFrame
      title={unsubscribe.isSuccess ? "No more emails about courses" : "Stop emails about courses?"}
      description="You will still get account emails such as sign-in codes and receipts."
    >
      {unsubscribe.isSuccess ? (
        <Notice tone="good">{unsubscribe.data.message}</Notice>
      ) : (
        <>
          {unsubscribe.isError && (
            <Notice tone="bad" className="mb-4">
              {errorText(unsubscribe.error)}
            </Notice>
          )}
          <Button variant="primary" size="lg" loading={unsubscribe.isPending} onClick={() => unsubscribe.mutate()}>
            Unsubscribe
          </Button>
        </>
      )}
    </AuthFrame>
  );
}
