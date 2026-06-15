// Lazy Supabase service-role client. Express owns platform tables (platform_users,
// platform_courses, platform_enrollments) and writes with the service role.
// Import-safe: the client is only created on first use, so the server boots even
// without creds (the Caseband proxy half works without Supabase).
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let _client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (_client) return _client;
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) {
    throw new Error(
      "Supabase not configured: set SUPABASE_URL and SUPABASE_SERVICE_KEY",
    );
  }
  _client = createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return _client;
}
