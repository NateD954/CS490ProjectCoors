import type { ButtonHTMLAttributes } from "react";
import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary";

const variants: Record<Variant, string> = {
  primary: "bg-violet-600 text-white hover:bg-violet-500",
  secondary: "bg-zinc-800 text-zinc-100 border border-zinc-700 hover:bg-zinc-700",
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  loading?: boolean;
};

export function Button({ variant = "primary", loading = false, className = "", children, disabled, ...rest }: Props) {
  return (
    <button
      disabled={disabled || loading}
      className={`inline-flex h-11 items-center justify-center gap-2 rounded-lg px-5 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-400 disabled:cursor-not-allowed disabled:opacity-60 ${variants[variant]} ${className}`}
      {...rest}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}
