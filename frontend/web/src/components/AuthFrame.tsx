import type { ReactNode } from "react";

/** The narrow column used by sign-up, sign-in and password pages. */
export function AuthFrame({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="mx-auto w-full max-w-[420px] px-5 pb-16 pt-12 sm:pt-16">
      <h1 className="text-[30px] font-semibold leading-tight text-ink">{title}</h1>
      {description && <p className="mt-2 text-[15px] text-ink-2">{description}</p>}
      <div className="mt-7">{children}</div>
      {footer && <div className="mt-8 border-t border-line pt-5 text-[14px] text-ink-2">{footer}</div>}
    </div>
  );
}
