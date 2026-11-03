import { useIsFetching, useQuery } from "@tanstack/react-query";
import { cn, initials, int } from "@xedu/shared/lib";
import { buttonClass, IconButton, Menu, ThemeToggle } from "@xedu/shared/ui";
import {
  ChevronDown,
  Columns3,
  Compass,
  FlaskConical,
  Gauge,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu as MenuIcon,
  MessageCircleQuestion,
  MessagesSquare,
  PhoneIncoming,
  Repeat,
  Scale,
  ScrollText,
  Search,
  Send,
  TicketPercent,
  type LucideIcon,
  Users,
  UsersRound,
  Wallet,
  Waypoints,
  X,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from "react-router";
import { api } from "../api/client";
import { useSimulation, useStats } from "../api/queries";
import { useMe, useSession } from "../app/session";
import { markStartSeen, startSeen } from "../lib/start";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  count?: number;
}

/** The counts beside the menu. Not asked for while the person still has to choose a password (the API refuses). */
function useNavCounts(enabled: boolean) {
  const stats = useStats(30_000, enabled);
  const qna = useQuery({
    queryKey: ["qna"],
    queryFn: () => api.get<{ questions: unknown[] }>("/qna"),
    refetchInterval: 60_000,
    enabled,
  });
  return {
    tasks: stats.data?.open_tasks,
    callbacks: stats.data?.open_callbacks,
    questions: qna.data?.questions.length,
  };
}

function Wordmark() {
  return (
    <div className="flex items-center gap-2.5 px-4">
      <svg aria-hidden viewBox="0 0 32 32" className="size-7 shrink-0">
        <rect width="32" height="32" rx="7" fill="var(--xe-brand)" />
        <path d="M9 9l14 14M23 9L9 23" stroke="#fff" strokeWidth="3.2" strokeLinecap="round" />
      </svg>
      <div className="leading-tight">
        <p className="text-[14px] font-semibold text-ink">X Education</p>
        <p className="text-[12px] text-muted">Admissions CRM</p>
      </div>
    </div>
  );
}

