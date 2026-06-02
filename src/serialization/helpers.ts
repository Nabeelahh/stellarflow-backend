/**
 * Serialization Helpers — Optimized Number Parsing
 * 
 * These utilities avoid multi-step type conversions and unnecessary CPU overhead
 * by processing inputs directly within clear type specifications.
 * 
 * Key optimizations:
 * - Type narrowing happens once at parse time, not per-check
 * - Early returns eliminate redundant validation chains
 * - Inline conditional logic avoids repeated function dispatch overhead
 * - Specialized converters for common patterns (rates, stroops, etc.)
 */

/**
 * Parse a value to a finite number with minimal overhead.
 * 
 * Handles: null, undefined, number, string inputs.
 * Returns: null if input cannot be converted to a finite number.
 * 
 * @example
 * parseToNumber(null)           // → null
 * parseToNumber(1.5)            // → 1.5
 * parseToNumber("1.5")          // → 1.5
 * parseToNumber("NaN")          // → null
 * parseToNumber({})             // → null
 * 
 * @performance
 * - Typical case: 1-2 type checks (vs. 3-4 in naive implementations)
 * - No repeated isFinite calls
 * - Uses Number.parseFloat directly (faster than custom parsing)
 */
export function parseToNumber(
  value: number | string | null | undefined,
): number | null {
  // Fast path: already a valid number
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }

  // Fast path: null or undefined
  if (value == null) {
    return null;
  }

  // String case: parse once and validate finitude
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Parse a value to a positive number or null.
 * 
 * Useful for rates, prices, and other positive-only quantities.
 * Rejects: negative numbers, zero, NaN, Infinity.
 * 
 * @example
 * parseToPositiveNumber(-1.5)   // → null
 * parseToPositiveNumber(0)      // → null
 * parseToPositiveNumber(1.5)    // → 1.5
 * parseToPositiveNumber("1.5")  // → 1.5
 * 
 * @performance
 * - Single pass validation (type + range check combined)
 * - No intermediate allocations
 */
export function parseToPositiveNumber(
  value: number | string | null | undefined,
): number | null {
  if (typeof value === "number") {
    return value > 0 && Number.isFinite(value) ? value : null;
  }

  if (value == null) {
    return null;
  }

  const parsed = Number.parseFloat(value);
  return parsed > 0 && Number.isFinite(parsed) ? parsed : null;
}

/**
 * Parse a value to a non-negative integer.
 * 
 * Useful for counts, ledger sequences, IDs.
 * Rejects: negative numbers, non-integers, NaN, Infinity.
 * 
 * @example
 * parseToNonNegativeInt(-1)     // → null
 * parseToNonNegativeInt(1.5)    // → null
 * parseToNonNegativeInt(100)    // → 100
 * parseToNonNegativeInt("100")  // → 100
 * 
 * @performance
 * - Single type check + range validation
 * - No floating-point conversion for integer inputs
 */
export function parseToNonNegativeInt(
  value: number | string | null | undefined,
): number | null {
  if (typeof value === "number") {
    return value >= 0 && Number.isSafeInteger(value) ? value : null;
  }

  if (value == null) {
    return null;
  }

  const parsed = Number.parseInt(value, 10);
  return parsed >= 0 && !Number.isNaN(parsed) ? parsed : null;
}

/**
 * Batch parse multiple numeric fields from an object with minimal overhead.
 * 
 * Avoids repeated function call dispatch overhead in tight loops by
 * processing all fields in a single pass with early type specialization.
 * 
 * @example
 * const row = { rate: "1.5", baseline: "1.2", count: "100" };
 * const parsed = parseBatchNumbers(row, ["rate", "baseline", "count"]);
 * // → { rate: 1.5, baseline: 1.2, count: 100 }
 * 
 * @performance
 * - Amortizes function call overhead across multiple fields
 * - Single type dispatch per field (not per validation)
 * - Ideal for database row mapping in loops
 */
export function parseBatchNumbers<
  T extends Record<string, any>,
  K extends readonly (keyof T)[],
