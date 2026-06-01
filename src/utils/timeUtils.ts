/**
 * Ensure any Date-like value is stored as UTC with millisecond precision.
 *
 * All JS Date objects represent instants in time in UTC internally, but this
 * helper explicitly builds the UTC form to avoid local timezone artifacts when
 * parsing strings or Date objects.
 */
export function normalizeDateToUTC(value: Date | string | number): Date {
  const date =
    value instanceof Date ? new Date(value.getTime()) : new Date(value);

  if (Number.isNaN(date.getTime())) {
    throw new Error(`Invalid date value provided: ${value}`);
  }

  return new Date(
    Date.UTC(
      date.getUTCFullYear(),
      date.getUTCMonth(),
      date.getUTCDate(),
      date.getUTCHours(),
      date.getUTCMinutes(),
      date.getUTCSeconds(),
      date.getUTCMilliseconds(),
    ),
  );
}

/**
 * Convert a local Date to UTC ISO string.
 * Useful for logging and serialization.
 */
export function toUTCISOString(date: Date | string | number): string {
  const normalized = normalizeDateToUTC(date);
  return normalized.toISOString();
}

/**
 * Parse a UTC ISO string to a UTC Date object.
 * Ensures strict UTC interpretation without timezone conversion.
 */
export function parseUTCDate(isoString: string): Date {
  // ISO strings from toISOString() are already in UTC
  const date = new Date(isoString);

  if (Number.isNaN(date.getTime())) {
    throw new Error(`Invalid ISO date string: ${isoString}`);
  }

  // Ensure the result is strictly UTC
  return normalizeDateToUTC(date);
}

/**
 * Get the current time in UTC.
 * Replaces new Date() in audit logging to ensure consistency.
 */
export function nowUTC(): Date {
  return normalizeDateToUTC(new Date());
}

/**
 * Verify that a Date is correctly in UTC and matches its ISO representation.
 * Useful for testing and validation.
 */
export function isValidUTCDate(date: Date): boolean {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
    return false;
  }

  // Check that the date's milliseconds match its ISO string representation
  const isoString = date.toISOString();
  const reparsed = new Date(isoString);
  return date.getTime() === reparsed.getTime();
}
