// Baut ../assets/editor/tiptap.bundle.js -- eine einzige IIFE-Datei, die der
// QWebEngineView ohne Modul-Lader und ohne Netz laden kann.
//
//   node build.mjs           einmal bauen
//   node build.mjs --watch   bei jeder Aenderung neu bauen

import * as esbuild from "esbuild";

const options = {
  entryPoints: ["src/main.js"],
  bundle: true,
  format: "iife",
  target: ["chrome120"], // QtWebEngine 6.11 bringt Chromium 13x mit
  outfile: "../assets/editor/tiptap.bundle.js",
  minify: true,
  legalComments: "eof", // MIT-Hinweise von Tiptap/ProseMirror bleiben drin
  logLevel: "info",
};

if (process.argv.includes("--watch")) {
  const ctx = await esbuild.context(options);
  await ctx.watch();
} else {
  await esbuild.build(options);
}
