import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { errorText, relative, time } from "@xedu/shared/lib";
import { Button, buttonClass, Notice, useToast } from "@xedu/shared/ui";
import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api/client";
import { useSession } from "../app/session";
import { PageHeader } from "../components/page";

interface Draft {
  type: "email" | "ab_test";
  lead_id?: number;
  to?: string;
  subject?: string;
  body?: string;
  name?: string;
  tier?: string;
  metric?: "purchase" | "click";
  hypothesis?: string;
  control_share?: number;
  mde?: number;
  variants?: { label: string; subject: string; body: string; offer_pct: number }[];
}

interface Answer {
  question: string;
  intent: string;
  answer: string;
  tools: { name: string; about: string | null; source: string; read_at: string }[];
  drafts: Draft[];
  links: { type: "lead" | "page"; lead_id?: number; to?: string; label: string }[];
  used_gemini: boolean;
}

interface Info {
  suggestions: string[];
  tools: Record<string, string>;
  gemini: boolean;
  recent: { asked_at: string; question: string; intent: string; used_gemini: number }[];
}

function DraftCard({ d }: { d: Draft }) {
  const { can } = useSession();
  const toast = useToast();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const create = useMutation({
    mutationFn: () =>
      api.post<{ id: number }>("/ab-tests", {
        name: d.name,
        tier: d.tier,
        hypothesis: d.hypothesis,
        metric: d.metric,
        control_share: d.control_share,
        mde: d.mde,
        variants: d.variants,
      }),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ["ab-tests"] });
      navigate(`/ab-tests/${r.id}`);
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  if (d.type === "email") {
    return (
      <div className="mt-3 rounded-md border border-line bg-surface px-4 py-3">
        <p className="text-[12.5px] text-muted">Draft email to {d.to}</p>
        <p className="mt-1 text-[14px] font-medium text-ink">{d.subject}</p>
        <p className="mt-1.5 whitespace-pre-line text-[13.5px] text-ink-2">{d.body}</p>
        {d.lead_id && (
          <Link to={`/leads/${d.lead_id}`} className={buttonClass("secondary", "sm", "mt-3")}>
            Open the lead to send it
          </Link>
        )}
      </div>
    );
  }
  return (
    <div className="mt-3 rounded-md border border-line bg-surface px-4 py-3">
      <p className="text-[12.5px] text-muted">Draft A/B test for {d.tier}</p>
      <p className="mt-1 text-[14px] font-medium text-ink">{d.name}</p>
      <ul className="mt-1.5 text-[13.5px] text-ink-2">
        {d.variants?.map((v, i) => (
          <li key={v.label}>
            {String.fromCharCode(65 + i)}: {v.label}, &ldquo;{v.subject}&rdquo;
          </li>
        ))}
      </ul>
      {can("marketing") && (
        <Button size="sm" className="mt-3" loading={create.isPending} onClick={() => create.mutate()}>
          Save it as a draft test
        </Button>
      )}
    </div>
  );
}

export default function Ask() {
  const qc = useQueryClient();
  const [question, setQuestion] = useState("");
  const [thread, setThread] = useState<Answer[]>([]);
  const end = useRef<HTMLDivElement>(null);
  const info = useQuery({ queryKey: ["copilot"], queryFn: () => api.get<Info>("/copilot") });
  const ask = useMutation({
    mutationFn: (q: string) => api.post<Answer>("/copilot", { question: q }),
    onSuccess: (a) => {
      setThread((t) => [...t, a]);
      setQuestion("");
      void qc.invalidateQueries({ queryKey: ["copilot"] });
    },
  });
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [thread.length]);

  const submit = (e?: FormEvent, q = question) => {
    e?.preventDefault();
    const s = q.trim();
    if (s && !ask.isPending) ask.mutate(s);
  };

  return (
    <>
      <PageHeader
        title="Ask the CRM"
        description={
          info.data?.gemini
            ? "Ask about the live data in plain words. Every number comes from the database; Gemini only phrases the answer."
            : "Ask about the live data in plain words. Answers are built from the database by fixed rules, so every number can be checked."
        }
      />
      <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0">
          {thread.length === 0 && info.data && (
            <div className="mb-6">
              <p className="mb-2 text-[13px] text-muted">Try one of these</p>
              <div className="flex flex-wrap gap-2">
                {info.data.suggestions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => submit(undefined, s)}
                    className="rounded-full border border-line-strong bg-surface px-3 py-1.5 text-[13px] text-ink-2 hover:border-brand hover:text-ink"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          <ol className="flex flex-col gap-6" aria-live="polite">
            {thread.map((a, i) => (
              <li key={i}>
                <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-brand-soft px-3.5 py-2 text-[14px] text-ink">
                  {a.question}
                </p>
                <div className="mt-3 max-w-[72ch]">
                  <p className="whitespace-pre-line text-[14px] leading-relaxed text-ink">{a.answer}</p>
                  {a.links.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {a.links.map((l) => (
                        <Link
                          key={l.label}
                          to={l.type === "lead" ? `/leads/${l.lead_id}` : (l.to ?? "/")}
                          className={buttonClass("secondary", "sm")}
                        >
                          {l.label}
                        </Link>
                      ))}
                    </div>
                  )}
                  {a.drafts.map((d, j) => (
                    <DraftCard key={j} d={d} />
                  ))}
                  <p className="mt-2 text-[12px] text-muted">
                    Read from {a.tools.map((t) => t.source).join(", ")} at {time(a.tools[0]?.read_at)}
                    {a.used_gemini ? ". Phrased by Gemini." : "."}
                  </p>
                </div>
              </li>
            ))}
          </ol>
          {ask.isError && (
            <Notice tone="bad" className="mt-4">
              {errorText(ask.error)}
            </Notice>
          )}
          <div ref={end} />
          <form
            onSubmit={submit}
            className="sticky bottom-4 mt-6 flex items-end gap-2 rounded-lg border border-line-strong bg-surface p-2 shadow-overlay"
          >
            <label htmlFor="ask" className="sr-only">
              Your question
            </label>
            <textarea
              id="ask"
              rows={1}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) submit(e);
              }}
              maxLength={500}
              placeholder="Who should we call today?"
              className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-[14px] text-ink placeholder:text-muted focus:outline-none"
            />
            <Button
              type="submit"
              variant="primary"
              aria-label="Ask"
              loading={ask.isPending}
              disabled={!question.trim()}
              className="size-9 px-0"
            >
              {!ask.isPending && <ArrowUp aria-hidden className="size-4" />}
            </Button>
          </form>
        </div>
        <aside className="flex flex-col gap-6">
          {info.data && info.data.recent.length > 0 && (
            <div>
              <h2 className="mb-2 text-[13px] font-semibold text-ink">Asked recently</h2>
              <ul className="flex flex-col gap-1">
                {info.data.recent.map((r, i) => (
                  <li key={i}>
                    <button
                      type="button"
                      className="w-full rounded-sm px-2 py-1.5 text-left text-[13px] text-ink-2 hover:bg-sunken hover:text-ink"
                      onClick={() => submit(undefined, r.question)}
                    >
                      {r.question}
                      <span className="block text-[12px] text-muted">{relative(r.asked_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {info.data && (
            <div>
              <h2 className="mb-2 text-[13px] font-semibold text-ink">What it can answer</h2>
              <ul className="flex flex-col gap-1.5 text-[13px] text-muted">
                {Object.entries(info.data.tools)
                  .filter(([k]) => k !== "help")
                  .map(([k, v]) => (
                    <li key={k}>{v}</li>
                  ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </>
  );
}
