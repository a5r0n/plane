// The one web app manifest link; credentialed so a login proxy in front of the app passes it with the session cookie.
export const MANIFEST_LINK = {
  rel: "manifest",
  href: "/manifest.json",
  crossOrigin: "use-credentials",
} as const;
