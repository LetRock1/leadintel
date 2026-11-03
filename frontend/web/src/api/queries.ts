/** Queries used on more than one page. */
import { useQuery } from "@tanstack/react-query";
import { useSession } from "../app/session";
import { api } from "./client";
import type { CartItem, Course, WishlistItem } from "./types";

export function useCourses() {
  return useQuery({
    queryKey: ["courses"],
    queryFn: () => api.get<{ courses: Course[] }>("/courses"),
    staleTime: 10 * 60_000,
    select: (d) => d.courses,
  });
}

export function useCart() {
  const { me } = useSession();
  return useQuery({
    queryKey: ["cart"],
    queryFn: () => api.get<{ cart: CartItem[] }>("/cart"),
    enabled: Boolean(me),
    select: (d) => d.cart,
  });
}

export function useWishlist() {
  const { me } = useSession();
  return useQuery({
    queryKey: ["wishlist"],
    queryFn: () => api.get<{ wishlist: WishlistItem[] }>("/wishlist"),
    enabled: Boolean(me),
    select: (d) => d.wishlist,
  });
}
