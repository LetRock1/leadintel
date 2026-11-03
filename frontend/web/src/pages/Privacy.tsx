import { Link } from "react-router";

const SECTIONS: { title: string; body: string[] }[] = [
  {
    title: "What we record",
    body: [
      "Your name, email address and password (stored only as a salted hash). If you give them: your occupation, field, age range, city and phone number.",
      "While you are signed in: the pages you open and for how long, course overviews you watch, brochures you open, what you add to your cart or wishlist, questions you ask, and the clicks on our emails.",
      "Nothing is recorded for visitors who are not signed in, apart from the clicks on links in our emails.",
    ],
  },
  {
    title: "What it is used for",
    body: [
      "To suggest courses that fit you, and to decide which follow-up is worth sending: an email with course details, a coupon, a WhatsApp message, or a call from a counsellor.",
      "A small random group of learners gets no follow-ups at all. Comparing them with everyone else shows whether the follow-ups help, so the team does not send messages that only annoy people.",
      "Your data is not sold or shared with advertisers.",
    ],
  },
  {
    title: "Your choices",
    body: [
      "Switch off course emails, calls or WhatsApp at any time in Settings; every marketing email also has a one-click unsubscribe link. The CRM's automatic follow-ups respect your choice straight away.",
      "Settings also shows what the model currently sees about you.",
      "Delete your account in Settings: everything linked to you is removed. The team's audit log keeps only numbers, not your details.",
    ],
  },
  {
    title: "About this site",
    body: [
      "X Education is a demonstration built for a research project on CRM decision-making. Payments are simulated and nothing is charged. Many of the learners you may see mentioned are simulated; their accounts end in demo.xeducation.test.",
    ],
  },
];

export default function Privacy() {
  return (
    <div className="mx-auto max-w-[760px] px-5 pb-10 pt-12 sm:px-8">
      <h1 className="text-[34px] font-semibold leading-tight text-ink">Privacy and your data</h1>
      <p className="mt-3 text-[16px] text-ink-2">What X Education records about you, why, and how to change it.</p>
      {SECTIONS.map((s) => (
        <section key={s.title} className="mt-10">
          <h2 className="text-[22px] font-semibold text-ink">{s.title}</h2>
          {s.body.map((p) => (
            <p key={p} className="mt-3 text-[15.5px] text-ink-2">
              {p}
            </p>
          ))}
        </section>
      ))}
      <p className="mt-10 text-[15px] text-ink-2">
        Change your choices in{" "}
        <Link to="/settings" className="font-medium text-brand-ink hover:underline">
          Settings
        </Link>
        .
      </p>
    </div>
  );
}
