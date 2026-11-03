import { useMutation, useQuery } from "@tanstack/react-query";
import { errorText } from "@xedu/shared/lib";
import { Button, buttonClass, Checkbox, Field, Input, Notice, Spinner } from "@xedu/shared/ui";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import type { Course } from "../api/types";
import { useMe } from "../app/session";
import { AuthFrame } from "../components/AuthFrame";
import { leadSource } from "../lib/tracker";

/** An enquiry about one course: always answered by email; a counsellor may call if they left a number. */
export default function Enquiry() {
  const { slug = "" } = useParams();
  const me = useMe();
  const course = useQuery({ queryKey: ["course", slug], queryFn: () => api.get<Course>(`/courses/${slug}`) });
  const [phone, setPhone] = useState(me.profile?.phone ?? "");
  const [whatsapp, setWhatsapp] = useState(Boolean(me.profile?.whatsapp_opt_in));
  const send = useMutation({
    mutationFn: () =>
      api.post<{ message: string }>("/enquiry", {
        course_slug: slug,
        course_type: course.data?.title,
        phone: phone.trim() || null,
        whatsapp_opt_in: whatsapp ? 1 : 0,
        lead_source: leadSource(),
      }),
  });
  if (course.isPending) return <Spinner className="m-12" />;
  if (course.isError) return <p className="m-12 text-muted">This course could not be found.</p>;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    send.mutate();
  };
  if (send.isSuccess) {
    return (
      <AuthFrame title="Enquiry sent" description={send.data.message}>
        <Link to={`/courses/${slug}`} className={buttonClass("primary", "lg")}>
          Back to {course.data.title}
        </Link>
      </AuthFrame>
    );
  }
  return (
    <AuthFrame
      title={`Ask about ${course.data.title}`}
      description="We email you the details: dates, fees and the next steps. Add a number if you would like a call."
    >
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        {send.isError && <Notice tone="bad">{errorText(send.error)}</Notice>}
        <Field label="Phone" optional>
          <Input
            type="tel"
            autoComplete="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+91 98765 43210"
            maxLength={20}
          />
        </Field>
        <Checkbox
          checked={whatsapp}
          onChange={(e) => setWhatsapp(e.target.checked)}
          label="WhatsApp me about this course"
          description="You can switch this off at any time in your settings."
          disabled={!phone.trim()}
        />
        <Button type="submit" variant="primary" size="lg" loading={send.isPending}>
          Send the enquiry
        </Button>
      </form>
    </AuthFrame>
  );
}
