import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { Plan, Product, Reservation, Shop, Template, Variant } from "../types";

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
  getTemplates: vi.fn(),
  getReservations: vi.fn(),
  getPlans: vi.fn(),
  restock: vi.fn(),
  adjust: vi.fn(),
  createProduct: vi.fn(),
  updateProduct: vi.fn(),
  uploadVariantPhoto: vi.fn(),
  reserve: vi.fn(),
  releaseReservation: vi.fn(),
  fulfillReservation: vi.fn(),
  checkoutStars: vi.fn(),
  clearDemos: vi.fn(),
}));

import * as api from "../api";
import { ApiError } from "../api";

const shopFixture: Shop = {
  shop_id: 1,
  shop_name: "Тестовий магазин",
  shop_slug: "test-shop",
  role: "owner",
  logo_url: null,
  accent_color: "#ff8800",
  status: "active",
  is_writable: true,
  trial_ends_at: null,
  current_period_end: "2026-12-01T00:00:00Z",
  plan_code: "pro",
};

const planFixture: Plan = {
  code: "pro",
  name: "Pro",
  period: "month",
  price_uah: "299.00",
  price_stars: 500,
  limits: { max_products: null, photos: true },
};

const clothingTemplate: Template = {
  id: 7,
  code: "clothing",
  name: "Одяг",
  field_schema: {
    attributes: [{ key: "material", label: "Матеріал", type: "string" }],
    variant_axes: [
      { key: "size", label: "Розмір", type: "enum", options: ["XS", "S", "M", "L"] },
      { key: "color", label: "Колір", type: "string" },
    ],
  },
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

function makeReservation(overrides: Partial<Reservation> = {}): Reservation {
  return {
    id: 100,
    variant_id: 1,
    order_id: null,
    qty: 1,
    reason: null,
    customer_note: null,
    source: "manual",
    status: "active",
    expires_at: null,
    created_at: "2026-06-01T00:00:00Z",
    released_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(api.getMe).mockReset();
  vi.mocked(api.getProducts).mockReset();
  vi.mocked(api.getTemplates).mockReset().mockResolvedValue([]);
  vi.mocked(api.getReservations).mockReset().mockResolvedValue([]);
  vi.mocked(api.getPlans).mockReset().mockResolvedValue([]);
  vi.mocked(api.restock).mockReset();
  vi.mocked(api.adjust).mockReset();
  vi.mocked(api.createProduct).mockReset();
  vi.mocked(api.updateProduct).mockReset();
  vi.mocked(api.uploadVariantPhoto).mockReset();
  vi.mocked(api.reserve).mockReset();
  vi.mocked(api.releaseReservation).mockReset();
  vi.mocked(api.fulfillReservation).mockReset();
  vi.mocked(api.checkoutStars).mockReset();
  vi.mocked(api.clearDemos).mockReset();
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
    // Плейсхолдер показується і на рівні картки товару, і на рівні варіанта (своє фото).
    expect(screen.getAllByText("📦").length).toBeGreaterThan(0);
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

describe("Add product form", () => {
  it("renders fields for the selected template and creates the product without a template", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getTemplates).mockResolvedValue([clothingTemplate]);
    const created = makeProduct({ id: 99, name: "Свічка", variants: [makeVariant({ id: 990 })] });
    vi.mocked(api.createProduct).mockResolvedValue(created);

    render(<App />);
    await screen.findByText("Тестовий магазин");

    fireEvent.click(screen.getByRole("button", { name: "Додати товар" }));

    fireEvent.change(screen.getByLabelText("Назва"), { target: { value: "Свічка" } });
    fireEvent.change(screen.getByLabelText("Ціна"), { target: { value: "120" } });

    fireEvent.click(screen.getByRole("button", { name: "Зберегти" }));

    await waitFor(() => {
      expect(api.createProduct).toHaveBeenCalledWith({
        name: "Свічка",
        description: undefined,
        template_id: undefined,
        attributes: {},
        variants: [{ axis_values: {}, price: "120", sku: undefined, on_hand: 0 }],
      });
    });

    expect(await screen.findByText("Свічка")).toBeInTheDocument();
  });

  it("generates clothing variant rows from template axes with correct axis_values", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getTemplates).mockResolvedValue([clothingTemplate]);
    vi.mocked(api.createProduct).mockResolvedValue(makeProduct({ id: 5, name: "Футболка" }));

    render(<App />);
    await screen.findByText("Тестовий магазин");

    fireEvent.click(screen.getByRole("button", { name: "Додати товар" }));
    fireEvent.change(screen.getByLabelText("Шаблон"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText("Назва"), { target: { value: "Футболка" } });

    const rows = document.querySelectorAll(".variant-builder-row");
    expect(rows).toHaveLength(1);
    const firstRow = within(rows[0] as HTMLElement);
    fireEvent.change(firstRow.getByLabelText("Розмір"), { target: { value: "M" } });
    fireEvent.change(firstRow.getByLabelText("Колір"), { target: { value: "Чорний" } });
    fireEvent.change(firstRow.getByLabelText("Ціна"), { target: { value: "300" } });
    fireEvent.change(firstRow.getByLabelText("Початковий залишок"), { target: { value: "10" } });

    fireEvent.click(screen.getByRole("button", { name: "+ Додати варіант" }));
    const rowsAfterAdd = document.querySelectorAll(".variant-builder-row");
    expect(rowsAfterAdd).toHaveLength(2);
    const secondRow = within(rowsAfterAdd[1] as HTMLElement);
    fireEvent.change(secondRow.getByLabelText("Розмір"), { target: { value: "L" } });
    fireEvent.change(secondRow.getByLabelText("Колір"), { target: { value: "Білий" } });
    fireEvent.change(secondRow.getByLabelText("Ціна"), { target: { value: "320" } });

    fireEvent.click(screen.getByRole("button", { name: "Зберегти" }));

    await waitFor(() => {
      expect(api.createProduct).toHaveBeenCalledWith({
        name: "Футболка",
        description: undefined,
        template_id: 7,
        attributes: {},
        variants: [
          { axis_values: { size: "M", color: "Чорний" }, price: "300", sku: undefined, on_hand: 10 },
          { axis_values: { size: "L", color: "Білий" }, price: "320", sku: undefined, on_hand: 0 },
        ],
      });
    });
  });
});

