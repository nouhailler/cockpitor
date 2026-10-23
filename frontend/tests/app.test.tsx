// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { App, api, bytes } from "../src/main";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("formats unavailable metrics and binary units", () => {
  expect(bytes(null)).toBe("Indisponible");
  expect(bytes(1073741824)).toBe("1,0 Gio");
});
it("requires an explicit token and does not put it in URL", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => ({}) });
  vi.stubGlobal("fetch", fetcher);
  await api("health", "private-token");
  expect(fetcher.mock.calls[0][0]).toBe("/api/v1/health");
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe(
    "Bearer private-token",
  );
});
it("renders API errors as text without interpreting HTML", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({
        error: { message: "<img src=x onerror=alert(1)>" },
      }),
    }),
  );
  render(<App />);
  fireEvent.change(
    screen.getByLabelText("Jeton affiché par le lanceur local"),
    { target: { value: "test" } },
  );
  fireEvent.click(screen.getByText("Ouvrir le cockpit →"));
  expect((await screen.findByRole("alert")).textContent).toContain("<img");
  expect(document.querySelector("img")).toBeNull();
  expect(screen.queryByText("Redémarrer")).toBeNull();
});

it("connects AI and container views to their read-only endpoints", async () => {
  const fetcher = vi.fn(async (url: string) => ({
    ok: true,
    json: async () => {
      if (url.endsWith("auth/options")) return { csrf_token: "csrf" };
      if (url.endsWith("auth/sessions"))
        return { token: "session", csrf_token: "csrf" };
      if (url.endsWith("ai/status"))
        return {
          collected_at: new Date().toISOString(),
          status: "ok",
          ollama: {
            status: "available",
            collected_at: new Date().toISOString(),
            models: [{ name: "model-local", size: 1024 }],
          },
          openwebui: {
            status: "disabled",
            collected_at: new Date().toISOString(),
            message: "URL non configurée",
          },
        };
      if (url.endsWith("containers"))
        return {
          collected_at: new Date().toISOString(),
          status: "ok",
          engines: [
            {
              name: "docker",
              status: "available",
              version: "test",
              containers: [
                {
                  id: "123",
                  name: "container-local",
                  image: "local-image",
                  state: "running",
                  status: "Up",
                  ports: [],
                },
              ],
            },
          ],
        };
      if (url.endsWith("system/history")) return [];
      return {
        collected_at: new Date().toISOString(),
        hostname: "test",
        os: "Linux",
        uptime_seconds: 120,
        cpu_percent: 12,
        cpu_cores: [12],
        load: [0, 0, 0],
        memory: { total: 1024, used: 512, available: 512, percent: 50 },
        swap: { total: 0, used: 0, percent: 0 },
        network: { received_bps: 0, sent_bps: 0 },
        disks: [],
        temperatures: [],
      };
    },
  }));
  vi.stubGlobal("fetch", fetcher);
  render(<App />);
  fireEvent.change(
    screen.getByLabelText("Jeton affiché par le lanceur local"),
    { target: { value: "test" } },
  );
  fireEvent.click(screen.getByText("Ouvrir le cockpit →"));
  fireEvent.click(await screen.findByRole("button", { name: "✧ IA locale" }));
  expect(await screen.findByText("model-local")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "▣ Conteneurs" }));
  expect(await screen.findByText("container-local")).toBeTruthy();
  expect(fetcher.mock.calls.some(([url]) => url.endsWith("/containers"))).toBe(
    true,
  );
});
