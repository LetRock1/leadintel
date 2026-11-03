import { pct } from "@xedu/shared/lib";
import type { Role } from "../api/types";

/** What the Start here page needs from the API: is everything set up, and the rules it explains. */
export interface StartInfo {
  email_sending: boolean;
  gemini: boolean;
  team_members: number;
  learners: { real: number; simulated: number };
  rules: { control_share: number; learning_steps: number; daily_calls: number; outcome_window_days: number };
  discount_budget: number | null;
}

export interface StartStep {
  title: string;
  text: string;
  to: string;
  link: string;
}

export const JOBS: { value: Role; label: string }[] = [
  { value: "counsellor", label: "Counsellor" },
  { value: "marketing", label: "Marketing" },
  { value: "admin", label: "Owner" },
];

/** The first things to do, by job, in the order a new person should do them. */
export const FIRST_STEPS: Record<Role, StartStep[]> = {
  counsellor: [
    {
      title: "Make today's calls",
      text: "Today's actions lists the calls the CRM chose for you, the most valuable first. Press Call now, talk, and record what happened.",
      to: "/actions",
      link: "Open Today's actions",
    },
    {
      title: "Answer call-backs and course questions",
      text: "People who asked for a call or asked about a course on the website are waiting here.",
      to: "/callbacks",
      link: "Open Call-backs",
    },
    {
      title: "Work the pipeline",
      text: "Each card shows the best step and how much it raises the chance of buying. Press Do it to take that step now.",
      to: "/pipeline",
      link: "Open the pipeline",
    },
    {
      title: "Look a lead up",
      text: "Type a name or an email in the search box at the top. A lead's page shows the score, the reasons and the best next step.",
      to: "/leads",
      link: "Open Leads",
    },
  ],
  marketing: [
    {
      title: "See how admissions are going",
      text: "Overview shows sign-ups, purchases and revenue, and what comes in anyway from the open leads.",
      to: "/overview",
      link: "Open the overview",
    },
    {
      title: "Find the leads worth working",
      text: "The pipeline puts first the leads where a step makes the most difference, and marks those who need no discount.",
      to: "/pipeline",
      link: "Open the pipeline",
    },
    {
      title: "Send a campaign",
      text: "Email a whole audience. A random hold-out group gets nothing, so you see what the email really added.",
      to: "/campaigns",
      link: "Open Campaigns",
    },
    {
      title: "Test two emails",
      text: "An A/B test sends each version to part of the audience and tells you which one won, once it is sure.",
      to: "/ab-tests",
      link: "Open A/B tests",
    },
    {
      title: "Give coupons that pay",
      text: "Before you give a coupon, the CRM shows how much it raises the chance of buying, or whether it would mostly go to someone who would buy anyway.",
      to: "/coupons",
      link: "Open Coupons",
    },
  ],
  admin: [
    {
      title: "Add your team",
      text: "Add your counsellors and marketers. Each one gets a role and sees only what that role needs.",
      to: "/team",
      link: "Open Team",
    },
    {
      title: "Plan the month",
      text: "The planner shows the month in rupees, what the team's work adds, whether another counsellor would pay for themselves, and lets you set a discount budget.",
      to: "/planner",
      link: "Open the planner",
    },
    {
      title: "Check that the score is honest",
      text: "The learning loop compares what the score expected with what leads nobody contacted really did.",
      to: "/learning",
      link: "Open the learning loop",
    },
    {
      title: "Ask the CRM",
      text: "Ask in plain words, for example “Should we hire another counsellor?”. The answers come from your own data.",
      to: "/ask",
      link: "Ask a question",
    },
  ],
};

/** What the CRM does by itself, with this CRM's own numbers. */
export function doesByItself(r: StartInfo["rules"]): string[] {
  return [
    `Scores every learner the moment they do something on the website: the score is their chance to buy within ${r.outcome_window_days} days if nobody contacts them.`,
    "Picks the best next step for each learner (an email, a 10% or 20% coupon, a call, a WhatsApp message, or nothing): the one that helps most after its cost and any discount.",
    "Sends the emails by itself and puts the calls in Today's actions, at most " +
      `${r.daily_calls} a day, for the leads where a call adds the most.`,
    `Never contacts ${pct(r.control_share)} of learners (the control group), so it can show what the team's work really adds.`,
    "Learns from every result and switches to a new score only when it predicts better for the leads nobody contacted.",
  ];
}

export interface Term {
  term: string;
  meaning: string;
}

/** The words the CRM uses, in plain words. */
export function glossary(r: StartInfo["rules"]): Term[] {
  return [
    {
      term: "Score",
      meaning: `A lead's chance, from 0 to 100, to buy within ${r.outcome_window_days} days if nobody contacts them.`,
    },
    {
      term: "Best step (next-best-action)",
      meaning: "The step that helps a lead most: an email, a coupon, a call, a WhatsApp message, or nothing.",
    },
    {
      term: "Comes in anyway",
      meaning: "Expected sales from all open leads if the team does nothing more: an estimate, not money earned.",
    },
    {
      term: "The team can add",
      meaning:
        "The extra sales the best steps are expected to bring across all open leads, after discounts: an estimate for the owner, never shown per lead.",
    },
    { term: "No discount needed", meaning: "A lead likely to buy anyway: a coupon would hardly change that." },
    {
      term: "Control group",
      meaning: `${pct(r.control_share)} of learners the CRM never contacts. Comparing with them shows what the team's work really adds.`,
    },
    {
      term: "Hold-out group",
      meaning: "The people in a campaign or an A/B test who get nothing, for the same reason.",
    },
    {
      term: "Learning steps",
      meaning: `${pct(r.learning_steps)} of the CRM's own decisions are picked at random, so it keeps checking fairly which step works.`,
    },
    {
      term: "Price of a call slot",
      meaning: `The team can make ${r.daily_calls} calls a day. A call is booked only when it adds more than this price, so the slots go to the calls that add the most.`,
    },
    {
      term: "Discount budget",
      meaning:
        "An optional monthly limit on discounts, set in the planner. The CRM then gives coupons where they add the most for each rupee.",
    },
    {
      term: "Simulated learner",
      meaning:
        "A practice learner, always marked as simulated, that keeps the CRM busy. Everyone who signs up on the website is real.",
    },
  ];
}

const SEEN_KEY = "xe.crm.start-seen";

/** Whether this browser has opened Start here (a per-viewer convenience: storage may be blocked). */
export function startSeen(): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

export function markStartSeen(): void {
  try {
    window.localStorage.setItem(SEEN_KEY, "1");
  } catch {
    // storage blocked: the welcome bar simply shows again next time
  }
}
