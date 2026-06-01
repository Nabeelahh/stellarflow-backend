import { decode, encode } from "@msgpack/msgpack";

export function pack<T = unknown>(data: T): Uint8Array {
  return encode(data);
}

export function unpack<T = unknown>(payload: Uint8Array | Buffer | string): T {
  if (typeof payload === "string") {
    return decode(Buffer.from(payload, "utf-8")) as T;
  }

  return decode(payload) as T;
}
