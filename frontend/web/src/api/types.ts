/** Shapes of the learner API's responses (see backend/app/api/learner and docs/api.md). */

export interface Course {
  slug: string;
  title: string;
  abbr: string;
  domain: string;
  tagline: string;
  level: string;
  duration: string;
  price: number;
  emi: number | null;
  outcomes: string[];
  instructor: { name: string; role: string; exp: string };
  curriculum: { module: string; title: string }[];
}

export interface User {
  id: number;
  name: string;
  email: string;
  is_verified?: number;
  created_at?: string;
}

export interface Profile {
  user_id: number;
  current_occupation: string | null;
  specialization: string | null;
  age_bracket: string | null;
  city: string | null;
  country: string | null;
  phone: string | null;
  whatsapp_opt_in: number | null;
  do_not_email: "Yes" | "No" | null;
  do_not_call: "Yes" | "No" | null;
  how_did_you_hear: string | null;
  profile_complete: number | null;
}

export interface SignInResponse {
  token: string;
  session_id: number;
  user: User;
  profile_complete: boolean;
  message?: string;
}

export interface CartItem {
  id: number;
  course_slug: string;
  course_title: string;
  price: number;
  added_at: string;
}

export interface WishlistItem {
  id: number;
  course_slug: string;
  course_title: string;
  added_at: string;
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
  coupon_code: string;
  discount_pct: number;
  used: number;
  used_at: string | null;
  expires_at: string | null;
  created_at: string;
}

export interface NextStep {
  label: string;
  to: string;
  why: string;
}

export interface Dashboard {
  user: User;
  profile: Profile | null;
  cart: CartItem[];
  wishlist: WishlistItem[];
  purchases: Purchase[];
  coupons: Coupon[];
  lead_score: number | null;
  persona: string | null;
  next_steps: NextStep[];
}

export interface Recommendation {
  title: string;
  slug: string | null;
  reason: string;
}

export interface Review {
  id: number;
  rating: number;
  review_text: string | null;
  created_at: string;
  name: string;
}

export interface Question {
  id: number;
  question: string;
  answer: string | null;
  answered_by: string | null;
  answered_at: string | null;
  created_at: string;
  user_name: string;
}

export interface ChatReply {
  conversation_id: string;
  reply: string;
  intent: string;
  course_slug: string | null;
  suggestions: string[];
  links: { label: string; to: string }[];
  action: { type: "callback_form" } | null;
}

export interface CouponCheck {
  code: string;
  discount_pct: number;
  expires_at: string | null;
  subtotal: number;
  discount: number;
  total: number;
}

export interface CheckoutResult {
  message: string;
  courses_purchased: string[];
  discount_applied: string;
  attributed_to: string;
  updated_lead_score: number;
  /** The payment is simulated: nothing is charged. */
  demo_payment?: boolean;
  /** A confirmation email goes out (only when email is set up). */
  confirmation_emailed?: boolean;
}
