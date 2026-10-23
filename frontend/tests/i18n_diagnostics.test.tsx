// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  act,
  waitFor,
} from "@testing-library/react";
import { App } from "../src/main";
import { ServicesView } from "../src/services";
import { SettingsView } from "../src/preferences";
import { DiagnosticView } from "../src/diagnostics";
import { setLanguage, t, formatNumber } from "../src/i18n";
import { bytes } from "../src/format";
import fr from "../../locales/fr.json";
import en from "../../locales/en.json";
afterEach(() => {
  cleanup();
  setLanguage("fr");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it("keeps matching catalogs, placeholders, binary units and locale numbers", () => {
  expect(Object.keys(fr).sort()).toEqual(Object.keys(en).sort());
  for (const [key, value] of Object.entries(en)) {
    expect(value.trim()).toBeTruthy();
    expect(key.match(/\{\d+\}/g) || []).toEqual(value.match(/\{\d+\}/g) || []);
  }
  setLanguage("en");
  expect(t("Vue d’ensemble")).toBe("Overview");
  expect(bytes(1073741824)).toBe("1.0 GiB");
  expect(formatNumber(12.5)).toBe("12.5");
  expect(t("Seuil 90 % franchi (95.0 %)")).toBe(
    "Threshold 90% exceeded (95.0%)",
  );
  setLanguage("fr");
  expect(formatNumber(12.5)).toBe("12,5");
  expect(t("unrecognized external log")).toBe("unrecognized external log");
});
it("switches login and every navigation label without changing route identifiers", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: false,
      json: async () => ({ error: { message: "Jeton local requis" } }),
    })),
  );
  render(<App />);
  fireEvent.change(screen.getByLabelText("Langue de la session"), {
    target: { value: "en" },
  });
  expect(
    screen.getByRole("heading", { name: "Your machine, at a glance." }),
  ).toBeTruthy();
  expect(document.documentElement.lang).toBe("en");
  fireEvent.change(screen.getByLabelText("Token shown by the local launcher"), {
    target: { value: "test" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Open cockpit →" }));
  expect(
    await screen.findByRole("button", { name: "▦ Overview" }),
  ).toBeTruthy();
  for (const name of [
    "◉ System",
    "≋ Processes",
    "⚙ Services",
    "✧ Local AI",
    "▣ Containers",
    "⚑ Alerts",
    "☷ Settings",
    "⇩ Diagnostics",
  ])
    expect(screen.getByRole("button", { name })).toBeTruthy();
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Local token required",
  );
});
it("renders services and error messages in English while retaining external names", async () => {
  setLanguage("en");
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({
        items: [
          {
            unit: "ssh.service",
            description: "Original description",
            active: "active",
            sub: "running",
          },
        ],
        total: 1,
        collected_at: new Date().toISOString(),
      }),
    })),
  );
  render(<ServicesView token="test" refresh={0} />);
  expect(
    await screen.findByRole("heading", { name: "Loaded system services" }),
  ).toBeTruthy();
  expect(
    await screen.findByRole("button", { name: "ssh.service" }),
  ).toBeTruthy();
  expect(screen.getByText("Original description")).toBeTruthy();
  act(() => setLanguage("fr"));
  expect(
    screen.getByRole("heading", { name: "Services système chargés" }),
  ).toBeTruthy();
});
it("submits persistent language preference rather than modifying metric/rule identifiers", async () => {
  let submitted: any;
  const onSaved = vi.fn();
  const settings = {
    language: "fr",
    theme: "system",
    refresh_seconds: 3,
    retention_days: 7,
    rules: [],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, options: RequestInit) => ({
      ok: true,
      json: async () => {
        if (options.method === "PUT") {
          submitted = JSON.parse(options.body as string);
          return { settings: submitted, operation_id: "op" };
        }
        return { settings, csrf_token: "csrf" };
      },
    })),
  );
  render(<SettingsView token="test" onSaved={onSaved} />);
  fireEvent.change(await screen.findByLabelText("Langue"), {
    target: { value: "en" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Enregistrer les réglages" }),
  );
  await waitFor(() => expect(onSaved).toHaveBeenCalled());
  expect(submitted.language).toBe("en");
});
it("requires confirmation before exporting and downloads a bounded JSON blob", async () => {
  setLanguage("en");
  const calls: { url: string; options: RequestInit }[] = [];
  const create = vi.fn(() => "blob:local-diagnostic");
  const revoke = vi.fn();
  vi.stubGlobal(
    "URL",
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }),
  );
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: RequestInit) => {
      calls.push({ url, options });
      return url.endsWith("/options")
        ? { ok: true, json: async () => ({ csrf_token: "csrf" }) }
        : {
            ok: true,
            headers: { get: () => "recorded" },
            blob: async () =>
              new Blob(['{"schema_version":1}'], { type: "application/json" }),
          };
    }),
  );
  render(<DiagnosticView token="test" />);
  const button = screen.getByRole("button", {
    name: "Download JSON diagnostic report",
  });
  expect((button as HTMLButtonElement).disabled).toBe(true);
  await waitFor(() => expect(calls.length).toBe(1));
  fireEvent.click(screen.getByRole("checkbox"));
  await waitFor(() =>
    expect((button as HTMLButtonElement).disabled).toBe(false),
  );
  fireEvent.click(button);
  expect((await screen.findByRole("status")).textContent).toContain(
    "downloaded and export audited",
  );
  const post = calls.find((c) => c.options.method === "POST")!;
  expect(JSON.parse(post.options.body as string)).toEqual({ confirmed: true });
  expect(post.options.headers).toMatchObject({
    "X-LocalCockpit-CSRF": "csrf",
    "Accept-Language": "en",
  });
  expect(click).toHaveBeenCalledOnce();
  expect(revoke).toHaveBeenCalledWith("blob:local-diagnostic");
});
