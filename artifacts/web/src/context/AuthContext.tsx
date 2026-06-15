import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { api, TOKEN_KEY } from "../api";
import type { AuthResponse, User } from "../types";

const USER_KEY = "caseband.user";

interface AuthCtx {
  user: User | null;
  login: (email: string, password: string) => Promise<User>;
  register: (name: string, email: string, password: string) => Promise<User>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx | null>(null);

function loadUser(): User | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(loadUser);

  const persist = useCallback((res: AuthResponse) => {
    localStorage.setItem(TOKEN_KEY, res.token);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    setUser(res.user);
    return res.user;
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api.post<AuthResponse>("/auth/login", {
        email,
        password,
      });
      return persist(res);
    },
    [persist],
  );

  const register = useCallback(
    async (name: string, email: string, password: string) => {
      const res = await api.post<AuthResponse>("/auth/register", {
        name,
        email,
        password,
      });
      return persist(res);
    },
    [persist],
  );

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem("caseband.course");
    setUser(null);
  }, []);

  return (
    <Ctx.Provider value={{ user, login, register, logout }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
