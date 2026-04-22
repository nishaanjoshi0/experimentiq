"use client";

import Link from "next/link";
import { SignedIn, SignedOut, UserButton } from "@clerk/nextjs";

export function NavAuth() {
  return (
    <div className="flex items-center gap-4 text-sm text-[var(--text-muted)]">
      <SignedOut>
        <Link
          href="/sign-in"
          className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-4 py-2 transition duration-150 ease-in hover:border-[var(--primary)] hover:text-[var(--text-primary)]"
        >
          Sign In
        </Link>
        <Link
          href="/sign-up"
          className="rounded-full bg-[var(--primary)] px-4 py-2 font-medium text-white shadow-[0_0_28px_rgba(99,102,241,0.35)] transition duration-150 ease-in hover:brightness-110"
        >
          Sign Up
        </Link>
      </SignedOut>
      <SignedIn>
        <UserButton />
      </SignedIn>
    </div>
  );
}
