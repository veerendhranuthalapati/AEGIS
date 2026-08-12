import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "@/stores/authStore";

describe("authStore", () => {
  beforeEach(() => {
    useAuthStore.getState().logout();
  });

  it("starts unauthenticated", () => {
    expect(useAuthStore.getState().isAuthenticated()).toBe(false);
  });

  it("stores session tokens", () => {
    useAuthStore.getState().setSession("access", "refresh", {
      id: "1",
      username: "admin",
      email: "a@b.c",
      is_active: true,
      is_locked: false,
      created_at: new Date().toISOString(),
      role: "admin",
    });
    expect(useAuthStore.getState().accessToken).toBe("access");
    expect(useAuthStore.getState().user?.username).toBe("admin");
  });

  it("clears session on logout", () => {
    useAuthStore.getState().setSession("a", "r", {
      id: "1",
      username: "u",
      email: "e",
      is_active: true,
      is_locked: false,
      created_at: new Date().toISOString(),
    });
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().isAuthenticated()).toBe(false);
  });
});
