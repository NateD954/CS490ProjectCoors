"use client";
import { useState, type FormEvent } from "react";
import { Button } from "./ui/Button";

type Props = {
  onSearch: (query: string) => void;
  loading?: boolean;
};

export function SearchBar({ onSearch, loading = false }: Props) {
  const [query, setQuery] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    onSearch(query);
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row">
      <label htmlFor="place-search" className="sr-only">
        Business name or location
      </label>
      <input
        id="place-search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search a business or location, e.g. Joe's Pizza Newark"
        className="h-11 flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-4 text-base text-zinc-100 placeholder:text-zinc-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-400"
      />
      <Button type="submit" loading={loading}>
        Search reviews
      </Button>
    </form>
  );
}
