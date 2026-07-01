import { NextRequest, NextResponse } from "next/server";
import { getAuthToken } from "@/lib/auth";

const BASE = process.env.FASTAPI_BASE_URL ?? "http://localhost:8000";

export async function GET(request: NextRequest) {
  const token = await getAuthToken();
  if (!token) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });

  const response = await fetch(`${BASE}/api/v1/analytics/platforms/status`, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
