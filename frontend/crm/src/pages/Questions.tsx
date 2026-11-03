import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dateTime, errorText, relative } from "@xedu/shared/lib";
import { Button, EmptyState, Field, Textarea, useToast } from "@xedu/shared/ui";
import { MessageCircleQuestion } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import { useCourses } from "../api/queries";
import { PageHeader } from "../components/page";
import { Loading, LoadError } from "../components/state";

interface Question {
  id: number;
  user_id: number;
  course_slug: string;
  question: string;
  user_name: string;
  created_at: string;
}

function Answer({ q }: { q: Question }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [text, setText] = useState("");
  const send = useMutation({
    mutationFn: () => api.post<{ message: string }>("/qna/answer", { qna_id: q.id, answer: text }),
    onSuccess: (r) => {
      toast({ tone: "good", text: r.message });
      void qc.invalidateQueries({ queryKey: ["qna"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  return (
    <form
      className="mt-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) send.mutate();
      }}
    >
      <Field label="Answer" hint="Published on the course page for everyone, and emailed to the person who asked.">
        <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} maxLength={4000} />
      </Field>
      <Button
        type="submit"
        variant="primary"
        size="sm"
        className="mt-2"
        loading={send.isPending}
        disabled={!text.trim()}
      >
        Publish the answer
      </Button>
    </form>
  );
}

export default function Questions() {
  const courses = useCourses();
  const list = useQuery({
    queryKey: ["qna"],
    queryFn: () => api.get<{ questions: Question[] }>("/qna"),
    refetchInterval: 30_000,
  });
  return (
    <>
      <PageHeader
        title="Course questions"
        description="Questions people asked on course pages that are not answered yet. An answer appears on the course page for everyone."
      />
      {list.isPending ? (
        <Loading label="Loading the questions" />
      ) : list.isError ? (
        <LoadError error={list.error} what="the questions" retry={() => void list.refetch()} />
      ) : list.data.questions.length === 0 ? (
        <div className="rounded-md border border-line bg-surface px-4">
          <EmptyState icon={MessageCircleQuestion} title="Every question has an answer">
            New questions from course pages appear here.
          </EmptyState>
        </div>
      ) : (
        <ul className="flex max-w-3xl flex-col gap-4">
          {list.data.questions.map((q) => (
            <li key={q.id} className="rounded-md border border-line bg-surface px-4 py-3.5">
              <div className="flex flex-wrap items-baseline gap-x-3 text-[12.5px] text-muted">
                <span className="font-medium text-ink-2">{courses.title(q.course_slug)}</span>
                <span>{q.user_name}</span>
                <span className="ml-auto" title={dateTime(q.created_at)}>
                  {relative(q.created_at)}
                </span>
              </div>
              <p className="mt-1.5 text-[14.5px] text-ink">{q.question}</p>
              <Answer q={q} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
