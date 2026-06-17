import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { Product, Shop, Variant } from "../types";

vi.mock("../api", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
      super(detail);
      this.name = "ApiError";
      this.status = status;
      this.detail = detail;
    }
  },
  getMe: vi.fn(),
  getProducts: vi.fn(),
  restock: vi.fn(),
  adjust: vi.fn(),
}));

import * as api from "../api";

const shopFixture: Shop = {
  shop_id: 1,
  shop_name: "Тестовий магазин",
  shop_slug: "test-shop",
  role: "owner",
  logo_url: null,
  accent_color: "#ff8800",
};

function makeVariant(overrides: Partial<Variant> = {}): Variant {
  return {
    id: 1,
    sku: "SKU-1",
    axis_values: { size: "M" },
    price: "450.00",
    on_hand: 5,
    reserved: 0,
    available: 5,
    low_stock_threshold: 3,
    photo_url: null,
    ...overrides,
  };
}

function makeProduct(overrides: Partial<Product> = {}): Product {
  return {
    id: 1,
    name: "Футболка",
    description: null,
    template_id: null,
    attributes: {},
    is_demo: false,
    archived: false,
    variants: [makeVariant()],
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(api.getMe).mockReset();
  vi.mocked(api.getProducts).mockReset();
  vi.mocked(api.restock).mockReset();
  vi.mocked(api.adjust).mockReset();
  document.documentElement.style.removeProperty("--accent-color");
});

describe("App catalog screen", () => {
  it("renders products from the API: photo placeholder, name, price, stock", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({
        name: "Футболка",
        variants: [makeVariant({ id: 11, price: "450.00", available: 5 })],
      }),
    ]);

    render(<App />);

    expect(await screen.findByText("Футболка")).toBeInTheDocument();
    expect(screen.getByText("450.00 ₴")).toBeInTheDocument();
    expect(screen.getByTestId("available-11")).toHaveTextContent("5 шт.");
    expect(screen.getByText("📦")).toBeInTheDocument();
  });

  it("renders the variant photo when photo_url is set instead of the placeholder", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({
        variants: [makeVariant({ id: 12, photo_url: "https://cdn.example.test/photo.webp" })],
      }),
    ]);

    render(<App />);

    const image = await screen.findByRole("img", { name: "Футболка" });
    expect(image).toHaveAttribute("src", "https://cdn.example.test/photo.webp");
    expect(screen.queryByText("📦")).not.toBeInTheDocument();
  });

  it("applies shop branding: accent color CSS variable and name in header", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);

    expect(await screen.findByText("Тестовий магазин")).toBeInTheDocument();
    await waitFor(() => {
      expect(document.documentElement.style.getPropertyValue("--accent-color")).toBe("#ff8800");
    });
  });

  it("shows low-stock and out-of-stock badges based on threshold", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({
        id: 1,
        name: "Товар А",
        variants: [makeVariant({ id: 21, available: 2, low_stock_threshold: 3 })],
      }),
      makeProduct({
        id: 2,
        name: "Товар Б",
        variants: [makeVariant({ id: 22, available: 0, low_stock_threshold: 3 })],
      }),
    ]);

    render(<App />);

    expect(await screen.findByText("мало")).toBeInTheDocument();
    expect(screen.getByText("нема")).toBeInTheDocument();
  });

  it("filters products by name via the search input", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ id: 1, name: "Футболка", variants: [makeVariant({ id: 31 })] }),
      makeProduct({ id: 2, name: "Свічка", variants: [makeVariant({ id: 32 })] }),
    ]);

    render(<App />);
    await screen.findByText("Футболка");
    expect(screen.getByText("Свічка")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Пошук товарів"), { target: { value: "свіч" } });

    expect(screen.queryByText("Футболка")).not.toBeInTheDocument();
    expect(screen.getByText("Свічка")).toBeInTheDocument();
  });

  it("plus button calls restock and updates the displayed stock", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 41, sku: "SKU-41", on_hand: 5, available: 5 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.restock).mockResolvedValue({ ...variant, on_hand: 6, available: 6 });

    render(<App />);
    await screen.findByTestId("available-41");

    fireEvent.click(screen.getByLabelText("Збільшити залишок: SKU-41"));

    await waitFor(() => {
      expect(screen.getByTestId("available-41")).toHaveTextContent("6 шт.");
    });
    expect(api.restock).toHaveBeenCalledWith(41, 1);
  });

  it("minus button calls adjust with on_hand-1 and updates the displayed stock", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 42, sku: "SKU-42", on_hand: 5, available: 5 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.adjust).mockResolvedValue({ ...variant, on_hand: 4, available: 4 });

    render(<App />);
    await screen.findByTestId("available-42");

    fireEvent.click(screen.getByLabelText("Зменшити залишок: SKU-42"));

    await waitFor(() => {
      expect(screen.getByTestId("available-42")).toHaveTextContent("4 шт.");
    });
    expect(api.adjust).toHaveBeenCalledWith(42, 4);
  });

  it("minus button is disabled when on_hand is already zero", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 43, sku: "SKU-43", on_hand: 0, available: 0 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);

    render(<App />);
    await screen.findByTestId("available-43");

    expect(screen.getByLabelText("Зменшити залишок: SKU-43")).toBeDisabled();
  });
});
