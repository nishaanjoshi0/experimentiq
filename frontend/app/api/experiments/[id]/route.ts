import { NextResponse } from "next/server";

import { getAuthToken } from "@/lib/auth";

const DEFAULT_FASTAPI_BASE_URL = "http://localhost:8000";

interface RouteContext {
  params: {
    id: string;
  };
}

export async function GET(_request: Request, context: RouteContext) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const response = await fetch(
    new URL(
      `/api/v1/experiments/${context.params.id}`,
      process.env.FASTAPI_BASE_URL ?? DEFAULT_FASTAPI_BASE_URL
    ),
    {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`
      },
      cache: "no-store"
    }
  );

  const data = await response.json();
  const experiment = data?.experiment ?? data;
  return NextResponse.json(experiment, { status: response.status });
}
