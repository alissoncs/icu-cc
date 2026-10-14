import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

beforeEach(() => {
  vi.stubEnv("VITE_MOCK", "1");
});
afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});