describe("Variant photo upload", () => {
  it("uploads a photo and shows it instead of the placeholder", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 51, sku: "SKU-51", photo_url: null });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.uploadVariantPhoto).mockResolvedValue({
      ...variant,
      photo_url: "https://cdn.example.test/v51.webp",
    });

    render(<App />);
    await screen.findByTestId("available-51");

    const file = new File(["data"], "photo.png", { type: "image/png" });
    const input = screen.getByLabelText("Завантажити фото: SKU-51");
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(api.uploadVariantPhoto).toHaveBeenCalledWith(51, file);
    });
    await waitFor(() => {
      const img = document.querySelector(".variant-photo img");
      expect(img).toHaveAttribute("src", "https://cdn.example.test/v51.webp");
    });
  });

  it("shows a clear message when photo upload returns 402 (plan limit)", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 52, sku: "SKU-52", photo_url: null });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.uploadVariantPhoto).mockRejectedValue(
      new ApiError(402, "Фото недоступні на поточному плані"),
    );

    render(<App />);
    await screen.findByTestId("available-52");

    const file = new File(["data"], "photo.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Завантажити фото: SKU-52"), {
      target: { files: [file] },
    });

    expect(await screen.findByText("Фото недоступні на поточному плані")).toBeInTheDocument();
  });
});

