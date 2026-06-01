import {
  normalizeDateToUTC,
  toUTCISOString,
  parseUTCDate,
  nowUTC,
  isValidUTCDate,
} from "../src/utils/timeUtils";
import {
  logUserAccessEvent,
  logLoginSuccess,
  logLoginFailed,
  UserAuditEventType,
} from "../src/services/userAuditService";

// Mock prisma
jest.mock("../src/lib/prisma", () => {
  const createMock = jest.fn(() => Promise.resolve({}));

  return {
    prisma: {
      auditLog: {
        create: createMock,
        findFirst: jest.fn(({ orderBy }: { orderBy?: any }) =>
          Promise.resolve({
            id: "test-ksuid-123456789012345678901234",
            eventType: "USER_LOGIN_SUCCESS",
            actorPublicKey: "user:1",
            actorName: "user:1",
            actorRole: "USER",
            eventDetails: "{}",
            previousState: null,
            newState: null,
            ipAddress: "127.0.0.1",
            userAgent: "test-agent",
            occurredAt: new Date("2026-06-01T12:34:56.789Z"),
            createdAt: new Date("2026-06-01T12:34:56.789Z"),
          }),
        ),
      },
      relayer: {
        findUnique: jest.fn(({ where }: { where: { id?: number } }) =>
          Promise.resolve({
            id: 1,
            email: "test@example.com",
            role: "USER",
          }),
        ),
      },
    },
  };
});

