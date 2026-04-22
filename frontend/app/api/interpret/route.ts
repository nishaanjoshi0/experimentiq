import { NextRequest, NextResponse } from "next/server";

import { getAuthToken } from "@/lib/auth";

const DEFAULT_FASTAPI_BASE_URL = "http://localhost:8000";

export async function POST(request: NextRequest) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const body = (await request.json()) as { id?: string };
  if (!body.id) {
    return NextResponse.json({ detail: "Experiment id is required." }, { status: 400 });
  }

  const response = await fetch(
    new URL(
      `/api/v1/experiments/${body.id}/interpret`,
      process.env.FASTAPI_BASE_URL ?? DEFAULT_FASTAPI_BASE_URL
    ),
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`
      },
      cache: "no-store"
    }
  );

  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
