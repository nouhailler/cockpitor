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
import { AlertsView, SettingsView, type Preferences } from "../src/preferences";
const prefs: Preferences = {
  language: "fr",
  theme: "system",
  refresh_seconds: 3,
  retention_days: 7,
  rules: [
    {
      id: "cpu",
      metric: "cpu_percent",
      threshold: 90,
      duration_seconds: 30,
      enabled: true,
      severity: "warning",
      target: null,
      engine: null,
    },
  ],
};
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("saves validated application settings with auth, JSON and CSRF headers", async () => {
  const calls: { url: string; options: RequestInit }[] = [];
  const onSaved = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: RequestInit) => {
      calls.push({ url, options });
      return {
        ok: true,
        json: async () =>
          options.method === "PUT"
            ? {
                operation_id: "operation-local",
                settings: { ...prefs, theme: "light" },
              }
            : { settings: prefs, csrf_token: "csrf-private" },
      };
    }),
  );
  render(<SettingsView token="auth-private" onSaved={onSaved} />);
  fireEvent.change(await screen.findByLabelText("Thème"), {
    target: { value: "light" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Enregistrer les réglages" }),
  );
  expect((await screen.findByRole("status")).textContent).toContain(
    "Réglages enregistrés",
  );
  const save = calls.find((c) => c.options.method === "PUT")!;
  expect(save.url).toBe("/api/v1/settings");
  expect(save.options.headers).toEqual({
    Authorization: "Bearer auth-private",
    "Accept-Language": "fr",
    "Content-Type": "application/json",
    "X-LocalCockpit-CSRF": "csrf-private",
  });
  expect(JSON.parse(save.options.body as string).theme).toBe("light");
  expect(onSaved).toHaveBeenCalledWith({ ...prefs, theme: "light" });
  expect(JSON.stringify(save.options.body)).not.toContain("csrf-private");
});
it("reports failed persistence without claiming settings were saved", async () => {
  const onSaved = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, options: RequestInit) => ({
      ok: options.method !== "PUT",
      json: async () =>
        options.method === "PUT"
          ? { error: { message: "Stockage verrouillé" } }
          : { settings: prefs, csrf_token: "csrf" },
    })),
  );
  render(<SettingsView token="test" onSaved={onSaved} />);
  await screen.findByLabelText("Thème");
  fireEvent.click(
    screen.getByRole("button", { name: "Enregistrer les réglages" }),
  );
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Stockage verrouillé",
  );
  expect(onSaved).not.toHaveBeenCalled();
  expect(screen.queryByText(/Réglages enregistrés/)).toBeNull();
});
it("keeps unavailable sources distinct from active and resolved alerts", async () => {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      return {
        ok: true,
        json: async () => ({
          items: [
            {
              id: "one",
              rule_id: "cpu",
              severity: "critical",
              status: "active",
              message: "<img src=x>",
              created_at: new Date().toISOString(),
              resolved_at: null,
            },
          ],
          total: 51,
          evaluated_at: new Date().toISOString(),
          rules: [
            {
              rule_id: "cpu",
              metric: "cpu_percent",
              status: "unavailable",
              active: true,
              value: null,
              message: "Source périmée",
            },
          ],
        }),
      };
    }),
  );
  render(<AlertsView token="test" refresh={0} />);
  expect(await screen.findByText("<img src=x>")).toBeTruthy();
  expect(document.querySelector("img")).toBeNull();
  expect(await screen.findByText(/alerte active conservée/)).toBeTruthy();
  expect(screen.getByText("Indisponible")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Alertes suivantes" }));
  await waitFor(() =>
    expect(calls.some((url) => url.includes("offset=50"))).toBe(true),
  );
  fireEvent.change(screen.getByLabelText("État des alertes"), {
    target: { value: "resolved" },
  });
  await waitFor(() =>
    expect(calls.some((url) => url.includes("status=resolved&offset=0"))).toBe(
      true,
    ),
  );
});
it("allows retry after storage becomes available", async () => {
  let calls = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      calls++;
      return {
        ok: calls > 1,
        json: async () =>
          calls > 1
            ? { settings: prefs, csrf_token: "csrf" }
            : { error: { message: "Stockage indisponible" } },
      };
    }),
  );
  render(<SettingsView token="test" onSaved={() => {}} />);
  await screen.findByRole("alert");
  fireEvent.click(
    screen.getByRole("button", { name: "Réessayer les paramètres" }),
  );
  expect(await screen.findByLabelText("Thème")).toBeTruthy();
});
