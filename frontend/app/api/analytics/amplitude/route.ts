import { NextRequest, NextResponse } from "next/server";
import { getAuthToken } from "@/lib/auth";

const BASE = process.env.FASTAPI_BASE_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const token = await getAuthToken();
  if (!token) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });

  const action = request.nextUrl.searchParams.get("action") ?? "recommendations";
  const body = await request.json();

  const response = await fetch(`${BASE}/api/v1/analytics/amplitude/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}

export async function DELETE(request: NextRequest) {
  const token = await getAuthToken();
  if (!token) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });

  const response = await fetch(`${BASE}/api/v1/analytics/amplitude/disconnect`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
