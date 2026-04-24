import { NextRequest, NextResponse } from "next/server";

import { getAuthToken } from "@/lib/auth";

const DEFAULT_FASTAPI_BASE_URL = "http://localhost:8000";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const state = searchParams.get("state");

  if (!code) {
    return NextResponse.redirect(new URL("/analytics?error=no_code", request.url));
  }

  const token = await getAuthToken();
  if (!token) {
    return NextResponse.redirect(new URL("/sign-in", request.url));
  }

  const response = await fetch(
    new URL(
      "/api/v1/auth/google/callback",
      process.env.FASTAPI_BASE_URL ?? DEFAULT_FASTAPI_BASE_URL
    ),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ code, state }),
      cache: "no-store",
    }
  );

  if (!response.ok) {
    return NextResponse.redirect(new URL("/analytics?error=oauth_failed", request.url));
  }

  return NextResponse.redirect(new URL("/analytics?connected=true", request.url));
}
