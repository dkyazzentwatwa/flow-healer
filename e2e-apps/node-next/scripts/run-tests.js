import { spawnSync } from "node:child_process";

const result = spawnSync(process.execPath, ["--test"], {
  stdio: "inherit",
});

if (result.error) {
  throw result.error;
}

process.exit(result.status ?? 1);
