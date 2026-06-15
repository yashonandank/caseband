// Course routes: list (role-scoped) + create (professor). Backed by
// platform_courses and platform_enrollments.
import { Router, type Request, type Response } from "express";
import { getSupabase } from "../lib/supabase";
import { requireAuth, requireRole } from "../lib/auth";

export const courses = Router();
courses.use(requireAuth);

interface CourseRow {
  id: string;
  code: string;
  name: string;
  semester: string;
  professor_id: string;
}

// GET /courses — professor: courses they own; student: courses they're enrolled in.
courses.get("/", async (req: Request, res: Response) => {
  try {
    const user = req.user!;
    const sb = getSupabase();

    if (user.role === "professor") {
      const r = await sb
        .from("platform_courses")
        .select("id, code, name, semester, professor_id")
        .eq("professor_id", user.id);
      if (r.error) throw new Error(r.error.message);
      res.json(r.data ?? []);
      return;
    }

    // student: resolve enrolled course ids, then fetch those courses.
    const enr = await sb
      .from("platform_enrollments")
      .select("course_id")
      .eq("student_id", user.id);
    if (enr.error) throw new Error(enr.error.message);
    const ids = (enr.data ?? []).map((e: { course_id: string }) => e.course_id);
    if (ids.length === 0) {
      res.json([]);
      return;
    }
    const r = await sb
      .from("platform_courses")
      .select("id, code, name, semester, professor_id")
      .in("id", ids);
    if (r.error) throw new Error(r.error.message);
    res.json(r.data ?? []);
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});

// POST /courses (professor) — create a course owned by the caller.
courses.post("/", requireRole("professor"), async (req: Request, res: Response) => {
  try {
    const { code, name, semester } = req.body ?? {};
    if (!code || !name || !semester) {
      res.status(400).json({ error: "code, name, and semester are required" });
      return;
    }
    const sb = getSupabase();
    const ins = await sb
      .from("platform_courses")
      .insert({ code, name, semester, professor_id: req.user!.id })
      .select("id, code, name, semester, professor_id")
      .single();
    if (ins.error) throw new Error(ins.error.message);
    res.json(ins.data as CourseRow);
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});
