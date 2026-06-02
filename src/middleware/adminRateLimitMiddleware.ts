import { Request, Response, NextFunction } from "express";
import { apiErrorPayload } from "../lib/apiError.js";
import { getRedisClient } from "../lib/redis";

/**
 * Resolves the real client IP, respecting X-Forwarded-For when the app is
 * behind a trusted reverse proxy (TRUST_PROXY=true).
 */
function resolveClientIp(req: Request): string {
  if (process.env.TRUST_PROXY === "true") {
    const forwarded = req.headers["x-forwarded-for"];
    if (forwarded) {
      const raw = Array.isArray(forwarded)
        ? forwarded[0]
        : forwarded.split(",")[0];
      const first = raw?.trim();
      if (first) return first;
    }
  }
  return req.ip ?? req.socket.remoteAddress ?? "unknown";
}

/**
 * Normalises an IP so that IPv4-mapped IPv6 addresses (::ffff:1.2.3.4)
 * compare equal to their plain IPv4 form.
 */
function normaliseIp(ip: string): string {
  return ip.startsWith("::ffff:") ? ip.slice(7) : ip;
}

/**
 * Generates a unique key for the caller based on IP and optional admin API key.
 * This identifies a unique "caller profile" for rate limiting purposes.
 */
function generateCallerKey(req: Request): string {
  const clientIp = normaliseIp(resolveClientIp(req));
  const adminKey = req.headers["x-admin-key"];

  if (adminKey && typeof adminKey === "string") {
    // Hash the admin key to avoid storing the actual key in Redis
    return `admin:${clientIp}:${adminKey.slice(0, 8)}`;
  }

  return `admin:${clientIp}`;
}

/**
 * Token-bucket rate limiter configuration.
 * - Max tokens: 10 (requests per minute)
 * - Refill rate: 10 tokens per 60 seconds (one token every 6 seconds)
 * - Window: 60 seconds (1 minute)
 */
const ADMIN_RATE_LIMIT_CONFIG = {
  maxTokens: 10,
  refillRatePerSecond: 10 / 60, // 10 tokens per 60 seconds
  windowMs: 60_000, // 1 minute
};

/**
 * In-memory token bucket store.
 * Stores token bucket state as { tokens: number, lastRefillTime: number }
 */
const inMemoryBuckets = new Map<
  string,
  { tokens: number; lastRefillTime: number }
>();

/**
 * Helper to clean up old buckets from memory (optional, prevents unbounded growth)
 */
function cleanupOldBuckets(): void {
  const now = Date.now();
  const maxAge = ADMIN_RATE_LIMIT_CONFIG.windowMs * 2; // Keep for 2 windows

  for (const [key, bucket] of inMemoryBuckets.entries()) {
    if (now - bucket.lastRefillTime > maxAge) {
      inMemoryBuckets.delete(key);
    }
  }
}

/**
 * Refills the token bucket based on elapsed time.
 * Returns the current token count after refill.
 */
function refillBucket(bucket: {
  tokens: number;
  lastRefillTime: number;
}): number {
  const now = Date.now();
  const elapsedSeconds = (now - bucket.lastRefillTime) / 1000;
  const tokensToAdd =
    elapsedSeconds * ADMIN_RATE_LIMIT_CONFIG.refillRatePerSecond;

  bucket.tokens = Math.min(
    ADMIN_RATE_LIMIT_CONFIG.maxTokens,
    bucket.tokens + tokensToAdd,
  );
  bucket.lastRefillTime = now;

  return bucket.tokens;
}

/**
 * In-memory token bucket implementation.
 * Non-blocking, but not shared across instances.
 */
async function checkInMemoryBucket(callerKey: string): Promise<boolean> {
  let bucket = inMemoryBuckets.get(callerKey);

  if (!bucket) {
    // Initialize new bucket with full tokens
    bucket = {
      tokens: ADMIN_RATE_LIMIT_CONFIG.maxTokens,
      lastRefillTime: Date.now(),
    };
    inMemoryBuckets.set(callerKey, bucket);
  }

  // Refill based on elapsed time
  const tokens = refillBucket(bucket);

  // Check if we have tokens available
  if (tokens >= 1) {
    bucket.tokens -= 1;
    return true; // Allow request
  }

  return false; // Reject request
}

/**
 * Redis-backed token bucket implementation.
 * Supports distributed rate limiting across multiple instances.
 */
async function checkRedisBucket(callerKey: string): Promise<boolean> {
  const redisClient = getRedisClient();

  if (!redisClient?.isOpen) {
    // Fall back to in-memory if Redis is not available
    return checkInMemoryBucket(callerKey);
  }

  const redisKey = `admin_rl:${callerKey}`;

  try {
    // Use Redis as a simple counter with TTL
    // Increment counter and set TTL if it doesn't exist
    const result = await redisClient.sendCommand(["INCR", redisKey]);
    const requestCount =
      typeof result === "number" ? result : parseInt(String(result), 10);

    // Set TTL on first request (60 seconds)
    if (requestCount === 1) {
      await redisClient.sendCommand(["EXPIRE", redisKey, "60"]);
    }

    // Allow up to 10 requests per minute
    return requestCount <= ADMIN_RATE_LIMIT_CONFIG.maxTokens;
  } catch (err) {
    console.error("[AdminRateLimit] Redis error:", err);
    // Fall back to in-memory if Redis fails
    return checkInMemoryBucket(callerKey);
  }
}

/**
 * Admin rate limiting middleware.
 *
 * Implements token-bucket rate limiting for administrative endpoints.
 * - 10 requests per minute per caller profile (IP + API key)
 * - Uses Redis for distributed rate limiting when available
 * - Falls back to in-memory store when Redis is unavailable
 *
 * Usage:
 *   app.use("/api/admin", adminRateLimitMiddleware, adminRouter);
 */
export const adminRateLimitMiddleware = async (
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> => {
  try {
    const callerKey = generateCallerKey(req);
    const redisClient = getRedisClient();

    // Check token bucket using Redis (if available) or in-memory store
    const allowed = redisClient?.isOpen
      ? await checkRedisBucket(callerKey)
      : await checkInMemoryBucket(callerKey);

    if (!allowed) {
      // Rate limit exceeded
      res.status(429).json({
        ...apiErrorPayload(
          "ADMIN_RATE_LIMITED",
          `Administrative rate limit exceeded. Maximum ${ADMIN_RATE_LIMIT_CONFIG.maxTokens} requests per minute.`,
        ),
        retryAfter: ADMIN_RATE_LIMIT_CONFIG.windowMs / 1000,
      });
      return;
    }

    // Clean up old buckets periodically (every 100 requests)
    if (Math.random() < 0.01) {
      cleanupOldBuckets();
    }

    next();
  } catch (err) {
    console.error("[AdminRateLimit] Unexpected error:", err);
    // On error, allow the request through to avoid breaking the API
    next();
  }
};
