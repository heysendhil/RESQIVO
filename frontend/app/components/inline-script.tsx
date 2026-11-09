/** An inline script that runs while the server-rendered HTML is parsed. On the
 * client it is rendered as text/plain, so React does not warn about rendering
 * a <script> tag and the script is never run a second time
 * (node_modules/next/dist/docs/01-app/02-guides/preventing-flash-before-hydration.md). */
export function InlineScript({ html }: { html: string }) {
  return (
    <script
      type={typeof window === "undefined" ? "text/javascript" : "text/plain"}
      suppressHydrationWarning
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
