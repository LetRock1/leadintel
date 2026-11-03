/** Words the CRM shows for the backend's keys. The backend sends most labels itself; these cover keys sent alone. */
import type { ActionKey, Policy } from "../api/types";

export const ACTION_LABEL: Record<ActionKey, string> = {
  none: "Do nothing for now",
  email_info: "Send an information email",
  email_coupon_10: "Send email with 10% coupon",
  email_coupon_20: "Send email with 20% coupon",
  call: "Counsellor phone call",
  whatsapp: "WhatsApp message",
};

/** Short names for table columns and chart axes. */
export const ACTION_SHORT: Record<ActionKey, string> = {
  none: "No step",
  email_info: "Information email",
  email_coupon_10: "10% coupon email",
  email_coupon_20: "20% coupon email",
  call: "Phone call",
  whatsapp: "WhatsApp",
};

export const ACTION_ORDER: ActionKey[] = [
  "none",
  "email_info",
  "email_coupon_10",
  "email_coupon_20",
  "call",
  "whatsapp",
];

export function actionLabel(key: string | null | undefined, short = false): string {
  if (!key) return "No step";
  const k = key as ActionKey;
  return (short ? ACTION_SHORT[k] : ACTION_LABEL[k]) ?? key;
}

/** Lead tiers, hottest first (crm_settings.json). */
export const TIERS = [
  "Target Immediately",
  "Nurture via Email/WhatsApp",
  "Marketing Campaign",
  "Low Priority",
] as const;

/** 4 for the hottest tier, 1 for the coolest; 0 when unknown. */
export function tierLevel(tier: string | null | undefined): number {
  const i = TIERS.indexOf((tier ?? "") as (typeof TIERS)[number]);
  return i < 0 ? 0 : TIERS.length - i;
}

export const POLICY_LABEL: Record<Policy, string> = {
  model: "The model's pick",
  explore: "Random step for learning",
  holdout: "Control group, left alone",
  manual: "Taken by hand",
};

export const POLICY_HELP: Record<Policy, string> = {
  model: "The step expected to help most, after its cost and any discount.",
  explore: "A small share of decisions take a random allowed step, so the model keeps learning what each step does.",
  holdout: "People in the control group are never contacted, so their outcome shows what happens without the CRM.",
  manual: "Someone on the team chose this step on the lead page.",
};

export const STAGE_LABEL: Record<string, string> = {
  Lead: "New lead",
  Engaged: "Engaged",
  MQL: "Interested (MQL)",
  SQL: "Ready to buy (SQL)",
  Customer: "Customer",
  Lost: "Lost",
};

export const TRIGGER_LABEL: Record<string, string> = {
  signup: "Signed up",
  session_end: "Visit ended",
  enquiry: "Sent an enquiry",
  wishlist: "Wishlist reminder",
  cart_abandon: "Left items in the cart",
  checkout_abandon: "Left the checkout",
  manual: "Step taken by hand",
  campaign: "Campaign",
  ab_test: "A/B test",
};

export function triggerLabel(key: string | null | undefined): string {
  if (!key) return "";
  return TRIGGER_LABEL[key] ?? key.replace(/_/g, " ");
}

export const EVENT_LABEL: Record<string, string> = {
  page_view: "Viewed a page",
  video_play: "Watched a course video",
  brochure_dl: "Downloaded the brochure",
  chat: "Asked the help assistant",
  pricing_view: "Looked at the fees",
  testimonial_view: "Read learner reviews",
  webinar_view: "Watched a webinar",
  webinar_register: "Registered for a live session",
  cart_add: "Added a course to the cart",
  wishlist_add: "Saved a course to the wishlist",
  checkout_start: "Started the checkout",
  enquiry_submit: "Sent an enquiry",
  purchase: "Bought a course",
};

export function eventLabel(key: string): string {
  return EVENT_LABEL[key] ?? key.replace(/_/g, " ");
}

export const SCORE_REASON_LABEL: Record<string, string> = {
  activity: "Website activity",
  manual_rescore: "Scored again by hand",
  purchase_conversion: "Bought a course",
  consent_changed: "Contact preferences changed",
  score_refresh: "Scheduled refresh",
  model_update: "New model",
};

export const OUTCOME_LABEL: Record<string, string> = {
  reached: "Spoke to them",
  no_answer: "No answer",
  not_interested: "Not interested",
  sent: "WhatsApp sent",
  skipped: "Skipped",
  expired: "Expired",
  "bought before the task was done": "Bought before the task was done",
};

export function outcomeLabel(key: string | null | undefined): string {
  if (!key) return "";
  return OUTCOME_LABEL[key] ?? key;
}

export const AUDIT_LABEL: Record<string, string> = {
  login: "Signed in",
  login_failed: "Failed sign-in",
  password_changed: "Changed their password",
  password_reset: "Set a new password for an account",
  member_created: "Added an account",
  member_updated: "Changed an account",
  member_deleted: "Deleted an account",
  team_settings: "Changed the team settings",
  lead_assigned: "Gave a lead to someone",
  lead_unassigned: "Made a lead unassigned",
  stage_moved: "Moved a lead on the pipeline",
  stage_auto: "Put a lead back on automatic stage",
  lead_lost: "Closed a lead as lost",
  lead_reopened: "Re-opened a lead",
  consent_recorded: "Recorded a contact preference",
  note_added: "Added a note",
  note_deleted: "Deleted a note",
  task_done: "Recorded a task outcome",
  task_skipped: "Skipped a task",
  callback_done: "Closed a call-back request",
  step_taken: "Took a step by hand",
  email_sent: "Sent an email",
  whatsapp_opened: "Opened WhatsApp",
  coupon_created: "Gave a coupon",
  coupon_deleted: "Withdrew a coupon",
  campaign_scheduled: "Scheduled a campaign",
  campaign_sent: "Sent a campaign",
  campaign_deleted: "Deleted a campaign",
  ab_test_created: "Created an A/B test",
  ab_test_sent: "Sent an A/B test",
  ab_test_deleted: "Deleted an A/B test",
  ab_winner_applied: "Turned an A/B variant into a campaign",
  adoption_reverted: "Switched back to the old standard email",
  question_answered: "Answered a course question",
  leads_exported: "Exported the leads",
  automations_run: "Ran the automatic follow-ups",
  learning_run: "Ran the learning loop",
  simulation_paused: "Paused the simulated learners",
  simulation_resumed: "Resumed the simulated learners",
};

export function auditLabel(key: string): string {
  return AUDIT_LABEL[key] ?? key.replace(/_/g, " ");
}
