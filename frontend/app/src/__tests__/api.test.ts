/**
 * Низькорівневі тести api.ts — на відміну від App.test.tsx (мокає весь
 * модуль "../api"), тут використовується РЕАЛЬНИЙ request()/setActiveShopId(),
 * а мокається лише globalThis.fetch — інакше заголовок X-Shop-Id (Стадія 3б)
 * ніде спостерігати.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { getProducts, setActiveShopId } from "../api";

function mockFetchOnce(body: unknown = []) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("api request X-Shop-Id header", () => {
  afterEach(() => {
    setActiveShopId(null);
    vi.restoreAllMocks();
  });

  it("omits X-Shop-Id when no active shop is set", async () => {
    const fetchMock = mockFetchOnce();

    await getProducts();

    const init = fetchMock.mock.calls[0][1] as { headers: Record<string, string> };
    expect(init.headers["X-Shop-Id"]).toBeUndefined();
  });

  it("includes X-Shop-Id after setActiveShopId", async () => {
    const fetchMock = mockFetchOnce();

    setActiveShopId(42);
    await getProducts();

    const init = fetchMock.mock.calls[0][1] as { headers: Record<string, string> };
    expect(init.headers["X-Shop-Id"]).toBe("42");
  });

  it("drops X-Shop-Id again after setActiveShopId(null)", async () => {
    const fetchMock = mockFetchOnce();

    setActiveShopId(7);
    setActiveShopId(null);
    await getProducts();

    const init = fetchMock.mock.calls[0][1] as { headers: Record<string, string> };
    expect(init.headers["X-Shop-Id"]).toBeUndefined();
  });
});
