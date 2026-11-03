/** Shapes of the CRM API's responses (see backend/app/api/crm and docs/api.md). */

export type Role = "admin" | "marketing" | "counsellor";

export interface TeamRef {
  id: number;
  name: string;
  role: Role;
  active?: boolean;
}

export interface Member {
  id: number;
  name: string;
  email: string;
  role: Role;
  role_label: string;
  is_owner: boolean;
  active: boolean;
  takes_new_leads: boolean;
  must_change_password: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

export interface Me extends Member {
  can: ("team" | "audit" | "marketing" | "leads")[];
  team: TeamRef[];
  env_password: boolean;
}

export type ActionKey = "none" | "email_info" | "email_coupon_10" | "email_coupon_20" | "call" | "whatsapp";

/** One line of a decision receipt: what a step is worth for this person. */
export interface StepOption {
  action: ActionKey;
  label: string;
  blocked: string | null;
  discount: number;
  cost: number;
  p_convert: number;
  uplift: number;
  expected_profit: number;
  incremental_profit: number;
  slot_price?: number;
  net_of_slot?: number;
  /** Expected discount: chance to buy with the step x fee x discount (what a coupon uses of a discount budget). */
  expected_discount?: number;
  /** With a monthly discount budget: the profit a rupee of discount must earn, and the coupon's value net of it. */
  budget_price?: number;
  net_of_budget?: number;
}

export interface Factor {
  factor: string;
  detail: string;
  impact: string;
  points: number;
}

export interface Tip {
  title: string;
  detail: string;
  steps: string[];
  new_score: number;
  effort: number;
}

export interface NowRecommendation {
  user_id: number;
  name: string;
  control_group: boolean;
  customer: boolean;
  away_days: number | null;
  purchases: { course: string; course_slug: string; paid: number; coupon: string | null; at: string }[];
  lead_model: string | null;
  nba_model: string;
  course?: { slug: string | null; title: string | null; price: number };
  score?: number;
  probability?: number;
  tier?: string;
  lead_age_days?: number | null;
  factors?: Factor[];
  tips?: Tip[];
  options?: StepOption[];
  slot_price?: number | null;
  call_value?: number | null;
  calls_today?: number;
  recommendation: { action: ActionKey; label: string; why: string; extra_profit: number; p_buy: number } | null;
  message?: string;
  /** Steps that cannot be taken by hand again yet, and why (the same email just sent, a call still waiting). */
  recent?: Partial<Record<ActionKey, string>>;
}

export type Policy = "model" | "explore" | "holdout" | "manual";

export interface DecisionItem {
  kind: "decision" | "campaign" | "ab";
  id?: number;
  at: string;
  trigger?: string;
  action?: ActionKey;
  label?: string;
  model_best?: ActionKey;
  model_best_label?: string;
  policy?: Policy;
  policy_text?: string;
  propensity?: number;
  base_probability?: number;
  price?: number;
  model_version?: string;
  options?: StepOption[];
  slot_price?: number | null;
  call_value?: number | null;
  task?: {
    type: string;
    status: string;
    outcome: string | null;
    done_at: string | null;
    done_by: string | null;
  } | null;
  adopted_email?: { arm: string; variant: string; test: string } | null;
  name?: string;
  arm?: string;
  sent?: boolean;
  probability?: number;
  email?: { subject: string; sent_at: string; clicked_at: string | null; clicks: number };
  next_visit: string | null;
  outcome: "bought" | "did_not_buy" | "waiting";
  bought?: { course: string; at: string; paid: number };
  days_left?: number;
}

export interface LeadRow {
  id: number;
  user_id: number;
  lead_score: number;
  conversion_probability: number;
  plv: number | null;
  persona: string;
  recommended_action: string;
  trigger_reason: string;
  course_type: string | null;
  course_slug: string | null;
  email_sent: number;
  created_at: string;
  /** The person's own last visit to the website (or their sign-up when they never came back). */
  last_active_at: string | null;
  nba_action: string | null;
  model_version: string | null;
  name: string;
  email: string;
  phone: string | null;
  whatsapp_opt_in: number | null;
  do_not_email: string | null;
  do_not_call: string | null;
  current_occupation: string | null;
  specialization: string | null;
  city: string | null;
  touches: number;
  purchases: number;
  spent: number;
  first_course: string | null;
  first_purchase_at: string | null;
  open_callbacks: number;
  lost: boolean;
  lost_reason: string | null;
  simulated: boolean;
  customer: boolean;
  owner_id: number | null;
  owner: string;
}

export interface LeadsResponse {
  leads: LeadRow[];
  segment: string;
  owner: string;
  counts: { all: number; real: number; simulated: number; mine: number; unassigned: number };
  matching: number;
  offset: number;
}

export interface BehaviourEvent {
  id: number;
  event_type: string;
  course_slug: string | null;
  time_spent_sec: number | null;
  created_at: string;
}

export interface EmailRow {
  id: number;
  subject: string;
  sent_at: string;
  click_count: number;
  first_clicked_at: string | null;
  campaign_name: string | null;
  ab_test_id: number | null;
  variant: string | null;
  /** Why the mail server did not take it (null: sent, or recorded without email set up). */
  error: string | null;
}

export interface TaskRow {
  id: number;
  user_id: number;
  lead_id: number | null;
  decision_id: number | null;
  task_type: "call" | "whatsapp";
  title: string;
  detail: string | null;
  expected_gain: number | null;
  status: "open" | "done" | "skipped";
  outcome: string | null;
  created_at: string;
  done_at: string | null;
  done_by: string | null;
}

export interface Note {
  id: number;
  member_id: number | null;
  author: string | null;
  kind: string;
  text: string;
  created_at: string;
}

export interface Purchase {
  id: number;
  course_slug: string;
  course_title: string;
  price_paid: number;
  coupon_used: string | null;
  discount_amount: number | null;
  purchased_at: string;
}

export interface Coupon {
  id: number;
  user_id: number;
  coupon_code: string;
  discount_pct: number;
  tier: string;
  used: number;
  used_at: string | null;
  expires_at: string | null;
  created_at: string;
  name?: string;
  email?: string;
}

export interface CallbackRow {
  id: number;
  user_id: number;
  phone: string;
  course_slug: string | null;
  preferred_time: string | null;
  note: string | null;
  status: "open" | "done";
  created_at: string;
  closed_at: string | null;
  done_by: string | null;
  name?: string;
  email?: string;
  lead_id?: number | null;
  overdue?: boolean;
  simulated?: boolean;
  owner?: string;
  owner_id?: number | null;
}

export interface LeadPage {
  id: number;
  user_id: number;
  name: string;
  email: string;
  phone: string | null;
  signed_up_at: string;
  /** The person's own last visit to the website. */
  last_active_at: string | null;
  lead_score: number;
  conversion_probability: number;
  plv: number | null;
  persona: string;
  recommended_action: string;
  trigger_reason: string;
  course_type: string | null;
  course_slug: string | null;
  lead_source: string | null;
  device_type: string | null;
  model_version: string | null;
  current_occupation: string | null;
  specialization: string | null;
  city: string | null;
  age_bracket: string | null;
  whatsapp_opt_in: number | null;
  do_not_email: string | null;
  do_not_call: string | null;
  email_subject: string | null;
  email_body: string | null;
  whatsapp_message: string | null;
  call_script: string | null;
  created_at: string;
  opened_record: number;
  latest_lead_id: number;
  behaviour_events: BehaviourEvent[];
  coupons: Coupon[];
  global_control: boolean;
  touches: {
    id: number;
    trigger_reason: string;
    lead_score: number;
    recommended_action: string;
    email_sent: number;
    created_at: string;
  }[];
  score_history: {
    id: number;
    old_score: number;
    new_score: number;
    old_tier: string;
    new_tier: string;
    reason: string;
    created_at: string;
  }[];
  emails: EmailRow[];
  purchases: Purchase[];
  chat: { role: "user" | "assistant"; text: string; intent: string | null; created_at: string }[];
  callbacks: CallbackRow[];
  tasks: TaskRow[];
  nba: (Partial<DecisionItem> & { why?: string; detail?: string }) | null;
  tips: Tip[] | null;
  factors: Factor[];
  simulated: boolean;
  customer: boolean;
  spent: number;
  decisions: DecisionItem[];
  owner: { id: number | null; name: string; assigned_at: string | null; how: string | null };
  notes: Note[];
  status: { lost: boolean; reason: string | null; note: string | null; since: string | null; by: string | null };
  can_change: boolean;
  can_change_why: string | null;
  lost_reasons: string[];
  team: TeamRef[];
}

export interface ActionRow extends TaskRow {
  name: string;
  email: string;
  phone: string | null;
  whatsapp_opt_in: number | null;
  lead_score: number | null;
  recommended_action: string | null;
  course_type: string | null;
  course_slug: string | null;
  policy: Policy | null;
  model_best: ActionKey | null;
  slot_price: number | null;
  call_value: number | null;
  options: StepOption[];
  course_price: number | null;
  tips: Tip[];
  simulated: boolean;
  overdue: boolean;
  owner: string;
  owner_id: number | null;
}

export interface ActionsResponse {
  actions: ActionRow[];
  segment: string;
  owner: string;
  other_segment_count: number;
  sla_hours: number;
  expiry_days: number;
}

export interface Capacity {
  policy: "priced" | "fcfs";
  capacity: number;
  days_seen: number;
  candidates: number;
  per_day: number;
  static_price: number;
  note: string;
  price: number | null;
  calls_today: number;
  slots_left: number;
  full: boolean;
  lookback_days: number;
  history: { computed_at: string; price: number; policy: string; per_day: number | null }[];
}

export interface Stats {
  total_leads: number;
  open_leads: number;
  customers: number;
  real_people: number;
  real_customers: number;
  real_purchases: number;
  real_revenue: number;
  simulated_people: number;
  simulated_customers: number;
  by_tier: Record<string, number>;
  avg_lead_score: number;
  total_users: number;
  total_purchases: number;
  revenue: number;
  active_carts: number;
  emails_sent: number;
  email_clicks: number;
  open_callbacks: number;
  open_tasks: number;
  calls_today: number;
  purchases_today: number;
  revenue_today: number;
  score_distribution: Record<string, number>;
}

export interface DailyPoint {
  date: string;
  signups: number;
  purchases: number;
  revenue: number;
}

export interface Forecast {
  open_leads: number;
  expected_revenue: number;
  range_90: [number, number];
  expected_customers: number;
  customers_range_90: [number, number];
  by_tier: { tier: string; leads: number; expected_customers: number; expected_revenue: number }[];
  window_days?: number;
  note?: string;
}

export interface Impact {
  days: number;
  worked_on: { people: number; bought: number; rate: number | null };
  control: { people: number; bought: number; rate: number | null };
  share: number;
  lift?: number;
  lift_ci?: [number, number];
  p_value?: number;
}

export interface PolicyEstimate {
  ips_profit_per_lead: number | null;
  snips_profit_per_lead: number | null;
  ci95: [number, number] | null;
  matched_decisions: number;
  enough: boolean;
}

export interface NbaPerformance {
  decisions_total: number;
  decisions_with_outcome: number;
  by_action: Record<string, { decisions: number; explore: number; known_outcome: number; converted: number }>;
  randomised_slice: Record<string, { n: number; converted: number; rate: number | null }>;
  verdict: string;
  policy_estimates: Record<string, PolicyEstimate>;
  note: string;
}

export interface ModelHealth {
  model: Record<string, unknown> | null;
  window_days: number;
  snapshots_total: number;
  snapshots_labelled: number;
  by_tier: { tier: string; snapshots: number; predicted_rate: number; actual_rate: number }[];
  calibration: { bin: number; n: number; predicted: number; actual: number }[];
}

export interface SimulationStatus {
  enabled: boolean;
  /** SIMULATION_ENABLED=false in backend/.env: off whatever the dashboard says. */
  switched_off_by_settings?: boolean;
  started_at: string | null;
  last_tick: string | null;
  last_error: string | null;
  learners: { total: number; customers: number; signed_up_live: number; on_site_now: number; still_deciding: number };
  expected_per_day: { visits: number; purchases: number; signups: number };
  last_24h: {
    visits: number;
    email_clicks: number;
    purchases: number;
    signups: number;
    team_tasks: number;
    errors: number;
  };
  tasks_waiting_for_team: number;
  recent: { at: string; user_id: number | null; kind: string; text: string }[];
  recent_errors: { at: string; text: string }[];
  queued_steps: number;
  next_step_at: string | null;
}

export interface PathReaction {
  reaction: "none" | "clicked" | "engaged" | "advanced" | "bought";
  label: string;
  prob: number;
  next: { score: number; tier: string; stage: string; stage_label: string } | null;
  best_next: { action: ActionKey; label: string; p_buy: number; gain: number } | null;
}

export interface PathStep {
  action: ActionKey;
  label: string;
  cost: number;
  discount: number;
  p_buy_step: number;
  uplift: number;
  extra_profit: number;
  reactions: PathReaction[];
  evidence: { decisions: number; basis: string; stage: string; stage_label: string };
}

export interface PathsResponse {
  lead: {
    user_id: number;
    name: string;
    customer: boolean;
    control_group: boolean;
    stage?: string;
    stage_label?: string;
  };
  customer?: boolean;
  steps: PathStep[];
  blocked?: Record<string, string>;
  best: ActionKey | null;
  summary: string;
  note: string;
}

export interface ActResponse {
  ok: boolean;
  message: string;
  action: ActionKey;
  lead_id: number;
  decision_id: number;
  model_pick: ActionKey;
  why: string;
}

export interface ImproveResponse {
  improved_subject: string;
  improved_body: string;
  suggestions: string[];
  engine: "gemini" | "rules";
  note: string;
}

export interface PipelineCard {
  user_id: number;
  lead_id: number;
  name: string;
  email: string;
  course: string | null;
  course_slug: string | null;
  score: number;
  tier: string;
  stage: string;
  auto_stage: string;
  moved_by_hand: boolean;
  override_note: string | null;
  moved_at: string | null;
  moved_by: string | null;
  lost_reason: string | null;
  last_seen: string | null;
  last_action: ActionKey | null;
  last_action_label: string | null;
  control_group: boolean;
  simulated: boolean;
  customer_since: string | null;
  /** The usual weighted value: chance to buy if the team does nothing x course fee (the same as anyway). */
  expected_value: number | null;
  owner_id: number | null;
  owner: string;
  /** The money view: what comes in anyway, what the team can add with the best step now, and a label. */
  segment: MoneySegment;
  anyway: number | null;
  add: number;
  best: ActionKey | null;
  best_label: string | null;
  p_anyway: number | null;
  p_with_step: number | null;
  /** More likely than not to buy anyway, and no coupon would add profit. */
  no_discount: boolean;
}

export type MoneySegment = "work" | "anyway" | "wait" | "control" | "unreachable" | "lost" | "customer";

export interface PipelineColumn {
  stage: string;
  about: string | null;
  count: number;
  expected_value: number;
  anyway: number;
  add: number;
  work: number;
  moved_by_hand: number;
  cards: PipelineCard[];
}

export interface MoneyTotals {
  window_days: number;
  open_leads: number;
  anyway: number;
  add: number;
  work: number;
  buys_anyway: number;
  no_discount: number;
}

export interface PipelineBoard {
  columns: PipelineColumn[];
  stages: string[];
  sort: "money" | "score";
  totals: MoneyTotals;
  generated_at: string;
  owner: string;
  lost_reasons: string[];
}

export interface Campaign {
  id: number;
  name: string;
  tier: string;
  subject: string;
  body: string;
  scheduled_at: string | null;
  status: "draft" | "scheduled" | "sending" | "sent" | "failed" | string;
  holdout_share: number | null;
  sent: number;
  sent_at: string | null;
  recipients: number | null;
  held_out: number | null;
  error: string | null;
  simulated: boolean;
  created_at: string;
  delivered: number;
  /** Emails the mail server did not take (they can be sent again). */
  failed: number;
  failed_reason: string | null;
  clicks: number;
  conversions: number;
  audience_now: number | null;
  holdout?: { people: number; conversions: number };
  incremental?: { lift: number; ci: [number, number]; final: boolean };
}

export interface CampaignsResponse {
  campaigns: Campaign[];
  audiences: string[];
  default_holdout_share: number;
  window_days: number;
}

export interface AbVariant {
  key: string;
  label: string;
  offer_pct: number;
  subject: string;
  body: string;
}

export interface AbVerdict {
  status: "broken" | "waiting" | "running" | "winner" | "loser" | "no_difference" | string;
  headline: string;
  detail?: string;
  winner?: string;
}

export interface AbTest {
  id: number;
  name: string;
  tier: string;
  hypothesis: string | null;
  metric: "purchase" | "click";
  control_share: number | null;
  mde: number | null;
  planned_per_arm: number | null;
  status: string;
  sent_at: string | null;
  started_at: string | null;
  applied_campaign_id: number | null;
  simulated: boolean;
  created_at: string;
  variants: AbVariant[];
  state: "draft" | "running" | "completed" | string;
  adoption: { id: number; status: string; variant_key: string; variant_label: string } | null;
  verdict: AbVerdict | null;
  people: number;
}

export interface AbPlan {
  audience: number;
  baseline_rate: number;
  planned_per_arm: number;
  per_arm_available: number;
  detectable_lift: number | null;
  enough: boolean;
  mde: number;
  metric: string;
}

export interface AbArm {
  arm: string;
  label: string;
  n: number;
  purchases: number;
  clicks: number;
  conversion_rate: number | null;
  click_rate: number | null;
  rate: number | null;
  rate_ci: [number | null, number | null];
  revenue: number;
  revenue_per_person: number | null;
  coupon_cost: number;
  send_cost: number;
  profit_per_person: number | null;
}

export interface AbComparison {
  variant: string;
  vs: string;
  lift: number;
  lift_ci: [number, number];
  relative_lift: number | null;
  p_value: number | null;
  p_adjusted: number | null;
  significant: boolean;
  revenue_lift_per_person: number;
  revenue_lift_ci: [number, number];
  profit_lift_per_person: number;
}

export interface AbSegmentRow {
  value: string;
  arms: Record<string, { n: number; rate: number | null; lift?: number; lift_ci?: [number, number] }>;
  best: string | null;
  enough: boolean;
}

export interface AbResults {
  metric: "bought" | "clicked";
  arms: AbArm[];
  comparisons: AbComparison[];
  reference: string | null;
  srm_p: number | null;
  srm_problem: boolean;
  final: boolean;
  days_since_start: number;
  window_days: number;
  planned_per_arm: number;
  smallest_arm: number;
  detectable_lift: number | null;
  curve: Record<string, number>[];
  segments: Record<string, AbSegmentRow[]>;
  verdict: AbVerdict;
  alpha: number;
  bonferroni_comparisons: number;
}

export interface AbTestsResponse {
  ab_tests: AbTest[];
  settings: {
    control_share: number;
    alpha: number;
    power: number;
    min_detectable_effect: number;
    max_variants: number;
  };
  window_days: number;
}

export interface Adoption {
  id: number;
  ab_test_id: number | null;
  test_name: string;
  audience: string;
  metric: string;
  variant_key: string;
  variant_label: string;
  subject: string;
  test_lift: number | null;
  test_lift_lo: number | null;
  test_lift_hi: number | null;
  check_share: number;
  status: "active" | "confirmed" | "reverted" | string;
  adopted_at: string;
  decided_at: string | null;
  reason: string | null;
  check: {
    adopted?: { n: number; rate: number | null };
    check?: { n: number; rate: number | null };
    lift?: number;
    ci?: [number, number];
    note?: string;
  } | null;
  simulated: boolean;
}
