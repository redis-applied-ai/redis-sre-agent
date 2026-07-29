import { renderHook } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./useInfraAuthzDisabled", () => ({
  useInfraAuthzDisabled: vi.fn(),
}));

import { useInfraAuthzDisabled } from "./useInfraAuthzDisabled";
import { useApp } from "./useApp";

const wrapper = ({ children }: { children: ReactNode }) => (
  <MemoryRouter>{children}</MemoryRouter>
);

describe("useApp navigation gating on infrastructure authorization", () => {
  beforeEach(() => vi.clearAllMocks());

  it("hides the Schedules nav item when infra authz is enabled", () => {
    (useInfraAuthzDisabled as unknown as ReturnType<typeof vi.fn>).mockReturnValue(true);
    const { result } = renderHook(() => useApp(), { wrapper });
    const hrefs = result.current.navigationItems.map((i) => i.href);
    expect(hrefs).not.toContain("/schedules");
    expect(hrefs).toContain("/settings"); // other items unaffected
  });

  it("shows the Schedules nav item when infra authz is disabled", () => {
    (useInfraAuthzDisabled as unknown as ReturnType<typeof vi.fn>).mockReturnValue(false);
    const { result } = renderHook(() => useApp(), { wrapper });
    const hrefs = result.current.navigationItems.map((i) => i.href);
    expect(hrefs).toContain("/schedules");
  });
});