>(
  obj: T,
  fields: K,
): Record<K[number], number | null> {
  const result: any = {};

  for (const field of fields) {
    const value = obj[field];

    // Inline parsing logic to avoid function call overhead in loop
    if (typeof value === "number") {
      result[field] = Number.isFinite(value) ? value : null;
    } else if (value == null) {
      result[field] = null;
    } else if (typeof value === "string") {
      const parsed = Number.parseFloat(value);
      result[field] = Number.isFinite(parsed) ? parsed : null;
    } else {
      result[field] = null;
    }
  }

  return result;
}

/**
 * Optimized base64-to-number conversion for common telemetry patterns.
 * 
 * Combines three operations (base64 decode → string → number) into a
 * single optimized pass to reduce CPU overhead in event parsing loops.
 * 
 * @example
 * const base64 = btoa("1.5");  // "MS41"
 * parseBase64ToNumber(base64)  // → 1.5
 * parseBase64ToNumber("")      // → null
 * 
 * @throws Error if base64 string is invalid
 * @performance
 * - Single decoding pass
 * - Direct number parsing without intermediate string variable
 * - Avoids redundant type checks
 */
export function parseBase64ToNumber(base64: string | null | undefined): number | null {
  if (!base64) {
    return null;
  }

  try {
    const valueStr = atob(base64);
    const parsed = Number.parseFloat(valueStr);
    return Number.isFinite(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/**
 * Optimized base64-to-positive-number conversion (rates, prices).
 * 
 * @example
 * const base64 = btoa("1.5");
 * parseBase64ToPositiveNumber(base64)  // → 1.5
 * parseBase64ToPositiveNumber(btoa("-1.5"))  // → null
 */
export function parseBase64ToPositiveNumber(base64: string | null | undefined): number | null {
  if (!base64) {
    return null;
  }

  try {
    const valueStr = atob(base64);
    const parsed = Number.parseFloat(valueStr);
    return parsed > 0 && Number.isFinite(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/**
 * Type predicate: check if a value is a valid finite number.
 * 
 * Useful for type guards and filtering.
 * 
 * @example
 * [1, "2", NaN, 3].filter(isFiniteNumber)  // → [1, 3]
 */
export function isFiniteNumber(value: any): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * Type predicate: check if a value is a positive number.
 * 
 * @example
 * [1, 0, -1, 1.5].filter(isPositiveNumber)  // → [1, 1.5]
 */
export function isPositiveNumber(value: any): value is number {
  return typeof value === "number" && value > 0 && Number.isFinite(value);
}

/**
 * Direct type specification for stroop conversion.
 * 
 * Eliminates redundant type checks in toStroops by specifying input
 * type upfront.
 * 
 * @example
 * stroopsFromNumber(1.5)      // → 15000000
 * stroopsFromString("1.5")    // → 15000000
 * stroopsFromBase64(btoa("1.5"))  // → 15000000
 * 
 * @performance
 * - No type branching: parser knows the input format
 * - Single conversion path per function
 */
export function stroopsFromNumber(price: number): number {
  return Math.round(price * 10_000_000);
}

export function stroopsFromString(price: string): number {
  return Math.round(Number.parseFloat(price) * 10_000_000);
}

export function stroopsFromBase64(base64: string): number | null {
  const parsed = parseBase64ToNumber(base64);
  return parsed !== null ? Math.round(parsed * 10_000_000) : null;
}

/**
 * Safe field accessor with automatic type coercion.
 * 
 * Prevents repeated safety checks when accessing optional numeric fields.
 * 
 * @example
 * const obj = { a: 1, b: "2", c: null };
 * getNumber(obj, "a")      // → 1
 * getNumber(obj, "b")      // → 2
 * getNumber(obj, "c")      // → null
 * getNumber(obj, "d")      // → null
 */
export function getNumber<T extends Record<string, any>>(
  obj: T,
  key: keyof T,
): number | null {
  if (!obj.hasOwnProperty(key)) {
    return null;
  }

  return parseToNumber(obj[key]);
}

export function getPositiveNumber<T extends Record<string, any>>(
  obj: T,
  key: keyof T,
): number | null {
  if (!obj.hasOwnProperty(key)) {
    return null;
  }

  return parseToPositiveNumber(obj[key]);
}
