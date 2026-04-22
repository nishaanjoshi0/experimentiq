import { auth } from "@clerk/nextjs/server";

export async function getAuthToken(): Promise<string | null> {
  const { getToken } = await auth();
  return getToken();
}