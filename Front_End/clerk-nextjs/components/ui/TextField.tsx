import type { InputHTMLAttributes } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "id"> & {
  id: string;
  label: string;
  error?: string;
  hint?: string;
};

// Labeled input with consistent hint and error text.
export function TextField({ id, label, error, hint, className = "", ...rest }: Props) {
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-zinc-200">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        className={`h-11 w-full rounded-lg border bg-zinc-950 px-4 text-base text-zinc-100 placeholder:text-zinc-500 read-only:text-zinc-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-400 ${
          error ? "border-red-600" : "border-zinc-700"
        } ${className}`}
        {...rest}
      />
      {error ? (
        <p id={`${id}-error`} className="text-sm text-red-400">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-sm text-zinc-400">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
