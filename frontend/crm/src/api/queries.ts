/** Queries used on more than one page (each page keeps its own queries next to it). */
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api, publicApi } from "./client";
import type { Capacity, SimulationStatus, Stats } from "./types";

export function useStats(refetchInterval = 30_000, enabled = true) {
  return useQuery({ queryKey: ["stats"], queryFn: () => api.get<Stats>("/stats"), refetchInterval, enabled });
}

export function useCapacity(refetchInterval = 30_000) {
  return useQuery({ queryKey: ["capacity"], queryFn: () => api.get<Capacity>("/capacity"), refetchInterval });
}

export function useSimulation(refetchInterval = 20_000, enabled = true) {
  return useQuery({
    queryKey: ["simulation"],
    queryFn: () => api.get<SimulationStatus>("/simulation"),
    refetchInterval,
    enabled,
  });
}

export interface CourseSummary {
  slug: string;
  title: string;
  domain: string;
  price: number;
}

/** The course catalogue (titles by slug); it changes only when the backend's catalogue file changes. */
export function useCourses() {
  const q = useQuery({
    queryKey: ["courses"],
    queryFn: () => publicApi.get<{ courses: CourseSummary[] }>("/courses"),
    staleTime: Infinity,
  });
  return useMemo(() => {
    const bySlug = new Map((q.data?.courses ?? []).map((c) => [c.slug, c]));
    return {
      list: q.data?.courses ?? [],
      title: (slug: string | null | undefined) => (slug ? (bySlug.get(slug)?.title ?? slug.replace(/-/g, " ")) : ""),
    };
  }, [q.data]);
}
