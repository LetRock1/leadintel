import { cn, initials, plural } from "@xedu/shared/lib";
import { buttonClass, IconButton, Menu, ThemeToggle } from "@xedu/shared/ui";
import { Heart, Menu as MenuIcon, ShoppingBag, X } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router";
import { useCart, useWishlist } from "../api/queries";
import { useSession, useSignOutHome } from "../app/session";
import { openAssistant } from "../lib/assistant-bus";

export function Brand({ className }: { className?: string }) {
  return (
    <Link to="/" className={cn("flex items-center gap-2.5", className)} aria-label="X Education, home">
      <svg aria-hidden viewBox="0 0 32 32" className="size-8">
        <rect width="32" height="32" rx="7" fill="var(--xe-brand)" />
        <path d="M9 9l14 14M23 9L9 23" stroke="#fff" strokeWidth="3.2" strokeLinecap="round" />
      </svg>
      <span className="font-display text-[18px] font-semibold tracking-[-0.01em] text-ink">X Education</span>
    </Link>
  );
}

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "rounded-sm px-3 py-2 text-[14.5px] transition-colors",
    isActive ? "font-medium text-ink" : "text-ink-2 hover:text-ink",
  );

function CountBadge({ n }: { n: number }) {
  if (!n) return null;
  return (
    <span className="num absolute -right-0.5 -top-0.5 flex min-w-4 items-center justify-center rounded-full bg-brand px-1 text-[10.5px] font-semibold leading-4 text-on-brand">
      {n}
    </span>
  );
}

export function SiteHeader() {
  const { me } = useSession();
  const navigate = useNavigate();
  const cart = useCart();
  const wishlist = useWishlist();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const signOutHome = useSignOutHome();

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-canvas/95 backdrop-blur print:hidden">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center gap-2 px-5 sm:px-8">
        <Brand className="mr-4" />
        <nav aria-label="Main" className="hidden items-center md:flex">
          <NavLink to="/courses" className={linkClass}>
            Courses
          </NavLink>
          <a href="/#live-session" className="rounded-sm px-3 py-2 text-[14.5px] text-ink-2 hover:text-ink">
            Free live session
          </a>
          <button
            type="button"
            onClick={() => openAssistant()}
            className="rounded-sm px-3 py-2 text-[14.5px] text-ink-2 hover:text-ink"
          >
            Ask a question
          </button>
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          {me ? (
            <>
              <Link
                to="/wishlist"
                aria-label={`Wishlist, ${plural(wishlist.data?.length ?? 0, "course")}`}
                className="relative inline-flex size-9 items-center justify-center rounded-sm text-ink-2 hover:bg-sunken hover:text-ink"
              >
                <Heart aria-hidden className="size-[18px]" />
                <CountBadge n={wishlist.data?.length ?? 0} />
              </Link>
              <Link
                to="/cart"
                aria-label={`Cart, ${plural(cart.data?.length ?? 0, "course")}`}
                className="relative inline-flex size-9 items-center justify-center rounded-sm text-ink-2 hover:bg-sunken hover:text-ink"
              >
                <ShoppingBag aria-hidden className="size-[18px]" />
                <CountBadge n={cart.data?.length ?? 0} />
              </Link>
              <Menu
                label="Your account"
                items={[
                  { label: "My learning", onSelect: () => navigate("/my-learning") },
                  { label: "Settings", onSelect: () => navigate("/settings") },
                  { label: "Sign out", onSelect: () => signOutHome() },
                ]}
                trigger={(p) => (
                  <button
                    type="button"
                    {...p}
                    aria-label="Your account"
                    className="ml-1 flex size-9 items-center justify-center rounded-full bg-brand-soft text-[13px] font-semibold text-brand-ink hover:ring-2 hover:ring-brand/30"
                  >
                    {initials(me.user.name)}
                  </button>
                )}
              />
            </>
          ) : (
            <div className="hidden items-center gap-1 sm:flex">
              <Link to="/login" className={buttonClass("ghost")}>
                Sign in
              </Link>
              <Link to="/signup" className={buttonClass("primary")}>
                Create a free account
              </Link>
            </div>
          )}
          <IconButton label="Open the menu" className="md:hidden" onClick={() => setOpen(true)}>
            <MenuIcon aria-hidden className="size-5" />
          </IconButton>
        </div>
      </div>
      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            aria-label="Close the menu"
            className="absolute inset-0 bg-[var(--xe-overlay)]"
            onClick={close}
          />
          <nav
            aria-label="Main"
            className="absolute inset-x-0 top-0 border-b border-line bg-surface px-5 pb-6 pt-3 shadow-overlay"
          >
            <div className="flex items-center justify-between">
              <Brand />
              <IconButton label="Close the menu" onClick={close}>
                <X aria-hidden className="size-5" />
              </IconButton>
            </div>
            <ul className="mt-4 flex flex-col gap-1 text-[16px]">
              <li>
                <Link to="/courses" onClick={close} className="block rounded-sm px-2 py-2.5 text-ink hover:bg-sunken">
                  Courses
                </Link>
              </li>
              <li>
                <a
                  href="/#live-session"
                  onClick={close}
                  className="block rounded-sm px-2 py-2.5 text-ink hover:bg-sunken"
                >
                  Free live session
                </a>
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => {
                    close();
                    openAssistant();
                  }}
                  className="block w-full rounded-sm px-2 py-2.5 text-left text-ink hover:bg-sunken"
                >
                  Ask a question
                </button>
              </li>
              {me ? (
                <>
                  <li>
                    <Link
                      to="/my-learning"
                      onClick={close}
                      className="block rounded-sm px-2 py-2.5 text-ink hover:bg-sunken"
                    >
                      My learning
                    </Link>
                  </li>
                  <li>
                    <Link
                      to="/settings"
                      onClick={close}
                      className="block rounded-sm px-2 py-2.5 text-ink hover:bg-sunken"
                    >
                      Settings
                    </Link>
                  </li>
                </>
              ) : (
                <li className="mt-3 flex gap-2">
                  <Link to="/login" onClick={close} className={buttonClass("secondary", "lg", "flex-1")}>
                    Sign in
                  </Link>
                  <Link to="/signup" onClick={close} className={buttonClass("primary", "lg", "flex-1")}>
                    Create an account
                  </Link>
                </li>
              )}
            </ul>
          </nav>
        </div>
      )}
    </header>
  );
}
