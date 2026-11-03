import { useEffect, useRef, type RefObject } from "react";
import { useSession } from "../app/session";
import { ensureVisit, track } from "./tracker";

/**
 * Records a page view when the learner leaves the page (or hides the tab), with the time spent on it. Only for
 * signed-in learners.
 */
export function usePageView(courseSlug?: string | null, enabled = true): void {
  const { me } = useSession();
  const userId = me?.user.id;
  useEffect(() => {
    if (!userId || !enabled) return;
    let start = Date.now();
    let sent = false;
    void ensureVisit();
    const send = (keepalive: boolean) => {
      if (sent) return;
      sent = true;
      void track("page_view", courseSlug, Math.max(1, (Date.now() - start) / 1000), keepalive);
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") send(true);
      else {
        start = Date.now();
        sent = false;
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    const mounted = Date.now();
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      // React mounts twice while it checks the code in development: a page "seen" for no time at all is not a view
      if (Date.now() - mounted >= 250) send(false);
    };
  }, [userId, courseSlug, enabled]);
}

/** Records an event once when an element has been at least half visible for a second (fees, reviews). */
export function useSeen(ref: RefObject<HTMLElement | null>, eventType: string, courseSlug?: string | null): void {
  const { me } = useSession();
  const userId = me?.user.id;
  const done = useRef(false);
  useEffect(() => {
    done.current = false;
  }, [courseSlug]);
  useEffect(() => {
    const el = ref.current;
    if (!el || !userId || typeof IntersectionObserver === "undefined") return;
    let timer: number | undefined;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !done.current) {
          timer = window.setTimeout(() => {
            done.current = true;
            void track(eventType, courseSlug, 1);
          }, 1000);
        } else if (timer) {
          window.clearTimeout(timer);
        }
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      if (timer) window.clearTimeout(timer);
    };
  }, [ref, eventType, courseSlug, userId]);
}
