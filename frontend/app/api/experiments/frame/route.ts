import { NextRequest, NextResponse } from "next/server";

import { getAuthToken } from "@/lib/auth";

const DEFAULT_FASTAPI_BASE_URL = "http://localhost:8000";

export async function POST(request: NextRequest) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const body = (await request.json()) as { hypothesis?: string };
  const response = await fetch(
    new URL("/api/v1/experiments/frame", process.env.FASTAPI_BASE_URL ?? DEFAULT_FASTAPI_BASE_URL),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ hypothesis: body.hypothesis ?? "" }),
      cache: "no-store"
    }
  );

  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
