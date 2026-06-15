import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import type { Course } from "../types";

const COURSE_KEY = "caseband.course";

interface CourseCtx {
  course: Course | null;
  setCourse: (c: Course | null) => void;
}

const Ctx = createContext<CourseCtx | null>(null);

function loadCourse(): Course | null {
  try {
    const raw = localStorage.getItem(COURSE_KEY);
    return raw ? (JSON.parse(raw) as Course) : null;
  } catch {
    return null;
  }
}

export function CourseProvider({ children }: { children: ReactNode }) {
  const [course, setCourseState] = useState<Course | null>(loadCourse);

  const setCourse = useCallback((c: Course | null) => {
    if (c) localStorage.setItem(COURSE_KEY, JSON.stringify(c));
    else localStorage.removeItem(COURSE_KEY);
    setCourseState(c);
  }, []);

  return (
    <Ctx.Provider value={{ course, setCourse }}>{children}</Ctx.Provider>
  );
}

export function useCourse(): CourseCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useCourse must be used within CourseProvider");
  return ctx;
}
