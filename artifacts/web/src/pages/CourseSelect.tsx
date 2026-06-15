import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BookOpen, AlertCircle, ChevronRight, ArrowRight } from "lucide-react";
import { api } from "../api";
import { useCourse } from "../context/CourseContext";
import type { Course } from "../types";

export default function CourseSelect() {
  const { setCourse } = useCourse();
  const navigate = useNavigate();
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .get<Course[]>("/courses")
      .then((c) => live && setCourses(c))
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, []);

  function pick(c: Course) {
    setCourse(c);
    navigate("/simulation");
  }

  function skip() {
    setCourse(null);
    navigate("/simulation");
  }

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <div className="w-full max-w-md fade-up">
        <div className="page-header">
          <div className="page-label">Your courses</div>
          <h1>Select a course</h1>
          <p className="subtitle">
            Caseband scopes simulations to a course. Pick one to continue.
          </p>
        </div>

        {error && (
          <div className="strip strip-error mb-4">
            <AlertCircle size={16} className="mt-px shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {courses === null && !error && (
          <div className="card flex items-center gap-3 text-[var(--ink3)]">
            <span className="spinner" /> Loading courses…
          </div>
        )}

        {courses && courses.length === 0 && (
          <div className="strip strip-info mb-4">
            <BookOpen size={16} className="mt-px shrink-0" />
            <span>No courses found yet. You can continue without one.</span>
          </div>
        )}

        <div className="space-y-2">
          {courses?.map((c) => (
            <button
              key={c.id}
              onClick={() => pick(c)}
              className="card flex w-full items-center justify-between text-left transition-colors hover:border-[var(--line2)]"
            >
              <div>
                <div className="text-[12px] font-semibold text-[var(--navy2)]">
                  {c.code} · {c.semester}
                </div>
                <div className="text-[15px] font-semibold">{c.name}</div>
              </div>
              <ChevronRight size={18} className="text-[var(--ink4)]" />
            </button>
          ))}
        </div>

        <button
          onClick={skip}
          className="btn btn-ghost mt-4 w-full justify-center"
        >
          Continue without a course <ArrowRight size={15} />
        </button>
      </div>
    </div>
  );
}
