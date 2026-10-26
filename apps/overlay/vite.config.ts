import { readFileSync } from "node:fs";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// The sample stream, served at fixtures/sample_stream.jsonl in dev and copied into dist at build.
const FIXTURE = new URL("../../tests/fixtures/stream/sample_stream.jsonl", import.meta.url);
const FIXTURE_PATH = "fixtures/sample_stream.jsonl";

function streamFixture(): Plugin {
  return {
    name: "whyline-stream-fixture",
    configureServer(server) {
      server.middlewares.use(`/${FIXTURE_PATH}`, (_req, res) => {
        res.setHeader("Content-Type", "application/x-ndjson");
        res.end(readFileSync(FIXTURE));
      });
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: FIXTURE_PATH, source: readFileSync(FIXTURE) });
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [react(), streamFixture()],
});
