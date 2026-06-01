import { pack, unpack } from "../src/serialization/binaryPack";

describe("binaryPack", () => {
  it("should encode and decode an object payload", () => {
    const payload = {
      symbol: "XLMNGN",
      price: 122.56,
      timestamp: Date.now(),
      valid: true,
      providers: ["providerA", "providerB"],
    };

    const encoded = pack(payload);
    const decoded = unpack<typeof payload>(encoded);

    expect(decoded).toEqual(payload);
  });

  it("should encode and decode primitive values", () => {
    expect(unpack<number>(pack(42))).toBe(42);
    expect(unpack<string>(pack("hello"))).toBe("hello");
    expect(unpack<boolean>(pack(false))).toBe(false);
  });
});