describe("Reservations", () => {
  it("reserve updates reserved/available on the variant and lists it as active", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 61, sku: "SKU-61", on_hand: 5, reserved: 0, available: 5 });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ name: "Сукня", variants: [variant] }),
    ]);
    const reservation = makeReservation({ id: 200, variant_id: 61, qty: 2 });
    vi.mocked(api.reserve).mockResolvedValue(reservation);

    render(<App />);
    await screen.findByTestId("available-61");

    fireEvent.click(screen.getByRole("button", { name: "Відклади" }));
    fireEvent.change(screen.getByLabelText("Кількість (доступно 5)"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Відкласти" }));

    await waitFor(() => {
      expect(api.reserve).toHaveBeenCalledWith(61, {
        qty: 2,
        customer_note: undefined,
        expires_at: undefined,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("available-61")).toHaveTextContent("3 шт.");
    });

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    expect(screen.getByText("2 шт.")).toBeInTheDocument();
    expect(screen.getByText("Сукня (M)")).toBeInTheDocument();
  });

  it("release calls the endpoint and restores availability", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 71, sku: "SKU-71", on_hand: 5, reserved: 2, available: 3 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    const reservation = makeReservation({ id: 300, variant_id: 71, qty: 2 });
    vi.mocked(api.getReservations).mockResolvedValue([reservation]);
    vi.mocked(api.releaseReservation).mockResolvedValue({
      ...reservation,
      status: "released",
    });

    render(<App />);
    await screen.findByTestId("available-71");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    fireEvent.click(screen.getByRole("button", { name: "Зняти" }));

    await waitFor(() => {
      expect(api.releaseReservation).toHaveBeenCalledWith(300);
    });
    await waitFor(() => {
      expect(screen.getByTestId("available-71")).toHaveTextContent("5 шт.");
    });
    expect(screen.getByText("Активних резервів немає")).toBeInTheDocument();
  });

  it("fulfill calls the endpoint and deducts on_hand", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 81, sku: "SKU-81", on_hand: 5, reserved: 2, available: 3 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    const reservation = makeReservation({ id: 400, variant_id: 81, qty: 2 });
    vi.mocked(api.getReservations).mockResolvedValue([reservation]);
    vi.mocked(api.fulfillReservation).mockResolvedValue({
      ...reservation,
      status: "fulfilled",
    });

    render(<App />);
    await screen.findByTestId("available-81");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    fireEvent.click(screen.getByRole("button", { name: "Продано" }));

    await waitFor(() => {
      expect(api.fulfillReservation).toHaveBeenCalledWith(400);
    });
    await waitFor(() => {
      expect(screen.getByTestId("available-81")).toHaveTextContent("3 шт.");
    });
    expect(screen.getByText("Активних резервів немає")).toBeInTheDocument();
  });
});

describe("Trial banner", () => {
  it("shows days remaining computed from trial_ends_at", async () => {
    const trialEndsAt = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();
    vi.mocked(api.getMe).mockResolvedValue({
      ...shopFixture,
      status: "trial",
      is_writable: true,
      trial_ends_at: trialEndsAt,
    });
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);

    expect(await screen.findByText("Тріал: залишилось 3 днів")).toBeInTheDocument();
  });

  it("does not render when status is not trial", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await screen.findByText("Тестовий магазин");

    expect(screen.queryByText(/Тріал:/)).not.toBeInTheDocument();
  });
});

