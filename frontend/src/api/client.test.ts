import { describe, it, expect } from "vitest";
import axios from "axios";
import { getErrorMessage } from "@/api/client";

describe("getErrorMessage", () => {
  it("extracts string detail from axios errors", () => {
    const err = new axios.AxiosError("fail", "ERR", undefined, undefined, {
      status: 401,
      data: { detail: "Invalid credentials" },
      statusText: "Unauthorized",
      headers: {},
      config: {} as never,
    });
    expect(getErrorMessage(err)).toBe("Invalid credentials");
  });

  it("falls back for unknown errors", () => {
    expect(getErrorMessage(new Error("boom"))).toBe("boom");
  });
});