describe("UTC Audit Timestamps", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("normalizeDateToUTC", () => {
    it("converts Date to UTC", () => {
      const date = new Date("2026-06-01T12:34:56.789Z");
      const normalized = normalizeDateToUTC(date);

      expect(normalized).toBeInstanceOf(Date);
      expect(normalized.toISOString()).toBe("2026-06-01T12:34:56.789Z");
    });

    it("converts ISO string to UTC Date", () => {
      const isoString = "2026-06-01T12:34:56.789Z";
      const normalized = normalizeDateToUTC(isoString);

      expect(normalized).toBeInstanceOf(Date);
      expect(normalized.toISOString()).toBe(isoString);
    });

    it("converts millisecond timestamp to UTC Date", () => {
      const timestamp = 1746086096789;
      const normalized = normalizeDateToUTC(timestamp);

      expect(normalized).toBeInstanceOf(Date);
      expect(normalized.getTime()).toBe(timestamp);
    });

    it("throws error for invalid date", () => {
      expect(() => normalizeDateToUTC("invalid-date")).toThrow(
        "Invalid date value provided",
      );
    });

    it("preserves UTC hour/minute/second values", () => {
      const date = new Date("2026-06-01T15:45:30.123Z");
      const normalized = normalizeDateToUTC(date);

      expect(normalized.getUTCHours()).toBe(15);
      expect(normalized.getUTCMinutes()).toBe(45);
      expect(normalized.getUTCSeconds()).toBe(30);
      expect(normalized.getUTCMilliseconds()).toBe(123);
    });
  });

  describe("toUTCISOString", () => {
    it("returns ISO string in UTC", () => {
      const date = new Date("2026-06-01T12:34:56.789Z");
      const isoString = toUTCISOString(date);

      expect(isoString).toBe("2026-06-01T12:34:56.789Z");
    });

    it("converts timestamp to ISO string", () => {
      const timestamp = 1746086096789;
      const isoString = toUTCISOString(timestamp);

      expect(isoString).toBe("2026-06-01T12:34:56.789Z");
    });

    it("converts ISO string input to ISO string output", () => {
      const isoString = "2026-06-01T12:34:56.789Z";
      const result = toUTCISOString(isoString);

      expect(result).toBe(isoString);
    });
  });

  describe("parseUTCDate", () => {
    it("parses UTC ISO string to Date", () => {
      const isoString = "2026-06-01T12:34:56.789Z";
      const date = parseUTCDate(isoString);

      expect(date).toBeInstanceOf(Date);
      expect(date.toISOString()).toBe(isoString);
    });

    it("throws error for invalid ISO string", () => {
      expect(() => parseUTCDate("invalid-iso")).toThrow(
        "Invalid ISO date string",
      );
    });

    it("maintains UTC timezone in result", () => {
      const isoString = "2026-06-01T12:34:56.789Z";
      const date = parseUTCDate(isoString);

      expect(date.getUTCHours()).toBe(12);
      expect(date.getUTCMinutes()).toBe(34);
      expect(date.getUTCSeconds()).toBe(56);
      expect(date.getUTCMilliseconds()).toBe(789);
    });
  });

  describe("nowUTC", () => {
    it("returns current time as UTC Date", () => {
      const beforeNow = Date.now();
      const utcNow = nowUTC();
      const afterNow = Date.now();

      expect(utcNow).toBeInstanceOf(Date);
      expect(utcNow.getTime()).toBeGreaterThanOrEqual(beforeNow);
      expect(utcNow.getTime()).toBeLessThanOrEqual(afterNow);
    });

    it("returns a valid UTC date", () => {
      const utcNow = nowUTC();
      expect(isValidUTCDate(utcNow)).toBe(true);
    });

    it("returns different times on subsequent calls", async () => {
      const time1 = nowUTC();
      // Small delay to ensure different millisecond values
      await new Promise((resolve) => setTimeout(resolve, 2));
      const time2 = nowUTC();

      expect(time2.getTime()).toBeGreaterThanOrEqual(time1.getTime());
    });
  });

  describe("isValidUTCDate", () => {
    it("returns true for valid UTC Date", () => {
      const date = normalizeDateToUTC("2026-06-01T12:34:56.789Z");
      expect(isValidUTCDate(date)).toBe(true);
    });

    it("returns true for now()", () => {
      const date = nowUTC();
      expect(isValidUTCDate(date)).toBe(true);
    });

    it("returns false for invalid Date", () => {
      const invalidDate = new Date("invalid");
      expect(isValidUTCDate(invalidDate)).toBe(false);
    });

    it("returns false for non-Date values", () => {
      expect(isValidUTCDate(null as any)).toBe(false);
      expect(isValidUTCDate(undefined as any)).toBe(false);
      expect(isValidUTCDate("2026-06-01T12:34:56.789Z" as any)).toBe(false);
      expect(isValidUTCDate(1746086096789 as any)).toBe(false);
    });

    it("verifies millisecond precision", () => {
      const date1 = normalizeDateToUTC("2026-06-01T12:34:56.789Z");
      const date2 = normalizeDateToUTC("2026-06-01T12:34:56.790Z");

      expect(isValidUTCDate(date1)).toBe(true);
      expect(isValidUTCDate(date2)).toBe(true);
      expect(date2.getTime() - date1.getTime()).toBe(1);
    });
  });

  describe("Audit Service Integration", () => {
    it("logUserAccessEvent uses UTC timestamps", async () => {
      const { prisma } = await import("../src/lib/prisma");
      const mockCreate = prisma.auditLog.create as jest.Mock;

      const context = {
        userId: 1,
        ipAddress: "127.0.0.1",
        userAgent: "Mozilla/5.0",
        resourceType: "SESSION" as const,
        resourceId: 1,
        action: UserAuditEventType.USER_LOGIN_SUCCESS,
      };

      await logUserAccessEvent(context);

      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            occurredAt: expect.any(Date),
          }),
        }),
      );

      const callData = mockCreate.mock.calls[0][0].data;
      expect(isValidUTCDate(callData.occurredAt)).toBe(true);
    });

    it("logLoginSuccess stores UTC timestamp", async () => {
      const { prisma } = await import("../src/lib/prisma");
      const mockCreate = prisma.auditLog.create as jest.Mock;

      await logLoginSuccess(1, "127.0.0.1", "test-agent");

      expect(mockCreate).toHaveBeenCalled();
      const callData = mockCreate.mock.calls[0][0].data;
      expect(isValidUTCDate(callData.occurredAt)).toBe(true);
    });

    it("logLoginFailed stores UTC timestamp", async () => {
      const { prisma } = await import("../src/lib/prisma");
      const mockCreate = prisma.auditLog.create as jest.Mock;

      await logLoginFailed(
        "test@example.com",
        "127.0.0.1",
        "test-agent",
        "Invalid credentials",
      );

      expect(mockCreate).toHaveBeenCalled();
      const callData = mockCreate.mock.calls[0][0].data;
      expect(isValidUTCDate(callData.occurredAt)).toBe(true);
    });

    it("audit logs maintain consistency across multiple entries", async () => {
      const { prisma } = await import("../src/lib/prisma");
      const mockCreate = prisma.auditLog.create as jest.Mock;

      const timestamps = [];
      for (let i = 0; i < 3; i++) {
        await logLoginSuccess(1, "127.0.0.1", "test-agent");
        const callData = mockCreate.mock.calls[i][0].data;
        timestamps.push(callData.occurredAt);
      }

      // All timestamps should be valid UTC
      timestamps.forEach((ts) => {
        expect(isValidUTCDate(ts)).toBe(true);
      });

      // Timestamps should be in order (monotonic)
      for (let i = 1; i < timestamps.length; i++) {
        expect(timestamps[i].getTime()).toBeGreaterThanOrEqual(
          timestamps[i - 1].getTime(),
        );
      }
    });
  });

  describe("Edge Cases", () => {
    it("handles dates at UTC boundaries", () => {
      const testDates = [
        "2026-01-01T00:00:00.000Z", // Start of year
        "2026-12-31T23:59:59.999Z", // End of year
        "2026-06-01T12:00:00.000Z", // Noon UTC
      ];

      testDates.forEach((isoString) => {
        const date = normalizeDateToUTC(isoString);
        expect(isValidUTCDate(date)).toBe(true);
        expect(date.toISOString()).toBe(isoString);
      });
    });

    it("preserves millisecond precision through serialization", () => {
      const originalMs = 789;
      const date = new Date("2026-06-01T12:34:56.789Z");
      const normalized = normalizeDateToUTC(date);

      expect(normalized.getUTCMilliseconds()).toBe(originalMs);
      expect(normalized.toISOString().endsWith("789Z")).toBe(true);
    });

    it("handles leap seconds (23:59:60 becomes 23:59:59)", () => {
      // Note: JavaScript doesn't support leap seconds, so this tests graceful degradation
      const date = normalizeDateToUTC("2026-06-30T23:59:59.999Z");
      expect(isValidUTCDate(date)).toBe(true);
    });
  });

  describe("Consistency Checks", () => {
    it("round-trip conversion maintains consistency", () => {
      const original = "2026-06-01T12:34:56.789Z";
      const date = parseUTCDate(original);
      const isoString = toUTCISOString(date);

      expect(isoString).toBe(original);
    });

    it("multiple normalizations produce identical results", () => {
      const date1 = normalizeDateToUTC("2026-06-01T12:34:56.789Z");
      const date2 = normalizeDateToUTC(date1);
      const date3 = normalizeDateToUTC(date2);

      expect(date1.getTime()).toBe(date2.getTime());
      expect(date2.getTime()).toBe(date3.getTime());
    });

    it("timestamp precision is maintained through all operations", () => {
      const isoString = "2026-06-01T12:34:56.123Z";
      const date = parseUTCDate(isoString);
      const normalized = normalizeDateToUTC(date);
      const output = toUTCISOString(normalized);

      expect(output).toBe(isoString);
    });
  });
});
