import { NextFunction, Request, Response } from "express";
import { verifyToken, getActiveSession, cleanupExpiredSessions } from "../utils/jwt.js";

declare global {
  namespace Express {
    interface Request {
      user?: {
        userId: number;
        email: string;
        role: string;
        group?: string;        // Added for future group isolation
        permissions?: string[]; // Added for fine-grained control
      };
      sessionId?: number;
    }
  }
}

let sessionCleanupTimer: NodeJS.Timeout | null = null;

function startSessionCleanup(): void {
  if (sessionCleanupTimer) return;
  sessionCleanupTimer = setInterval(async () => {
    try {
      await cleanupExpiredSessions();
    } catch (error) {
      console.error("[JWT] Session cleanup error:", error);
    }
  }, 60 * 60 * 1000);
}

export const jwtMiddleware = (
  req: Request,
  res: Response,
  next: NextFunction,
): void => {
  if (!sessionCleanupTimer) {
    startSessionCleanup();
  }

  const authHeader = req.headers.authorization;

  if (!authHeader?.startsWith("Bearer ")) {
    return next();
  }

  const token = authHeader.substring(7);

  const payload = verifyToken(token);

  if (!payload) {
    return next();
  }

  // Updated user object with role (already present) + optional fields
  (req as Request & { user: any }).user = {
    userId: payload.userId,
    email: payload.email,
    role: payload.role || 'OBSERVER',           // Default to OBSERVER if missing
    group: payload.group,
    permissions: payload.permissions,
  };

  next();
};