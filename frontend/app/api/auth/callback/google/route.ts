import { NextRequest, NextResponse } from "next/server";

const DEFAULT_FASTAPI_BASE_URL = "http://localhost:8000";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const state = searchParams.get("state");

  if (!code) {
    return NextResponse.redirect(new URL("/analytics?error=no_code", request.url));
  }

  try {
    const response = await fetch(
      new URL("/api/v1/auth/google/callback", process.env.FASTAPI_BASE_URL ?? DEFAULT_FASTAPI_BASE_URL),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, state }),
        cache: "no-store",
        signal: AbortSignal.timeout(20_000),
      }
    );

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const detail = (body as { detail?: string }).detail ?? "oauth_failed";
      return NextResponse.redirect(new URL(`/analytics?error=${encodeURIComponent(detail)}`, request.url));
    }
  } catch {
    return NextResponse.redirect(new URL("/analytics?error=callback_timeout", request.url));
  }

  return NextResponse.redirect(new URL("/analytics?connected=true", request.url));
}
