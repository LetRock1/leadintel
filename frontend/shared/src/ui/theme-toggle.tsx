import { Moon, Sun } from "lucide-react";
import { useTheme } from "../lib";
import { IconButton } from "./button";

/** Switches between light and dark (the first choice follows the computer's setting). */
export function ThemeToggle({ className }: { className?: string }) {
  const { resolved, toggle } = useTheme();
  const toDark = resolved === "light";
  return (
    <IconButton
      label={toDark ? "Switch to dark theme" : "Switch to light theme"}
      onClick={toggle}
      className={className}
    >
      {toDark ? <Moon aria-hidden className="size-[18px]" /> : <Sun aria-hidden className="size-[18px]" />}
    </IconButton>
  );
}
