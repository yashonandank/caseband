import { Link } from "react-router-dom";
import { FlaskConical, ArrowRight, ShieldCheck, Layers } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useCourse } from "../context/CourseContext";

export default function Dashboard() {
  const { user } = useAuth();
  const { course } = useCourse();
  const isProf = user?.role === "professor";

  return (
    <div className="fade-up">
      <div className="page-header">
        <div className="page-label">
          {course ? `${course.code} · ${course.name}` : "Caseband"}
        </div>
        <h1>Hi {user?.name?.split(" ")[0] ?? "there"}</h1>
        <p className="subtitle">
          {isProf
            ? "Author solvable, red-teamed case simulations from a source document."
            : "Work through your assigned case simulations and get graded instantly."}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="card">
          <Layers size={20} className="text-[var(--navy2)]" />
          <div className="mt-3 text-[15px] font-semibold">
            {isProf ? "Author a case" : "Open a case"}
          </div>
          <p className="muted mt-1 text-[13px]">
            {isProf
              ? "Paste a source document and let the writers' room build it."
              : "Set your decisions and submit for an instant grade."}
          </p>
        </div>
        <div className="card">
          <ShieldCheck size={20} className="text-[var(--green2)]" />
          <div className="mt-3 text-[15px] font-semibold">Proven solvable</div>
          <p className="muted mt-1 text-[13px]">
            Every case is red-teamed to guarantee a winning path exists.
          </p>
        </div>
        <div className="card">
          <FlaskConical size={20} className="text-[var(--amber)]" />
          <div className="mt-3 text-[15px] font-semibold">Outcome engine</div>
          <p className="muted mt-1 text-[13px]">
            Decisions feed a real KPI model with a rubric overlay.
          </p>
        </div>
      </div>

      <Link
        to="/simulation"
        className="btn btn-primary mt-6 inline-flex"
      >
        Go to Simulations <ArrowRight size={15} />
      </Link>
    </div>
  );
}
