import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  FlaskConical,
  BookOpen,
  GraduationCap,
  LogOut,
  ChevronDown,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useCourse } from "../context/CourseContext";

const navItem =
  "flex items-center gap-3 px-3 py-2 rounded-lg text-[14px] font-medium transition-colors";

export function AppShell() {
  const { user, logout } = useAuth();
  const { course } = useCourse();
  const navigate = useNavigate();

  const link = ({ isActive }: { isActive: boolean }) =>
    `${navItem} ${
      isActive
        ? "bg-[var(--panel2)] text-[var(--ink)]"
        : "text-[var(--ink3)] hover:text-[var(--ink2)] hover:bg-[var(--bg2)]"
    }`;

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="w-60 shrink-0 border-r border-[var(--line)] bg-[var(--bg2)] flex flex-col">
        <div className="px-5 py-5 border-b border-[var(--line)]">
          <div className="flex items-center gap-2">
            <div className="grid h-7 w-7 place-items-center rounded-md bg-gradient-to-b from-[var(--navy2)] to-[var(--navy)] text-white">
              <FlaskConical size={16} />
            </div>
            <div className="text-[15px] font-bold tracking-tight">Caseband</div>
          </div>
          <div className="mt-1 text-[11px] uppercase tracking-wider text-[var(--ink4)]">
            Goizueta
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          <NavLink to="/dashboard" className={link}>
            <LayoutDashboard size={17} /> Dashboard
          </NavLink>
          <NavLink to="/simulation" className={link}>
            {user?.role === "professor" ? (
              <>
                <BookOpen size={17} /> Case Authoring
              </>
            ) : (
              <>
                <FlaskConical size={17} /> Play a Case
              </>
            )}
          </NavLink>
        </nav>

        <div className="border-t border-[var(--line)] p-3">
          <button
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[var(--ink3)] hover:text-[var(--ink)] hover:bg-[var(--bg)] transition-colors"
            onClick={() => {
              logout();
              navigate("/login");
            }}
          >
            <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[var(--panel2)] text-[var(--ink2)]">
              <GraduationCap size={15} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-medium text-[var(--ink2)]">
                {user?.name ?? "Guest"}
              </div>
              <div className="truncate text-[11px] capitalize text-[var(--ink4)]">
                {user?.role ?? "—"}
              </div>
            </div>
            <LogOut size={15} />
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-[var(--line)] bg-[var(--bg2)]/60 px-7 py-3.5 backdrop-blur">
          <button
            className="flex items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--panel)] px-3 py-1.5 text-[13px] text-[var(--ink2)] hover:border-[var(--line2)] transition-colors"
            onClick={() => navigate("/courses")}
          >
            <BookOpen size={14} className="text-[var(--navy2)]" />
            {course ? (
              <span>
                <span className="font-semibold text-[var(--ink)]">
                  {course.code}
                </span>{" "}
                · {course.name}
              </span>
            ) : (
              <span className="text-[var(--ink3)]">Select a course</span>
            )}
            <ChevronDown size={14} className="text-[var(--ink4)]" />
          </button>
        </header>

        <main className="flex-1 overflow-y-auto px-7 py-7">
          <div className="mx-auto max-w-5xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
