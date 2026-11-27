import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MANIFEST_LINK } from "../pwa";

const web = resolve(__dirname, "../../../..");
const manifest = JSON.parse(readFileSync(resolve(web, "public/manifest.json"), "utf8"));

describe("web app manifest", () => {
  it("root.tsx links exactly one manifest, the credentialed one", () => {
    const root = readFileSync(resolve(web, "app/root.tsx"), "utf8");
    expect(root.match(/rel: "manifest"/g)).toBeNull();
    expect(root.match(/MANIFEST_LINK,/g)).toHaveLength(1);
  });

  it("renders the link with crossorigin=use-credentials", () => {
    const html = renderToStaticMarkup(<link {...MANIFEST_LINK} />);
    expect(html).toBe('<link rel="manifest" href="/manifest.json" crossorigin="use-credentials"/>');
  });

  it("is installable: name, standalone, start_url", () => {
    expect(manifest.name).toBe("Plane");
    expect(manifest.short_name).toBe("Plane");
    expect(manifest.display).toBe("standalone");
    expect(manifest.start_url).toBe("/");
  });

  it("has 192 and 512 icons and exactly one maskable, all on disk", () => {
    const icons: { src: string; sizes: string; purpose?: string }[] = manifest.icons;
    const any = icons.filter((i) => (i.purpose ?? "any").split(" ").includes("any"));
    expect(any.map((i) => i.sizes)).toEqual(["192x192", "512x512"]);
    expect(icons.filter((i) => i.purpose?.split(" ").includes("maskable"))).toHaveLength(1);
    for (const icon of icons) expect(existsSync(resolve(web, "public", icon.src.slice(1)))).toBe(true);
  });
});
