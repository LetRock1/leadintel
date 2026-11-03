import { useMutation } from "@tanstack/react-query";
import { cn, errorText } from "@xedu/shared/lib";
import { Button, IconButton } from "@xedu/shared/ui";
import { ArrowUp, MessageCircle, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router";
import { api } from "../api/client";
import type { ChatReply } from "../api/types";
import { useSession } from "../app/session";
import { onOpenAssistant } from "../lib/assistant-bus";
import { track } from "../lib/tracker";
import { CallbackForm } from "./CallbackForm";

interface Line {
  from: "you" | "assistant";
  text: string;
  reply?: ChatReply;
}

const STARTERS = [
  "How much does it cost?",
  "Which course suits me?",
  "Can I study while working?",
  "Talk to a counsellor",
];

/** The help assistant: answers from the course catalogue and the written policies only, and books a call. */
export function Assistant() {
  const { me } = useSession();
  const location = useLocation();
  const slug = /^\/courses\/([^/]+)$/.exec(location.pathname)?.[1] ?? null;
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [conversation, setConversation] = useState<string | null>(null);
  const [tracked, setTracked] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  const ask = useMutation({
    mutationFn: (message: string) =>
      api.post<ChatReply>("/chat", { message, conversation_id: conversation, course_slug: slug }),
    onSuccess: (r) => {
      setConversation(r.conversation_id);
      setLines((ls) => [...ls, { from: "assistant", text: r.reply, reply: r }]);
    },
    onError: (e) => setLines((ls) => [...ls, { from: "assistant", text: errorText(e) }]),
  });

  const send = (message: string) => {
    const m = message.trim();
    if (!m || ask.isPending) return;
    setLines((ls) => [...ls, { from: "you", text: m }]);
    setText("");
    ask.mutate(m);
    if (me && !tracked) {
      setTracked(true);
      void track("chat", slug);
    }
  };

  // other parts of the site open the assistant (with a first question) through the bus
  const sendLatest = useRef(send);
  useEffect(() => {
    sendLatest.current = send;
  });
  useEffect(
    () =>
      onOpenAssistant((q) => {
        setOpen(true);
        if (q) sendLatest.current(q);
      }),
    [],
  );
  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [lines.length, ask.isPending]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    send(text);
  };

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed bottom-5 right-5 z-30 flex items-center gap-2 rounded-full bg-brand px-4 py-3 text-[14px] font-medium text-on-brand shadow-overlay hover:bg-brand-strong"
        >
          <MessageCircle aria-hidden className="size-[18px]" />
          Ask a question
        </button>
      )}
      {open && (
        <section
          aria-label="Course help"
          className="fixed inset-0 z-40 flex flex-col bg-surface sm:inset-auto sm:bottom-5 sm:right-5 sm:h-[min(600px,calc(100vh-2.5rem))] sm:w-[380px] sm:rounded-lg sm:border sm:border-line sm:shadow-overlay"
        >
          <header className="flex items-start gap-3 border-b border-line px-4 py-3">
            <div className="min-w-0 flex-1">
              <h2 className="text-[15px] font-semibold text-ink">Course help</h2>
              <p className="text-[12.5px] text-muted">
                An automated assistant. It answers from the course pages and can book a counsellor.
              </p>
            </div>
            <IconButton label="Close course help" size="sm" onClick={() => setOpen(false)}>
              <X aria-hidden className="size-4" />
            </IconButton>
          </header>
          <div className="flex-1 overflow-y-auto px-4 py-3" aria-live="polite">
            {lines.length === 0 && (
              <div>
                <p className="text-[14px] text-ink-2">
                  Ask about fees, duration, the syllabus or which course fits you.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {STARTERS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => send(s)}
                      className="rounded-full border border-line-strong px-3 py-1.5 text-[13px] text-ink-2 hover:border-brand hover:text-ink"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <ol className="flex flex-col gap-3">
              {lines.map((l, i) => (
                <li key={i} className={cn("max-w-[88%] text-[14px]", l.from === "you" ? "ml-auto" : "")}>
                  <p
                    className={cn(
                      "whitespace-pre-line rounded-lg px-3 py-2",
                      l.from === "you" ? "bg-brand text-on-brand" : "bg-sunken text-ink",
                    )}
                  >
                    {l.text}
                  </p>
                  {l.reply && l.reply.links.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {l.reply.links.map((k) => (
                        <Link
                          key={k.to + k.label}
                          to={k.to}
                          onClick={() => setOpen(false)}
                          className="rounded-sm border border-line-strong px-2 py-1 text-[12.5px] font-medium text-brand-ink hover:bg-brand-soft"
                        >
                          {k.label}
                        </Link>
                      ))}
                    </div>
                  )}
                  {l.reply?.action?.type === "callback_form" && (
                    <div className="mt-2 rounded-md border border-line p-3">
                      <CallbackForm
                        courseSlug={l.reply.course_slug}
                        compact
                        onDone={(m) => setLines((ls) => [...ls, { from: "assistant", text: m }])}
                      />
                    </div>
                  )}
                </li>
              ))}
              {ask.isPending && (
                <li
                  className="w-fit rounded-lg bg-sunken px-3 py-2 text-[14px] text-muted"
                  aria-label="The assistant is answering"
                >
                  Writing an answer
                </li>
              )}
            </ol>
            <div ref={end} />
          </div>
          <form onSubmit={submit} className="flex items-end gap-2 border-t border-line p-3">
            <label htmlFor="assistant-input" className="sr-only">
              Your question
            </label>
            <textarea
              id="assistant-input"
              ref={input}
              rows={1}
              value={text}
              maxLength={1000}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) submit(e);
              }}
              placeholder="Type your question"
              className="max-h-32 min-h-9 flex-1 resize-none rounded-sm border border-line-strong bg-surface px-3 py-2 text-[14px] text-ink placeholder:text-muted focus:border-brand focus:outline-none"
            />
            <Button
              type="submit"
              variant="primary"
              aria-label="Send"
              disabled={!text.trim() || ask.isPending}
              className="size-9 px-0"
            >
              <ArrowUp aria-hidden className="size-4" />
            </Button>
          </form>
        </section>
      )}
    </>
  );
}
