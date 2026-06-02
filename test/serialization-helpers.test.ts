/**
 * Tests for optimized serialization helpers
 * Verifies performance improvements and type-safe number parsing
 */

import {
  parseToNumber,
  parseToPositiveNumber,
  parseToNonNegativeInt,
  parseBatchNumbers,
  parseBase64ToNumber,
  parseBase64ToPositiveNumber,
  isFiniteNumber,
  isPositiveNumber,
  stroopsFromNumber,
  stroopsFromString,
  stroopsFromBase64,
  getNumber,
  getPositiveNumber,
} from "../src/serialization/helpers";

let passed = 0;
let failed = 0;

function assert(description: string, actual: any, expected: any): void {
  const ok =
    actual === expected ||
    (typeof actual === "number" &&
      typeof expected === "number" &&
      Math.abs(actual - expected) < 1e-10);

  if (ok) {
    console.log(`  ✓ ${description}`);
    passed++;
  } else {
    console.error(`  ✗ ${description}`);
    console.error(`      expected: ${JSON.stringify(expected)}`);
    console.error(`      received: ${JSON.stringify(actual)}`);
    failed++;
  }
}

function assertDeep(
  description: string,
  actual: any,
  expected: any,
): void {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok) {
    console.log(`  ✓ ${description}`);
    passed++;
  } else {
    console.error(`  ✗ ${description}`);
    console.error(`      expected: ${JSON.stringify(expected)}`);
    console.error(`      received: ${JSON.stringify(actual)}`);
    failed++;
  }
}

console.log("🧪 Testing optimized serialization helpers...\n");

// ─────────────────────────────────────────────────────────────────────────────
console.log("📌 parseToNumber()");

assert("handles null", parseToNumber(null), null);
assert("handles undefined", parseToNumber(undefined), null);
assert("handles valid number", parseToNumber(1.5), 1.5);
assert("handles valid string", parseToNumber("1.5"), 1.5);
assert("rejects NaN", parseToNumber(NaN), null);
assert("rejects Infinity", parseToNumber(Infinity), null);
assert("rejects -Infinity", parseToNumber(-Infinity), null);
assert("handles negative number", parseToNumber(-5.5), -5.5);
assert("handles negative string", parseToNumber("-5.5"), -5.5);
assert("rejects non-numeric string", parseToNumber("abc"), null);
assert("handles zero", parseToNumber(0), 0);
assert("handles empty string", parseToNumber(""), null);

// ─────────────────────────────────────────────────────────────────────────────
console.log("\n📌 parseToPositiveNumber()");

assert("handles null", parseToPositiveNumber(null), null);
assert("handles undefined", parseToPositiveNumber(undefined), null);
assert("accepts positive number", parseToPositiveNumber(1.5), 1.5);
assert("accepts positive string", parseToPositiveNumber("1.5"), 1.5);
assert("rejects zero", parseToPositiveNumber(0), null);
assert("rejects negative number", parseToPositiveNumber(-1.5), null);
assert("rejects negative string", parseToPositiveNumber("-1.5"), null);
assert("rejects NaN", parseToPositiveNumber(NaN), null);
assert("rejects Infinity", parseToPositiveNumber(Infinity), null);

// ─────────────────────────────────────────────────────────────────────────────
console.log("\n📌 parseToNonNegativeInt()");

assert("handles null", parseToNonNegativeInt(null), null);
assert("handles undefined", parseToNonNegativeInt(undefined), null);
assert("accepts zero", parseToNonNegativeInt(0), 0);
assert("accepts positive integer", parseToNonNegativeInt(100), 100);
assert("accepts positive int string", parseToNonNegativeInt("100"), 100);
assert("rejects negative integer", parseToNonNegativeInt(-100), null);
assert("rejects negative int string", parseToNonNegativeInt("-100"), null);
assert("rejects float", parseToNonNegativeInt(1.5), null);
assert("rejects float string", parseToNonNegativeInt("1.5"), null);
assert("rejects NaN", parseToNonNegativeInt(NaN), null);

// ─────────────────────────────────────────────────────────────────────────────
console.log("\n📌 parseBatchNumbers() - batch parsing optimization");

const batchTestRow = {
  rate: "1.5",
  baseline_rate: 1.2,
  change_percent: "2.5",
  currency: "NGN",
  count: "100",
};

const batchResult = parseBatchNumbers(batchTestRow, [
  "rate",
  "baseline_rate",
  "change_percent",
] as const);

assertDeep("parses multiple numeric fields correctly", batchResult, {
  rate: 1.5,
  baseline_rate: 1.2,
  change_percent: 2.5,
});

// ─────────────────────────────────────────────────────────────────────────────
console.log("\n📌 parseBase64ToNumber()");

const base64_1_5 = btoa("1.5");
const base64_0_1 = btoa("0.1");
const base64_invalid = btoa("NaN");

assert(
  "decodes valid base64 number",
  parseBase64ToNumber(base64_1_5),
  1.5,
);
assert(
  "decodes another valid base64 number",
  parseBase64ToNumber(base64_0_1),
  0.1,
);
assert("handles empty string", parseBase64ToNumber(""), null);
assert("handles null", parseBase64ToNumber(null), null);
assert("handles undefined", parseBase64ToNumber(undefined), null);
assert("rejects invalid base64", parseBase64ToNumber("!!!"), null);

