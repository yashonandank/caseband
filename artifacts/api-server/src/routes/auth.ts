// Auth routes: register + login against platform_users. Emory-only.
import { Router, type Request, type Response } from "express";
import { getSupabase } from "../lib/supabase";
import {
  hashPassword,
  verifyPassword,
  signToken,
  type Role,
} from "../lib/auth";

export const auth = Router();

interface UserRow {
  id: string;
  name: string;
  email: string;
  role: Role;
  password_hash: string;
}

const publicUser = (u: UserRow) => ({
  id: u.id,
  name: u.name,
  email: u.email,
  role: u.role,
});

auth.post("/register", async (req: Request, res: Response) => {
  try {
    const { name, email, password } = req.body ?? {};
    if (!name || !email || !password) {
      res.status(400).json({ error: "name, email, and password are required" });
      return;
    }
    const normEmail = String(email).trim().toLowerCase();
    if (!normEmail.endsWith("@emory.edu")) {
      res.status(422).json({ error: "Email must end with @emory.edu" });
      return;
    }
    const role: Role = req.body?.role === "professor" ? "professor" : "student";
    const sb = getSupabase();

    const existing = await sb
      .from("platform_users")
      .select("id")
      .eq("email", normEmail)
      .maybeSingle();
    if (existing.error) throw new Error(existing.error.message);
    if (existing.data) {
      res.status(409).json({ error: "An account with that email already exists" });
      return;
    }

    const password_hash = await hashPassword(String(password));
    const ins = await sb
      .from("platform_users")
      .insert({ name, email: normEmail, role, password_hash })
      .select("id, name, email, role, password_hash")
      .single();
    if (ins.error) throw new Error(ins.error.message);

    const user = ins.data as UserRow;
    res.json({ token: signToken({ id: user.id, role: user.role, email: user.email }), user: publicUser(user) });
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});

auth.post("/login", async (req: Request, res: Response) => {
  try {
    const { email, password } = req.body ?? {};
    if (!email || !password) {
      res.status(400).json({ error: "email and password are required" });
      return;
    }
    const normEmail = String(email).trim().toLowerCase();
    const sb = getSupabase();
    const found = await sb
      .from("platform_users")
      .select("id, name, email, role, password_hash")
      .eq("email", normEmail)
      .maybeSingle();
    if (found.error) throw new Error(found.error.message);
    const user = found.data as UserRow | null;
    if (!user || !(await verifyPassword(String(password), user.password_hash))) {
      res.status(401).json({ error: "Invalid email or password" });
      return;
    }
    res.json({ token: signToken({ id: user.id, role: user.role, email: user.email }), user: publicUser(user) });
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});
