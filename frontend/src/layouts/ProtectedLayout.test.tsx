import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ProtectedLayout } from "@/layouts/ProtectedLayout";
import { useAuthStore } from "@/stores/authStore";

function DashboardStub() {
  return <div>Dashboard content</div>;
}

describe("ProtectedLayout", () => {
  beforeEach(() => {
    useAuthStore.getState().logout();
  });

  it("redirects to login when unauthenticated", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/login" element={<div>Login page</div>} />
          <Route element={<ProtectedLayout />}>
            <Route index element={<DashboardStub />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("Login page")).toBeInTheDocument();
  });

  it("renders child route when authenticated", () => {
    useAuthStore.getState().setSession("tok", "ref", {
      id: "1",
      username: "admin",
      email: "a",
      is_active: true,
      is_locked: false,
      created_at: new Date().toISOString(),
      role: "admin",
    });
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<ProtectedLayout />}>
            <Route index element={<DashboardStub />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("Dashboard content")).toBeInTheDocument();
  });
});
