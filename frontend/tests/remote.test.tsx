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
import { RemoteView } from "../src/remote";
import { setLanguage } from "../src/i18n";
afterEach(() => {
  cleanup();
  setLanguage("fr");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
const host = {
  id: "debian",
  label: "Debian lab",
  group: "Lab",
  address: "127.0.0.1",
  port: 2222,
  username: "tester",
  host_key_fingerprint: "SHA256:pinned",
  configuration_id: "a".repeat(32),
  allow_sftp: true,
  remote_root: "/",
  last_check: null,
};
it.each(["fr", "en"] as const)(
  "does not connect automatically and requires an explicit confirmed target in %s",
  async (lang) => {
    setLanguage(lang);
    const fetcher = vi.fn(async (url: string, options: any) => ({
      ok: true,
      json: async () =>
        url.endsWith("hosts")
          ? { items: [host], configuration_error: false }
          : {
              checked_at: "2026-11-20T00:00:00Z",
              authenticated: true,
              host_key_verified: true,
              items: [
                {
                  name: "<img src=x onerror=alert(1)>",
                  kind: "file",
                  size: 12,
                },
              ],
            },
    }));
    vi.stubGlobal("fetch", fetcher);
    render(<RemoteView token="session" csrf="csrf" />);
    await screen.findByRole("option", { name: "Debian lab · 127.0.0.1:2222" });
    expect(fetcher.mock.calls.every(([url]) => url.endsWith("hosts"))).toBe(
      true,
    );
    fireEvent.change(
      screen.getByLabelText(lang === "fr" ? "Hôte distant" : "Remote host"),
      { target: { value: "debian" } },
    );
    expect(screen.getByText("SHA256:pinned")).toBeTruthy();
    const button = screen.getByRole("button", {
      name: lang === "fr" ? "Lister la racine SFTP" : "List SFTP root",
    });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(
      screen.getByLabelText(
        lang === "fr"
          ? "Je confirme cette connexion vers l’hôte et la clé affichés"
          : "I confirm connecting to the displayed host and key",
      ),
    );
    fireEvent.click(button);
    await screen.findByText("<img src=x onerror=alert(1)>");
    expect(document.querySelector("img")).toBeNull();
    const sent = fetcher.mock.calls.find(([url]) => url.endsWith("list"));
    expect(JSON.parse(sent![1].body)).toEqual({
      host_id: "debian",
      configuration_id: "a".repeat(32),
      confirmed: true,
    });
    await waitFor(() =>
      expect((button as HTMLButtonElement).disabled).toBe(true),
    );
  },
);
it("keeps hosts empty by default", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ items: [], configuration_error: false }),
    })),
  );
  render(<RemoteView token="session" csrf="csrf" />);
  await screen.findByText(/LOCALCOCKPIT_REMOTE_HOSTS/);
  expect(
    screen.queryByRole("button", { name: "Vérifier la connexion SSH" }),
  ).toBeNull();
});
it("shows host-key refusal without reporting a verified connection", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: url.endsWith("hosts"),
      json: async () =>
        url.endsWith("hosts")
          ? { items: [host], configuration_error: false }
          : {
              error: { message: "Clé d’hôte refusée ; vérifiez-la hors bande" },
            },
    })),
  );
  render(<RemoteView token="session" csrf="csrf" />);
  await screen.findByRole("option", { name: /Debian lab/ });
  fireEvent.change(screen.getByLabelText("Hôte distant"), {
    target: { value: "debian" },
  });
  fireEvent.click(
    screen.getByLabelText(
      "Je confirme cette connexion vers l’hôte et la clé affichés",
    ),
  );
  fireEvent.click(screen.getByText("Vérifier la connexion SSH"));
  await screen.findByRole("alert");
  expect(
    screen.queryByRole("region", { name: "Résultat de connexion" }),
  ).toBeNull();
});
