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
import { ServicesView } from "../src/services";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const now = new Date().toISOString();
it("opens service details and paginates logs as text, without mutation controls", async () => {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      let data;
      if (url.includes("/logs?"))
        data = {
          unit: "ssh.service",
          collected_at: now,
          scanned: 1,
          next_cursor: url.includes("cursor=") ? null : "s=abc;i=1",
          items: [
            {
              message: url.includes("cursor=")
                ? "older message"
                : "<img src=x onerror=alert(1)>",
              priority: "3",
              timestamp_us: "1000000",
            },
          ],
        };
      else if (url.includes("services?"))
        data = {
          items: [
            {
              unit: "ssh.service",
              description: "SSH server",
              active: "active",
              sub: "running",
              load: "loaded",
            },
          ],
          total: 1,
          collected_at: now,
        };
      else
        data = {
          unit: "ssh.service",
          collected_at: now,
          properties: { Id: "ssh.service", ActiveState: "active" },
        };
      return { ok: true, json: async () => data };
    }),
  );
  render(<ServicesView token="test" refresh={0} />);
  fireEvent.click(await screen.findByRole("button", { name: "ssh.service" }));
  expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeTruthy();
  expect(document.querySelector("img")).toBeNull();
  expect(screen.getByText("ActiveState")).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Entrées plus anciennes" }),
  );
  expect(await screen.findByText("older message")).toBeTruthy();
  expect(calls.some((url) => url.includes("cursor=s%3Dabc%3Bi%3D1"))).toBe(
    true,
  );
  fireEvent.change(screen.getByLabelText("État"), {
    target: { value: "failed" },
  });
  await waitFor(() =>
    expect(calls.some((url) => url.includes("state=failed"))).toBe(true),
  );
  expect(
    screen.queryByRole("button", { name: /arrêter|redémarrer/i }),
  ).toBeNull();
});
it("shows permission errors separately from an empty journal", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: !url.includes("/logs?"),
      json: async () =>
        url.includes("/logs?")
          ? { error: { message: "Droits de lecture insuffisants" } }
          : url.includes("services?")
            ? {
                items: [
                  {
                    unit: "ssh.service",
                    description: "SSH",
                    active: "active",
                    sub: "running",
                    load: "loaded",
                  },
                ],
                total: 1,
                collected_at: now,
              }
            : { unit: "ssh.service", collected_at: now, properties: {} },
    })),
  );
  render(<ServicesView token="test" refresh={0} />);
  fireEvent.click(await screen.findByRole("button", { name: "ssh.service" }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Droits de lecture insuffisants",
  );
  expect(screen.queryByText(/Aucune entrée visible/)).toBeNull();
});
