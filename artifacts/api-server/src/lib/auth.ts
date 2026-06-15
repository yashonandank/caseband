// JWT auth + password hashing for the platform surface (professor/student).
// Tokens carry { sub: userId, role, email }; requireAuth populates req.user.
import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import type { NextFunction, Request, Response } from "express";

export type Role = "professor" | "student";

export interface AuthUser {
  id: string;
  role: Role;
  email: string;
}

// Augment Express Request so req.user is typed everywhere.
declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      user?: AuthUser;
    }
  }
}

const JWT_SECRET = process.env.JWT_SECRET ?? "caseband-dev-secret-change-me";
const JWT_EXPIRES_IN = "7d";

export async function hashPassword(plain: string): Promise<string> {
  return bcrypt.hash(plain, 10);
}

export async function verifyPassword(
  plain: string,
  hash: string,
): Promise<boolean> {
  return bcrypt.compare(plain, hash);
}

export function signToken(user: AuthUser): string {
  return jwt.sign({ sub: user.id, role: user.role, email: user.email }, JWT_SECRET, {
    expiresIn: JWT_EXPIRES_IN,
  });
}

export function verifyToken(token: string): AuthUser {
  const payload = jwt.verify(token, JWT_SECRET) as jwt.JwtPayload;
  if (!payload.sub || !payload.role) {
    throw new Error("Malformed token");
  }
  return {
    id: String(payload.sub),
    role: payload.role as Role,
    email: String(payload.email ?? ""),
  };
}

// Reads `Authorization: Bearer <jwt>`, sets req.user, else 401.
export function requireAuth(req: Request, res: Response, next: NextFunction): void {
  const header = req.headers.authorization ?? "";
  const [scheme, token] = header.split(" ");
  if (scheme !== "Bearer" || !token) {
    res.status(401).json({ error: "Missing or malformed Authorization header" });
    return;
  }
  try {
    req.user = verifyToken(token);
    next();
  } catch {
    res.status(401).json({ error: "Invalid or expired token" });
  }
}

// Guard a route to a single role; assumes requireAuth ran first.
export function requireRole(role: Role) {
  return (req: Request, res: Response, next: NextFunction): void => {
    if (!req.user) {
      res.status(401).json({ error: "Not authenticated" });
      return;
    }
    if (req.user.role !== role) {
      res.status(403).json({ error: `Requires ${role} role` });
      return;
    }
    next();
  };
}
