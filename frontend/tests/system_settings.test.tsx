// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { SystemSettingsView } from "../src/system-settings";
import { setLanguage } from "../src/i18n";
afterEach(() => {
  cleanup();
  setLanguage("fr");
  vi.unstubAllGlobals();
});
const health = {
  version: "0.1.0",
  release_date: null,
  checked_at: "2026-11-20T12:00:00Z",
  read_only: true,
  storage: { status: "available" },
};
it.each(["fr", "en"] as const)(
  "shows truthful release metadata and refreshes the last check in %s",
  async (lang) => {
    setLanguage(lang);
    let count = 0;
    const fetcher = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        ...health,
        checked_at: count++ ? "2026-11-20T13:00:00Z" : health.checked_at,
      }),
    }));
    vi.stubGlobal("fetch", fetcher);
    render(<SystemSettingsView token="session" />);
    await screen.findByText(
      lang === "fr" ? "Non publiée (prototype)" : "Unreleased (prototype)",
    );
    expect(document.querySelector("time")?.dateTime).toBe(health.checked_at);
    fireEvent.click(
      screen.getByRole("button", {
        name: lang === "fr" ? "Vérifier maintenant" : "Check now",
      }),
    );
    await waitFor(() =>
      expect(document.querySelector("time")?.dateTime).toBe(
        "2026-11-20T13:00:00Z",
      ),
    );
    expect(fetcher.mock.calls.length).toBe(2);
  },
);
it("preserves the previous check date and reports a failed refresh", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce({ ok: true, json: async () => health })
    .mockRejectedValueOnce(new Error("offline"));
  vi.stubGlobal("fetch", fetcher);
  render(<SystemSettingsView token="session" />);
  await screen.findByText("0.1.0");
  fireEvent.click(screen.getByText("Vérifier maintenant"));
  expect((await screen.findByRole("alert")).textContent).toContain("offline");
  expect(document.querySelector("time")?.dateTime).toBe(health.checked_at);
});
it("does not invent dates from invalid metadata", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ ...health, checked_at: "invalid" }),
    })),
  );
  render(<SystemSettingsView token="session" />);
  await screen.findByRole("alert");
  expect(document.querySelector("time")).toBeNull();
});
