import { NextRequest, NextResponse } from "next/server";
import { getAuthToken } from "@/lib/auth";

const BASE = process.env.FASTAPI_BASE_URL ?? "http://localhost:8000";

export async function GET(_request: NextRequest) {
  const token = await getAuthToken();
  if (!token) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });

  const response = await fetch(`${BASE}/api/v1/experiments/platforms/status`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  return NextResponse.json(await response.json(), { status: response.status });
}

export async function POST(request: NextRequest) {
  const token = await getAuthToken();
  if (!token) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });

  const platform = request.nextUrl.searchParams.get("platform");
  if (!platform) return NextResponse.json({ detail: "Missing platform" }, { status: 400 });

  const body = await request.json();
  const response = await fetch(`${BASE}/api/v1/experiments/platforms/${platform}/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  return NextResponse.json(await response.json(), { status: response.status });
}

export async function DELETE(request: NextRequest) {
  const token = await getAuthToken();
  if (!token) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });

  const platform = request.nextUrl.searchParams.get("platform");
  if (!platform) return NextResponse.json({ detail: "Missing platform" }, { status: 400 });

  const response = await fetch(`${BASE}/api/v1/experiments/platforms/${platform}/disconnect`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  return NextResponse.json(await response.json(), { status: response.status });
}
