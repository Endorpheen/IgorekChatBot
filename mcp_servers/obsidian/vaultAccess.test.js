import { before, after, test } from "node:test";
import assert from "node:assert/strict";
import fs from "fs/promises";
import os from "os";
import path from "path";
import { createVaultReader, VaultAccessError } from "./vaultAccess.js";

const state = {};

before(async () => {
  state.tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "vault-access-"));
  state.vaultDir = path.join(state.tempRoot, "vault");
  await fs.mkdir(state.vaultDir, { recursive: true });

  const notesDir = path.join(state.vaultDir, "notes");
  await fs.mkdir(notesDir, { recursive: true });

  state.notePath = path.join(notesDir, "example.md");
  await fs.writeFile(state.notePath, "# Example note\n");

  state.reader = createVaultReader(state.vaultDir);
});

after(async () => {
  if (state.tempRoot) {
    await fs.rm(state.tempRoot, { recursive: true, force: true });
  }
});

test("reads files located inside the vault", async () => {
  const content = await state.reader.readFile("notes/example.md");
  assert.equal(content, "# Example note\n");
});

test("rejects attempts to traverse outside the vault", async () => {
  await assert.rejects(
    state.reader.readFile("../../etc/passwd"),
    (error) => {
      assert(error instanceof VaultAccessError);
      assert.equal(error.reason, "outside_of_base");
      return true;
    },
  );
});
