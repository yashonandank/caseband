import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FlaskConical, AlertCircle } from "lucide-react";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
      navigate("/courses");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <div className="w-full max-w-sm fade-up">
        <div className="mb-7 flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-b from-[var(--navy2)] to-[var(--navy)] text-white">
            <FlaskConical size={18} />
          </div>
          <div>
            <div className="text-[18px] font-bold tracking-tight">Caseband</div>
            <div className="text-[12px] text-[var(--ink3)]">
              Goizueta Case Simulations
            </div>
          </div>
        </div>

        <div className="card">
          <div className="page-label">Sign in</div>
          <h1 className="mb-5 text-[20px] font-bold">Welcome back</h1>

          {error && (
            <div className="strip strip-error mb-4">
              <AlertCircle size={16} className="mt-px shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="label">Emory email</label>
              <input
                className="field"
                type="email"
                placeholder="you@emory.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="label">Password</label>
              <input
                className="field"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <button
              className="btn btn-primary w-full justify-center"
              disabled={busy}
            >
              {busy && <span className="spinner" />}
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>

        <div className="mt-4 text-center text-[13px] text-[var(--ink3)]">
          No account?{" "}
          <Link to="/register" className="font-semibold text-[var(--navy2)]">
            Register
          </Link>
        </div>
      </div>
    </div>
  );
}
