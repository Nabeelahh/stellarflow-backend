import { Router } from "express";
import prisma from "../lib/prisma";

const router = Router();

// In-memory cache for status responses (TTL 3000ms)
let statusCache: { data: any; timestamp: number } = { data: null, timestamp: 0 };

/**
 * @swagger
 * /api/v1/status:
 *   get:
 *     tags:
 *       - Status
 *     summary: System status
 *     description: Returns DB health and last successful price sync time for dashboard indicators
 *     responses:
 *       '200':
 *         description: System status (green or red)
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 status:
 *                   type: string
 *                   enum: [green, red]
 *                 db:
 *                   type: string
 *                   enum: [ok, error]
 *                 lastSync:
 *                   type: string
 *                   format: date-time
 *                   nullable: true
 *                 timestamp:
 *                   type: string
 *                   format: date-time
 */
router.get("/", async (req, res) => {
  const now = Date.now();
  if (statusCache.data && now - statusCache.timestamp < 3000) {
    return res.json(statusCache.data);
  }

  let dbOk = false;
  let lastSync: string | null = null;

  try {
    await prisma.$queryRaw`SELECT 1`;
    dbOk = true;

    // Last successful price sync = most recent PriceHistory entry
    const latest = await prisma.priceHistory.findFirst({
      orderBy: { timestamp: "desc" },
      select: { timestamp: true },
    });

    lastSync = latest?.timestamp?.toISOString() ?? null;
  } catch {
    dbOk = false;
  }

  const result = {
    status: dbOk ? "green" : "red",
    db: dbOk ? "ok" : "error",
    lastSync,
    timestamp: new Date().toISOString(),
  };

  // Update cache
  statusCache = { data: result, timestamp: now };

  return res.json(result);
});

export default router;