function NavGroup({ title, items, onNavigate }: { title?: string; items: NavItem[]; onNavigate?: () => void }) {
  return (
    <div className={cn("px-2.5", !title && "pt-3")}>
      {title && <p className="px-2 pb-1 pt-4 text-[12px] font-medium text-muted">{title}</p>}
      <ul className="flex flex-col gap-px">
        {items.map(({ to, label, icon: Icon, count }) => (
          <li key={to}>
            <NavLink
              to={to}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "flex h-[34px] items-center gap-2.5 rounded-sm px-2 text-[13.5px] transition-colors",
                  isActive ? "bg-brand-soft font-medium text-brand-ink" : "text-ink-2 hover:bg-sunken hover:text-ink",
                )
              }
            >
              <Icon aria-hidden className="size-4 shrink-0" />
              <span className="flex-1 truncate">{label}</span>
              {count ? <span className="num text-[12px] text-muted">{int(count)}</span> : null}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SimulationLine() {
  const me = useMe();
  const sim = useSimulation(20_000, !me.must_change_password);
  const on = sim.data?.enabled;
  return (
    <NavLink
      to="/simulation"
      className="mx-2.5 flex items-center gap-2 rounded-sm px-2 py-1.5 text-[12.5px] text-muted hover:bg-sunken hover:text-ink"
    >
      <span className={cn("size-2 rounded-full", on ? "bg-good" : "bg-line-strong")} aria-hidden />
      {sim.isPending
        ? "Simulated learners"
        : on
          ? "Simulated learners active"
          : sim.data?.switched_off_by_settings
            ? "Simulated learners off"
            : "Simulated learners paused"}
    </NavLink>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const me = useMe();
  const { signOut, can } = useSession();
  const navigate = useNavigate();
  const counts = useNavCounts(!me.must_change_password);
  const start: NavItem[] = [{ to: "/start", label: "Start here", icon: Compass }];
  const work: NavItem[] = [
    { to: "/actions", label: "Today's actions", icon: ListChecks, count: counts.tasks },
    { to: "/leads", label: "Leads", icon: Users },
    { to: "/pipeline", label: "Pipeline", icon: Columns3 },
    { to: "/callbacks", label: "Call-backs", icon: PhoneIncoming, count: counts.callbacks },
    { to: "/questions", label: "Course questions", icon: MessageCircleQuestion, count: counts.questions },
  ];
  const marketing: NavItem[] = [
    { to: "/campaigns", label: "Campaigns", icon: Send },
    { to: "/ab-tests", label: "A/B tests", icon: FlaskConical },
    { to: "/coupons", label: "Coupons", icon: TicketPercent },
  ];
  const insight: NavItem[] = [
    { to: "/overview", label: "Overview", icon: LayoutDashboard },
    { to: "/planner", label: "Planner", icon: Wallet },
    { to: "/decisions", label: "Next-best-action", icon: Scale },
    { to: "/learning", label: "Learning loop", icon: Repeat },
    { to: "/model", label: "Model health", icon: Gauge },
    { to: "/journeys", label: "Journeys", icon: Waypoints },
    { to: "/ask", label: "Ask the CRM", icon: MessagesSquare },
  ];
  const admin: NavItem[] = [
    ...(can("team") ? [{ to: "/team", label: "Team", icon: UsersRound }] : []),
    ...(can("audit") ? [{ to: "/audit", label: "Audit log", icon: ScrollText }] : []),
  ];
  return (
    <div className="flex h-full flex-col">
      <div className="pb-1 pt-4">
        <Wordmark />
      </div>
      <nav aria-label="Main" className="flex-1 overflow-y-auto pb-4">
        <NavGroup items={start} onNavigate={onNavigate} />
        <NavGroup title="Work" items={work} onNavigate={onNavigate} />
        {can("marketing") && <NavGroup title="Marketing" items={marketing} onNavigate={onNavigate} />}
        <NavGroup title="Insight" items={insight} onNavigate={onNavigate} />
        {admin.length > 0 && <NavGroup title="Admin" items={admin} onNavigate={onNavigate} />}
      </nav>
      <div className="border-t border-line pb-3 pt-2">
        <SimulationLine />
        <div className="mt-1 px-2.5">
          <Menu
            align="start"
            label="Account"
            items={[
              {
                label: "Account and password",
                onSelect: () => {
                  onNavigate?.();
                  navigate("/account");
                },
              },
              { label: "Sign out", onSelect: signOut },
            ]}
            trigger={(p) => (
              <button
                type="button"
                {...p}
                className="flex w-full items-center gap-2.5 rounded-sm px-2 py-1.5 text-left hover:bg-sunken"
              >
                <span className="flex size-7 items-center justify-center rounded-full bg-brand-soft text-[12px] font-semibold text-brand-ink">
                  {initials(me.name)}
                </span>
                <span className="min-w-0 flex-1 leading-tight">
                  <span className="block truncate text-[13px] font-medium text-ink">{me.name}</span>
                  <span className="block text-[12px] text-muted">{me.role_label}</span>
                </span>
                <ChevronDown aria-hidden className="size-4 text-muted" />
              </button>
            )}
          />
        </div>
      </div>
    </div>
  );
}

function GlobalSearch() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  // on the Leads page the box shows the search in use (and is cleared with it)
  const current = location.pathname === "/leads" ? (params.get("search") ?? "") : "";
  const [q, setQ] = useState(current);
  const [shown, setShown] = useState(current);
  if (current !== shown) {
    setShown(current);
    setQ(current);
  }
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const s = q.trim();
    navigate(s ? `/leads?search=${encodeURIComponent(s)}` : "/leads");
  };
  return (
    <form role="search" onSubmit={submit} className="relative w-full max-w-md">
      <Search
        aria-hidden
        className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted"
      />
      <input
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Find a lead by name, email or course"
        aria-label="Find a lead"
        className="h-9 w-full rounded-sm border border-line bg-sunken pl-8 pr-3 text-[13.5px] text-ink placeholder:text-muted focus:border-brand focus:bg-surface focus:outline-none"
      />
    </form>
  );
}

function LiveDot() {
  const fetching = useIsFetching() > 0;
  return (
    <span
      className="hidden items-center gap-1.5 text-[12.5px] text-muted sm:flex"
      title="Every page refreshes by itself"
    >
      <span aria-hidden className={cn("size-1.5 rounded-full transition-colors", fetching ? "bg-brand" : "bg-good")} />
      {fetching ? "Updating" : "Live"}
    </span>
  );
}

/** Until someone has opened Start here once (in this browser), a slim bar points new people to it. */
function WelcomeBar() {
  const location = useLocation();
  const [hidden, setHidden] = useState(startSeen);
  if (hidden || location.pathname === "/start" || location.pathname === "/account") return null;
  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md border border-line bg-brand-soft px-4 py-2.5 text-[13.5px] text-ink">
      <Compass aria-hidden className="size-4 shrink-0 text-brand-ink" />
      <span className="min-w-0 flex-1 basis-60">
        New to this CRM? <strong className="font-medium">Start here</strong> explains what it does and where to begin,
        in five minutes.
      </span>
      <Link to="/start" className={buttonClass("primary", "sm")}>
        Open the guide
      </Link>
      <button
        type="button"
        className={buttonClass("ghost", "sm")}
        onClick={() => {
          markStartSeen();
          setHidden(true);
        }}
      >
        Hide
      </button>
    </div>
  );
}

export function Shell() {
  const [open, setOpen] = useState(false);
  const { signOut } = useSession();
  return (
    <div className="min-h-screen lg:pl-[232px]">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[232px] border-r border-line bg-surface lg:block">
        <Sidebar />
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 bg-[var(--xe-overlay)]"
            onClick={() => setOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-[260px] border-r border-line bg-surface shadow-overlay">
            <IconButton label="Close menu" className="absolute right-2 top-3" onClick={() => setOpen(false)}>
              <X aria-hidden className="size-4" />
            </IconButton>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
      <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-canvas/90 px-4 backdrop-blur sm:px-6">
        <IconButton label="Open menu" className="lg:hidden" onClick={() => setOpen(true)}>
          <MenuIcon aria-hidden className="size-5" />
        </IconButton>
        <GlobalSearch />
        <div className="ml-auto flex items-center gap-1.5">
          <LiveDot />
          <ThemeToggle />
          <div className="mx-1 hidden h-4 w-px bg-line/80 sm:block" />
          <IconButton label="Sign out" onClick={signOut} title="Sign out of CRM" className="text-muted hover:text-ink">
            <LogOut aria-hidden className="size-4" />
          </IconButton>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1360px] px-4 pb-16 pt-6 sm:px-6">
        <WelcomeBar />
        <Outlet />
      </main>
    </div>
  );
}