describe("Paywall + read-only state", () => {
  it("shows paywall modal, catalog is visible read-only, and write actions are disabled", async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      ...shopFixture,
      status: "expired",
      is_writable: false,
    });
    const variant = makeVariant({ id: 91, sku: "SKU-91", on_hand: 5, available: 5 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.getPlans).mockResolvedValue([planFixture]);

    render(<App />);
    await screen.findByTestId("available-91");

    // Paywall modal is shown
    expect(screen.getByRole("dialog", { name: "Оберіть тариф" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Оберіть тариф" })).toBeInTheDocument();
    expect(screen.getByText("Pro")).toBeInTheDocument();

    // Catalog is rendered behind the modal (data visible)
    expect(screen.getByText("Футболка")).toBeInTheDocument();

    // All write actions disabled via writable=false
    expect(screen.getByRole("button", { name: "Додати товар" })).toBeDisabled();
    expect(screen.getByLabelText("Збільшити залишок: SKU-91")).toBeDisabled();
    expect(screen.getByLabelText("Зменшити залишок: SKU-91")).toBeDisabled();
    expect(screen.getByLabelText("Завантажити фото: SKU-91")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Відклади" })).toBeDisabled();
  });

  it("collapses modal to sticky banner then re-opens via 'Оформити'", async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      ...shopFixture,
      status: "expired",
      is_writable: false,
    });
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getPlans).mockResolvedValue([planFixture]);

    render(<App />);
    await screen.findByRole("dialog", { name: "Оберіть тариф" });

    // Dismiss the modal
    fireEvent.click(screen.getByRole("button", { name: "Переглянути склад" }));

    // Modal is gone; sticky banner is shown
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("Підписку призупинено — дії заблоковано")).toBeInTheDocument();

    // Re-open via the banner's action button
    fireEvent.click(screen.getByRole("button", { name: "Оформити" }));

    expect(screen.getByRole("dialog", { name: "Оберіть тариф" })).toBeInTheDocument();
  });

  it("checks out via Stars and opens the invoice link", async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      ...shopFixture,
      status: "expired",
      is_writable: false,
    });
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getPlans).mockResolvedValue([planFixture]);
    vi.mocked(api.checkoutStars).mockResolvedValue({
      invoice_link: "https://t.me/invoice/abc",
    });

    render(<App />);
    await screen.findByText("Pro");

    fireEvent.click(screen.getByRole("button", { name: "Оформити через Stars" }));

    await waitFor(() => {
      expect(api.checkoutStars).toHaveBeenCalledWith("pro");
    });
    expect(
      await screen.findByText("https://t.me/invoice/abc"),
    ).toBeInTheDocument();
  });

  it("hides billing UI for managers", async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      ...shopFixture,
      role: "manager",
      status: "expired",
      is_writable: false,
    });
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getPlans).mockResolvedValue([planFixture]);

    render(<App />);

    expect(await screen.findByText("Підписку призупинено")).toBeInTheDocument();
    expect(screen.getByText("Оформлення доступне лише власнику магазину.")).toBeInTheDocument();
    expect(screen.queryByText("Pro")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Оформити через Stars" })).not.toBeInTheDocument();
  });
});

describe("Demo banner", () => {
  it("shows the demo banner and clears demos via the endpoint", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const demoProduct = makeProduct({ id: 1, name: "Демо товар", is_demo: true });
    const ownProduct = makeProduct({
      id: 2,
      name: "Свій товар",
      is_demo: false,
      variants: [makeVariant({ id: 95 })],
    });
    vi.mocked(api.getProducts)
      .mockResolvedValueOnce([demoProduct, ownProduct])
      .mockResolvedValueOnce([ownProduct]);
    vi.mocked(api.clearDemos).mockResolvedValue({ removed: 1 });

    render(<App />);
    await screen.findByText("Демо товар");

    expect(screen.getByText(/Це приклади/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Очистити приклади" }));

    await waitFor(() => {
      expect(api.clearDemos).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.queryByText("Демо товар")).not.toBeInTheDocument();
    });
    expect(screen.queryByText(/Це приклади/)).not.toBeInTheDocument();
    expect(screen.getByText("Свій товар")).toBeInTheDocument();
  });

  it("hides the clear button for managers but still shows the banner", async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...shopFixture, role: "manager" });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ id: 1, name: "Демо товар", is_demo: true }),
    ]);

    render(<App />);
    await screen.findByText("Демо товар");

    expect(screen.getByText(/Це приклади/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Очистити приклади" })).not.toBeInTheDocument();
  });
});