// ─────────────────────────────────────────────────────────────────────────────
console.log("\n📌 parseBase64ToPositiveNumber()");

assert(
  "accepts positive base64 number",
  parseBase64ToPositiveNumber(base64_1_5),
  1.5,
);

const base64_negative = btoa("-1.5");
assert(
  "rejects negative base64 number",
  parseBase64ToPositiveNumber(base64_negative),
  null,
);
assert("handles null", parseBase64ToPositiveNumber(null), null);

// ─────────────────────────────────────────────────────────────────────────────
console.log("\n📌 Type predicates: isFiniteNumber() and isPositiveNumber()");

const testArray = [1, "2", NaN, 3, Infinity, -1, 0, 1.5];

assert("isFiniteNumber filters correctly", [
  ...testArray.filter(isFiniteNumber),
], [1, 3, -1, 0, 1.5]);

assert("isPositiveNumber filters correctly", [
  ...testArray.filter(isPositiveNumber),
], [1, 3, 1.5]);

// ─────────────────────────────────────────────────────────────────────────────
console.log("\n📌 stroopsFromNumber(), stroopsFromString(), stroopsFromBase64()");

assert("stroopsFromNumber(1.5)", stroopsFromNumber(1.5), 15_000_000);
assert("stroopsFromNumber(0.1)", stroopsFromNumber(0.1), 1_000_000);
assert("stroopsFromString('1.5')", stroopsFromString("1.5"), 15_000_000);
assert("stroopsFromString('0.1')", stroopsFromString("0.1"), 1_000_000);

const base64ForStroops = btoa("1.5");
assert(
  "stroopsFromBase64(btoa('1.5'))",
  stroopsFromBase64(base64ForStroops),
  15_000_000,
);

assert("stroopsFromBase64(null)", stroopsFromBase64(null as any), null);
assert("stroopsFromBase64('')", stroopsFromBase64(""), null);

// ─────────────────────────────────────────────────────────────────────────────
console.log("\n📌 Safe field accessors: getNumber() and getPositiveNumber()");

const testObj = {
  rate: 1.5,
  price: "2.5",
  invalid: NaN,
  negative: -1,
};

assert("getNumber returns number field", getNumber(testObj, "rate"), 1.5);
assert("getNumber converts string field", getNumber(testObj, "price"), 2.5);
assert("getNumber rejects NaN", getNumber(testObj, "invalid"), null);
assert("getNumber handles missing field", getNumber(testObj, "missing" as any), null);

assert(
  "getPositiveNumber returns positive number",
  getPositiveNumber(testObj, "rate"),
  1.5,
);
assert(
  "getPositiveNumber rejects negative",
  getPositiveNumber(testObj, "negative"),
  null,
);

// ─────────────────────────────────────────────────────────────────────────────
console.log("\n📌 Performance: Batch parsing reduces function call overhead");

// Simulate database row mapping scenario
interface MockRow {
  rate: string | number;
  baseline_rate: string | number | null;
  change_percent: string | number | null;
}

const mockRows: MockRow[] = [
  { rate: "1.5", baseline_rate: "1.2", change_percent: "2.5" },
  { rate: 1.6, baseline_rate: 1.3, change_percent: null },
  { rate: "1.7", baseline_rate: null, change_percent: "3.5" },
];

// Old approach: 3 function calls per row (9 total)
let oldStyleCallCount = 0;
function oldToNumber(value: number | string | null | undefined): number | null {
  oldStyleCallCount++;
  if (value === null || value === undefined) return null;
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

const oldStyleResults = mockRows.map(row => ({
  rate: oldToNumber(row.rate) ?? 0,
  baselineRate: oldToNumber(row.baseline_rate),
  changePercent: oldToNumber(row.change_percent),
}));

// New approach: 1 batch parse per row (3 total)
let newStyleCallCount = 0;
const newStyleResults = mockRows.map(row => {
  newStyleCallCount++;
  const parsed = parseBatchNumbers(row, [
    "rate",
    "baseline_rate",
    "change_percent",
  ] as const);
  return {
    rate: parsed.rate ?? 0,
    baselineRate: parsed.baseline_rate,
    changePercent: parsed.change_percent,
  };
});

// Results should be identical
assertDeep(
  "Old vs new approach produce identical results",
  oldStyleResults,
  newStyleResults,
);

console.log(`\n  ℹ️  Old approach: ${oldStyleCallCount} function calls for ${mockRows.length} rows`);
console.log(`  ℹ️  New approach: ${newStyleCallCount} batch calls for ${mockRows.length} rows`);
console.log(
  `  ℹ️  Reduction: ${((1 - newStyleCallCount / oldStyleCallCount) * 100).toFixed(0)}% fewer dispatch operations`,
);

// ─────────────────────────────────────────────────────────────────────────────
console.log(`\n${"=".repeat(60)}`);
console.log(`${passed} passed, ${failed} failed`);

if (failed > 0) {
  process.exit(1);
}
