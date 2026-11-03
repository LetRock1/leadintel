import { useQuery } from "@tanstack/react-query";
import { int, money } from "@xedu/shared/lib";
import { Badge, Segmented, type Tone } from "@xedu/shared/ui";
import { ArrowRight, CheckCircle2, Circle, Compass } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import { useSimulation } from "../api/queries";
import type { Role } from "../api/types";
import { useMe, useSession } from "../app/session";
import { PageHeader, Panel, Section } from "../components/page";
import { QueryView } from "../components/state";
import { doesByItself, FIRST_STEPS, glossary, JOBS, markStartSeen, type StartInfo } from "../lib/start";

interface Check {
  label: string;
  tone: Tone;
  state: string;
  text: string;
  to?: string;
  link?: string;
}

function checks(s: StartInfo, simulationOn: boolean | undefined, owner: boolean): Check[] {
  const out: Check[] = [
    s.email_sending
      ? { label: "Email", tone: "good", state: "Sending", text: "Emails and sign-up codes go out through Gmail." }
      : {
          label: "Email",
          tone: "warn",
          state: "Not set up",
          text: "Emails and sign-up codes are only recorded in the API's log, not sent. Add a Gmail address and app password to backend/.env and restart to send them.",
        },
    s.gemini
      ? {
          label: "Writing help",
          tone: "good",
          state: "On",
          text: "Gemini writes the message drafts; the facts come from the course catalogue.",
        }
      : {
          label: "Writing help",
          tone: "neutral",
          state: "Off",
          text: "Templates write the messages. A Gemini key in backend/.env turns on drafts in your own words; everything works without it.",
        },
    s.team_members > 1
      ? {
          label: "Team",
          tone: "good",
          state: `${int(s.team_members)} people`,
          text: "New leads are shared among the counsellors who take them.",
        }
      : {
          label: "Team",
          tone: "warn",
          state: "Only you",
          text: "Add your counsellors and marketers so calls and leads can be shared.",
          ...(owner ? { to: "/team", link: "Add people" } : {}),
        },
    {
      label: "Learners",
      tone: "neutral",
      state: `${int(s.learners.real)} real, ${int(s.learners.simulated)} simulated`,
      text:
        simulationOn === false
          ? "The simulated learners are paused. Everyone who signs up on the website is a real lead."
          : "Simulated learners use the website like real people so the CRM has something to do. Everyone who signs up on the website is a real lead.",
      to: "/simulation",
      link: "Simulated learners",
    },
    s.discount_budget === null
      ? {
          label: "Discount budget",
          tone: "neutral",
          state: "None",
          text: "A coupon goes out whenever it pays for itself. The owner can set a monthly limit in the planner.",
          to: "/planner",
          link: "Open the planner",
        }
      : {
          label: "Discount budget",
          tone: "good",
          state: `${money(s.discount_budget)} a month`,
          text: "The CRM spends it on the coupons that add the most for each rupee, so it lasts the month.",
          to: "/planner",
          link: "Open the planner",
        },
  ];
  return out;
}

/** The first page for a new team member: what the CRM does, where to begin, what is set up, and its words. */
export default function Start() {
  const me = useMe();
  const { can } = useSession();
  const [job, setJob] = useState<Role>(me.role);
  const info = useQuery({ queryKey: ["start"], queryFn: () => api.get<StartInfo>("/start") });
  const sim = useSimulation(30_000);
  useEffect(() => markStartSeen(), []);

  return (
    <>
      <PageHeader
        title="Start here"
        description="What this CRM does for you, where to begin, and the words it uses. It takes about five minutes."
      />
      <QueryView query={info} what="the guide">
        {(s) => (
          <>
            <Section id="does" title="What the CRM does by itself">
              <Panel>
                <ul className="grid gap-3">
                  {doesByItself(s.rules).map((line) => (
                    <li key={line} className="flex gap-3 text-[14px] text-ink-2">
                      <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0 text-good" />
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-4 border-t border-line pt-3 text-[13.5px] text-muted">
                  Your part: make the calls it gives you, answer people who ask, run campaigns and tests, and decide
                  what it cannot (a discount budget, the size of the team).
                </p>
              </Panel>
            </Section>

            <Section
              id="first-steps"
              title="Your first steps"
              description="Pick your job to see where to begin."
              actions={<Segmented label="Job" options={JOBS} value={job} onChange={setJob} />}
            >
              <ol className="grid gap-3 md:grid-cols-2">
                {FIRST_STEPS[job].map((step, i) => (
                  <li key={step.title}>
                    <Panel className="flex h-full gap-3">
                      <span
                        aria-hidden
                        className="num flex size-7 shrink-0 items-center justify-center rounded-full bg-brand-soft text-[13px] font-semibold text-brand-ink"
                      >
                        {i + 1}
                      </span>
                      <div className="min-w-0">
                        <p className="text-[14px] font-medium text-ink">{step.title}</p>
                        <p className="mt-1 text-[13.5px] text-ink-2">{step.text}</p>
                        <Link
                          to={step.to}
                          className="mt-2 inline-flex items-center gap-1 text-[13.5px] font-medium text-brand-ink hover:underline"
                        >
                          {step.link}
                          <ArrowRight aria-hidden className="size-3.5" />
                        </Link>
                      </div>
                    </Panel>
                  </li>
                ))}
              </ol>
            </Section>

            <Section id="setup" title="Is everything set up?" description="Read from this CRM right now.">
              <Panel padded={false}>
                <ul className="divide-y divide-line">
                  {checks(s, sim.data?.enabled, can("team")).map((c) => (
                    <li key={c.label} className="flex flex-wrap items-start gap-x-4 gap-y-1.5 px-4 py-3">
                      <span className="flex w-40 shrink-0 items-center gap-2 text-[14px] font-medium text-ink">
                        <Circle aria-hidden className="size-2.5 fill-current text-muted" />
                        {c.label}
                      </span>
                      <span className="min-w-0 flex-1 basis-64 text-[13.5px] text-ink-2">
                        <Badge tone={c.tone}>{c.state}</Badge> <span className="ml-1">{c.text}</span>
                        {c.to && c.link && (
                          <Link to={c.to} className="ml-2 font-medium text-brand-ink hover:underline">
                            {c.link}
                          </Link>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </Panel>
            </Section>

            <Section id="words" title="Words you will see">
              <Panel>
                <dl className="grid gap-x-8 gap-y-3 md:grid-cols-2">
                  {glossary(s.rules).map((w) => (
                    <div key={w.term}>
                      <dt className="text-[14px] font-medium text-ink">{w.term}</dt>
                      <dd className="mt-0.5 text-[13.5px] text-ink-2">{w.meaning}</dd>
                    </div>
                  ))}
                </dl>
              </Panel>
            </Section>

            <p className="mt-8 flex items-center gap-2 text-[13px] text-muted">
              <Compass aria-hidden className="size-4" />
              This guide stays in the menu under Start here. Ask the CRM answers questions about your data in plain
              words.
            </p>
          </>
        )}
      </QueryView>
    </>
  );
}
