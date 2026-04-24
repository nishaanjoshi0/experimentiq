import { NextRequest, NextResponse } from "next/server";

import { getAuthToken } from "@/lib/auth";

const DEFAULT_FASTAPI_BASE_URL = "http://localhost:8000";

export async function POST(request: NextRequest) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json();
  const response = await fetch(
    new URL(
      "/api/v1/analytics/ga4/recommendations",
      process.env.FASTAPI_BASE_URL ?? DEFAULT_FASTAPI_BASE_URL
    ),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
      cache: "no-store",
    }
  );

  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
