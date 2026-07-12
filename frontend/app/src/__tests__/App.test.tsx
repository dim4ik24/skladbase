import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type {
  FinanceSummary,
  HistoryEvent,
  Plan,
  Product,
  Reservation,
  Role,
  Shop,
  Template,
  Variant,
} from "../types";

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
  createTemplate: vi.fn(),
  getReservations: vi.fn(),
  getPlans: vi.fn(),
  restock: vi.fn(),
  adjust: vi.fn(),
  createProduct: vi.fn(),
  updateProduct: vi.fn(),
  uploadVariantPhoto: vi.fn(),
  uploadProductPhoto: vi.fn(),
  deleteProductPhoto: vi.fn(),
  updateShopProfile: vi.fn(),
  uploadShopLogo: vi.fn(),
  deleteShopLogo: vi.fn(),
  reserve: vi.fn(),
  releaseReservation: vi.fn(),
  fulfillReservation: vi.fn(),
  checkoutStars: vi.fn(),
  redeemPromo: vi.fn(),
  clearDemos: vi.fn(),
  getFinanceSummary: vi.fn(),
  getFinanceHistory: vi.fn(),
  patchVariant: vi.fn(),
  addVariant: vi.fn(),
  deleteVariant: vi.fn(),
  createInvite: vi.fn(),
  listInvites: vi.fn(),
  revokeInvite: vi.fn(),
  listMembers: vi.fn(),
  removeMember: vi.fn(),
  getRoles: vi.fn(),
  createRole: vi.fn(),
  patchRole: vi.fn(),
  deleteRole: vi.fn(),
  setMemberRole: vi.fn(),
  patchMemberPermissions: vi.fn(),
  setActiveShopId: vi.fn(),
  getNpStatus: vi.fn(),
  putNpKey: vi.fn(),
  deleteNpKey: vi.fn(),
  shipReservation: vi.fn(),
  updateReservationTtn: vi.fn(),
  pickUpReservation: vi.fn(),
  notPickedUpReservation: vi.fn(),
  searchNpCities: vi.fn(),
  getNpWarehouses: vi.fn(),
  getNpSender: vi.fn(),
  putNpSender: vi.fn(),
  createTtn: vi.fn(),
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
  limits: { max_products: null, photos: true, integrations: true },
  products_count: 0,
  active_count: 0,
  max_products: null,
  invite_status: null,
  shops: [{ shop_id: 1, shop_name: "Тестовий магазин", logo_url: null, role: "owner" }],
  active_shop_id: 1,
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
    attributes: [
      { key: "product_type", label: "Тип", type: "enum", options: ["Футболка", "Худі"] },
      { key: "material", label: "Матеріал", type: "string" },
    ],
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
    is_frozen: false,
    archived: false,
    variants: [makeVariant()],
    photos: [],
    ...overrides,
  };
}

function makeFinance(overrides: Partial<FinanceSummary> = {}): FinanceSummary {
  return {
    shop_id: 1,
    revenue_uah: "0.00",
    sales_count: 0,
    units_sold: 0,
    returns_uah: "0.00",
    returns_count: 0,
    chart: [],
    top_products: [],
    release_reasons: [],
    return_reasons: [],
    ...overrides,
  };
}

function makeHistoryEvent(overrides: Partial<HistoryEvent> = {}): HistoryEvent {
  return {
    id: 1,
    date: "2026-07-05T10:00:00Z",
    type: "sale",
    product_name: "Футболка",
    variant_label: "M",
    qty: 1,
    amount: "300.00",
    reason: null,
    customer: null,
    ttn: null,
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
    ttn: null,
    np_status: null,
    np_recipient: null,
    expires_at: null,
    created_at: "2026-06-01T00:00:00Z",
    released_at: null,
    shipped_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(api.getMe).mockReset();
  vi.mocked(api.getProducts).mockReset();
  vi.mocked(api.getTemplates).mockReset().mockResolvedValue([]);
  vi.mocked(api.createTemplate).mockReset();
  vi.mocked(api.getReservations).mockReset().mockResolvedValue([]);
  vi.mocked(api.getPlans).mockReset().mockResolvedValue([]);
  vi.mocked(api.restock).mockReset();
  vi.mocked(api.adjust).mockReset();
  vi.mocked(api.createProduct).mockReset();
  vi.mocked(api.updateProduct).mockReset();
  vi.mocked(api.uploadVariantPhoto).mockReset();
  vi.mocked(api.uploadProductPhoto).mockReset();
  vi.mocked(api.deleteProductPhoto).mockReset();
  vi.mocked(api.updateShopProfile).mockReset();
  vi.mocked(api.uploadShopLogo).mockReset();
  vi.mocked(api.deleteShopLogo).mockReset();
  vi.mocked(api.reserve).mockReset();
  vi.mocked(api.releaseReservation).mockReset();
  vi.mocked(api.fulfillReservation).mockReset();
  vi.mocked(api.checkoutStars).mockReset();
  vi.mocked(api.redeemPromo).mockReset();
  vi.mocked(api.clearDemos).mockReset();
  vi.mocked(api.getFinanceSummary).mockReset().mockResolvedValue(makeFinance());
  vi.mocked(api.getFinanceHistory).mockReset().mockResolvedValue([]);
  vi.mocked(api.patchVariant).mockReset();
  vi.mocked(api.addVariant).mockReset();
  vi.mocked(api.deleteVariant).mockReset();
  vi.mocked(api.createInvite).mockReset();
  vi.mocked(api.listInvites).mockReset().mockResolvedValue([]);
  vi.mocked(api.revokeInvite).mockReset();
  vi.mocked(api.listMembers).mockReset().mockResolvedValue([]);
  vi.mocked(api.removeMember).mockReset();
  vi.mocked(api.getRoles).mockReset().mockResolvedValue([]);
  vi.mocked(api.createRole).mockReset();
  vi.mocked(api.patchRole).mockReset();
  vi.mocked(api.deleteRole).mockReset();
  vi.mocked(api.setMemberRole).mockReset();
  vi.mocked(api.patchMemberPermissions).mockReset();
  vi.mocked(api.setActiveShopId).mockReset();
  vi.mocked(api.getNpStatus).mockReset().mockResolvedValue({ connected: false });
  vi.mocked(api.putNpKey).mockReset();
  vi.mocked(api.deleteNpKey).mockReset();
  vi.mocked(api.shipReservation).mockReset();
  vi.mocked(api.updateReservationTtn).mockReset();
  vi.mocked(api.pickUpReservation).mockReset();
  vi.mocked(api.notPickedUpReservation).mockReset();
  vi.mocked(api.searchNpCities).mockReset();
  vi.mocked(api.getNpWarehouses).mockReset();
  vi.mocked(api.getNpSender).mockReset().mockResolvedValue({
    city_ref: null,
    city_name: null,
    warehouse_ref: null,
    warehouse_name: null,
    phone: null,
    name: null,
  });
  vi.mocked(api.putNpSender).mockReset();
  vi.mocked(api.createTtn).mockReset();
  document.documentElement.style.removeProperty("--accent-color");
  localStorage.clear();
});

// Default tab is Dashboard; navigate to Sklad when tests need catalog content.
async function goToSklad() {
  await screen.findByText("Тестовий магазин");
  fireEvent.click(screen.getByRole("tab", { name: "Склад" }));
}

// Open modal, then open the variant sheet for the tag with the given axisLabel.
// VariantSheet is code-split (React.lazy) — opening the tag mounts a
// Suspense boundary that resolves on a microtask, so callers must await
// its actual appearance before querying anything inside it.
async function openSheet(tagLabel: string) {
  fireEvent.click(await screen.findByLabelText(`Варіант: ${tagLabel}`));
  await screen.findByRole("dialog", { name: new RegExp(`^Варіант: `) });
}

// Reservation badges are clean (no action buttons) — tap the badge to open
// the info sheet, which exposes the state-based actions (Зняти/Відправлено/...).
async function openReservationSheet(productName: string) {
  fireEvent.click(await screen.findByLabelText(`Резерв: ${productName}`));
}

describe("App catalog screen", () => {
  it("renders products from the API: photo placeholder, name, price, stock", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({
        name: "Футболка",
        variants: [makeVariant({ id: 11, price: "450.00", on_hand: 5, reserved: 0, available: 5 })],
      }),
    ]);

    render(<App />);
    await goToSklad();

    expect(await screen.findByText("Футболка")).toBeInTheDocument();
    // Компактна картка: діапазон цін, сумарний available, бейдж варіантів
    expect(screen.getByText("450 ₴")).toBeInTheDocument();
    expect(screen.getByText("5 шт.")).toBeInTheDocument();
    expect(screen.getByText("1 варіант")).toBeInTheDocument();
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
    await goToSklad();

    const image = await screen.findByRole("img", { name: "Футболка" });
    expect(image).toHaveAttribute("src", "https://cdn.example.test/photo.webp");
    expect(screen.queryByText("📦")).not.toBeInTheDocument();
  });

  it("variant chip falls back to the product's first photo when the variant has none", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 62, sku: "SKU-62", photo_url: null });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({
        name: "Сукня",
        variants: [variant],
        photos: [{ id: 1, url: "https://cdn.example.test/product-cover.webp", position: 0 }],
      }),
    ]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Сукня");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Сукня"));

    const tagButton = await screen.findByLabelText("Варіант: M");
    const img = tagButton.querySelector("img");
    expect(img).toHaveAttribute("src", "https://cdn.example.test/product-cover.webp");
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

  it("renders the shop name inside the animated GradientText heading", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);

    const name = await screen.findByText("Тестовий магазин");
    expect(name).toHaveClass("gradient-text");
    expect(name.closest("h1")).toHaveClass("shop-name");
  });

  it("shows low-stock and out-of-stock badges in the variant tag (no sheet needed)", async () => {
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
    await goToSklad();

    // Badge "мало" is visible in the VariantTag without opening the sheet
    fireEvent.click(screen.getByLabelText("Редагувати товар: Товар А"));
    expect(await screen.findByText("мало")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Закрити" }));

    fireEvent.click(await screen.findByLabelText("Редагувати товар: Товар Б"));
    expect(await screen.findByText("нема")).toBeInTheDocument();
  });

  it("filters products by name via the search input", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ id: 1, name: "Футболка", variants: [makeVariant({ id: 31 })] }),
      makeProduct({ id: 2, name: "Свічка", variants: [makeVariant({ id: 32 })] }),
    ]);

    render(<App />);
    await goToSklad();
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
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-41"); // visible in VariantTag

    await openSheet("M");
    fireEvent.click(screen.getByLabelText("Збільшити залишок: SKU-41"));

    await waitFor(() => {
      expect(screen.getByTestId("available-41")).toHaveTextContent("6 шт.");
    });
    expect(api.restock).toHaveBeenCalledWith(41, 1);
  });

  it("minus button opens a write-off dialog instead of adjusting immediately", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 42, sku: "SKU-42", on_hand: 5, available: 5 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-42");

    await openSheet("M");
    fireEvent.click(screen.getByLabelText("Зменшити залишок: SKU-42"));

    expect(screen.getByText("Кількість (доступно 5)")).toBeInTheDocument();
    expect(screen.getByText("💰 Продано")).toBeInTheDocument();
    expect(api.adjust).not.toHaveBeenCalled();
  });

  it("write-off dialog: sold reason calls adjust with {qty, reason} and updates stock", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 42, sku: "SKU-42", on_hand: 5, available: 5 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.adjust).mockResolvedValue({ ...variant, on_hand: 3, available: 3 });

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-42");

    await openSheet("M");
    fireEvent.click(screen.getByLabelText("Зменшити залишок: SKU-42"));

    fireEvent.change(screen.getByLabelText("Кількість (доступно 5)"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByText("💰 Продано"));
    fireEvent.click(screen.getByText("Списати"));

    await waitFor(() => {
      expect(api.adjust).toHaveBeenCalledWith(42, {
        qty: 2,
        reason: "sold",
        comment: undefined,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("available-42")).toHaveTextContent("3 шт.");
    });
  });

  it("write-off dialog: 'other' reason without a comment is rejected client-side", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 42, sku: "SKU-42", on_hand: 5, available: 5 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-42");

    await openSheet("M");
    fireEvent.click(screen.getByLabelText("Зменшити залишок: SKU-42"));

    fireEvent.click(screen.getByText("❓ Інше"));
    expect(screen.getByText("Коментар (обов'язково)")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Списати"));

    expect(screen.getByLabelText("Коментар (обов'язково)")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(api.adjust).not.toHaveBeenCalled();
  });

  it("adjust success refetches the finance summary (Дохід не лишається застарілим)", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 44, sku: "SKU-44", on_hand: 5, available: 5 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.adjust).mockResolvedValue({ ...variant, on_hand: 4, available: 4 });
    vi.mocked(api.getFinanceSummary)
      .mockResolvedValueOnce(makeFinance())
      .mockResolvedValueOnce(makeFinance({ revenue_uah: "150.00", sales_count: 1, units_sold: 1 }));

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-44");

    await openSheet("M");
    fireEvent.click(screen.getByLabelText("Зменшити залишок: SKU-44"));
    fireEvent.click(screen.getByText("💰 Продано"));
    fireEvent.click(screen.getByText("Списати"));

    await waitFor(() => {
      expect(api.getFinanceSummary).toHaveBeenCalledTimes(2);
    });
  });

  it("minus button is disabled when on_hand is already zero", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 43, sku: "SKU-43", on_hand: 0, available: 0 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-43");

    await openSheet("M");
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
    await goToSklad();

    fireEvent.click(screen.getByRole("button", { name: "Додати товар" }));

    fireEvent.change(screen.getByLabelText("Назва"), { target: { value: "Свічка" } });
    fireEvent.change(screen.getByLabelText("Ціна"), { target: { value: "120" } });

    fireEvent.click(screen.getByRole("button", { name: "Створити" }));

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
    await goToSklad();

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

    fireEvent.click(screen.getByRole("button", { name: "Створити" }));

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

  it("renders an enum attribute as a select and includes the chosen value in attributes", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getTemplates).mockResolvedValue([clothingTemplate]);
    vi.mocked(api.createProduct).mockResolvedValue(makeProduct({ id: 8, name: "Худі" }));

    render(<App />);
    await goToSklad();

    fireEvent.click(screen.getByRole("button", { name: "Додати товар" }));
    fireEvent.change(screen.getByLabelText("Шаблон"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText("Назва"), { target: { value: "Худі" } });
    fireEvent.click(screen.getByRole("button", { name: "Додатково" }));

    const typeField = screen.getByLabelText("Тип");
    expect(typeField.tagName).toBe("SELECT");
    fireEvent.change(typeField, { target: { value: "Худі" } });

    const firstRow = within(document.querySelectorAll(".variant-builder-row")[0] as HTMLElement);
    fireEvent.change(firstRow.getByLabelText("Ціна"), { target: { value: "890" } });

    fireEvent.click(screen.getByRole("button", { name: "Створити" }));

    await waitFor(() => {
      expect(api.createProduct).toHaveBeenCalledWith(
        expect.objectContaining({ attributes: { product_type: "Худі" } }),
      );
    });
  });
});

describe("Create form field validation highlighting", () => {
  it("highlights the name field and shows a banner when name is empty", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getTemplates).mockResolvedValue([]);

    render(<App />);
    await goToSklad();
    fireEvent.click(screen.getByRole("button", { name: "Додати товар" }));

    fireEvent.change(screen.getByLabelText("Ціна"), { target: { value: "120" } });
    fireEvent.click(screen.getByRole("button", { name: "Створити" }));

    expect(await screen.findByText("Вкажіть назву товару")).toBeInTheDocument();
    expect(screen.getByLabelText("Назва")).toHaveClass("input-error");
    expect(api.createProduct).not.toHaveBeenCalled();
  });

  it("highlights the empty price field for the second variant with a 1-based message", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getTemplates).mockResolvedValue([clothingTemplate]);

    render(<App />);
    await goToSklad();
    fireEvent.click(screen.getByRole("button", { name: "Додати товар" }));
    fireEvent.change(screen.getByLabelText("Шаблон"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText("Назва"), { target: { value: "Футболка" } });

    const firstRow = within(document.querySelectorAll(".variant-builder-row")[0] as HTMLElement);
    fireEvent.change(firstRow.getByLabelText("Ціна"), { target: { value: "300" } });

    fireEvent.click(screen.getByRole("button", { name: "+ Додати варіант" }));
    const rows = document.querySelectorAll(".variant-builder-row");
    expect(rows).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Створити" }));

    expect(await screen.findByText("Вкажіть ціну для варіанта 2")).toBeInTheDocument();
    const secondRow = within(document.querySelectorAll(".variant-builder-row")[1] as HTMLElement);
    expect(secondRow.getByLabelText("Ціна")).toHaveClass("input-error");
    expect(api.createProduct).not.toHaveBeenCalled();
  });

  it("clears the highlight once the user starts typing into the field", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getTemplates).mockResolvedValue([]);

    render(<App />);
    await goToSklad();
    fireEvent.click(screen.getByRole("button", { name: "Додати товар" }));

    fireEvent.change(screen.getByLabelText("Ціна"), { target: { value: "120" } });
    fireEvent.click(screen.getByRole("button", { name: "Створити" }));
    expect(await screen.findByText("Вкажіть назву товару")).toBeInTheDocument();
    expect(screen.getByLabelText("Назва")).toHaveClass("input-error");

    fireEvent.change(screen.getByLabelText("Назва"), { target: { value: "Свічка" } });
    expect(screen.getByLabelText("Назва")).not.toHaveClass("input-error");
  });
});

describe("Create form template memory", () => {
  it("saves the selected template id to localStorage after a successful create", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getTemplates).mockResolvedValue([clothingTemplate]);
    vi.mocked(api.createProduct).mockResolvedValue(makeProduct({ id: 5, name: "Футболка" }));
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");

    render(<App />);
    await goToSklad();
    fireEvent.click(screen.getByRole("button", { name: "Додати товар" }));
    fireEvent.change(screen.getByLabelText("Шаблон"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText("Назва"), { target: { value: "Футболка" } });

    const firstRow = within(document.querySelectorAll(".variant-builder-row")[0] as HTMLElement);
    fireEvent.change(firstRow.getByLabelText("Ціна"), { target: { value: "300" } });

    fireEvent.click(screen.getByRole("button", { name: "Створити" }));

    await waitFor(() => {
      expect(setItemSpy).toHaveBeenCalledWith("skladbase:lastTemplateId", "7");
    });
  });

  it("preselects the last used template when opening the create form", async () => {
    localStorage.setItem("skladbase:lastTemplateId", "7");
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getTemplates).mockResolvedValue([clothingTemplate]);

    render(<App />);
    await goToSklad();
    fireEvent.click(screen.getByRole("button", { name: "Додати товар" }));

    expect(screen.getByLabelText("Шаблон")).toHaveValue("7");
    expect(screen.getByLabelText("Розмір")).toBeInTheDocument();
    expect(screen.getByLabelText("Колір")).toBeInTheDocument();
  });

  it("ignores a saved template id that no longer exists, without crashing", async () => {
    localStorage.setItem("skladbase:lastTemplateId", "999");
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getTemplates).mockResolvedValue([clothingTemplate]);

    render(<App />);
    await goToSklad();
    fireEvent.click(screen.getByRole("button", { name: "Додати товар" }));

    expect(screen.getByLabelText("Шаблон")).toHaveValue("");
    expect(screen.queryByLabelText("Розмір")).not.toBeInTheDocument();
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
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-51");

    await openSheet("M");

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

  it("shows UpgradePrompt when photo upload returns 402 (plan limit)", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 52, sku: "SKU-52", photo_url: null });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.uploadVariantPhoto).mockRejectedValue(
      new ApiError(402, "Фото недоступні на поточному плані"),
    );

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-52");

    await openSheet("M");

    const file = new File(["data"], "photo.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Завантажити фото: SKU-52"), {
      target: { files: [file] },
    });

    expect(await screen.findByText("Фото недоступні на поточному плані")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Обрати тариф" })).toBeInTheDocument();
  });
});

describe("Product photo gallery viewer", () => {
  async function openGalleryViewer(photoIndex: number) {
    fireEvent.click(screen.getByRole("tab", { name: "Фото" }));
    const thumbs = document.querySelectorAll(".photo-thumb img");
    fireEvent.click(thumbs[photoIndex]);
    // PhotoViewer is code-split — await its Suspense boundary resolving.
    await screen.findByRole("dialog", { name: "Перегляд фото" });
    return document.querySelector(".photo-viewer-image") as HTMLImageElement;
  }

  function twoPhotoProduct() {
    return makeProduct({
      name: "Сукня",
      photos: [
        { id: 1, url: "https://cdn.example.test/p1.webp", position: 0 },
        { id: 2, url: "https://cdn.example.test/p2.webp", position: 1 },
      ],
    });
  }

  it("tapping a thumbnail opens the viewer on that photo", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([twoPhotoProduct()]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Сукня");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Сукня"));

    const image = await openGalleryViewer(1);
    expect(image).toHaveAttribute("src", "https://cdn.example.test/p2.webp");
    expect(screen.getByRole("dialog", { name: "Перегляд фото" })).toBeInTheDocument();
  });

  it("swiping left/right navigates photos, looping at both ends", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([twoPhotoProduct()]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Сукня");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Сукня"));

    const image = await openGalleryViewer(0);
    expect(image).toHaveAttribute("src", "https://cdn.example.test/p1.webp");

    // Свайп вліво -> наступне фото
    fireEvent.touchStart(image, { touches: [{ clientX: 200 }] });
    fireEvent.touchEnd(image, { changedTouches: [{ clientX: 100 }] });
    expect(image).toHaveAttribute("src", "https://cdn.example.test/p2.webp");

    // Свайп вліво знову -> зациклено на перше
    fireEvent.touchStart(image, { touches: [{ clientX: 200 }] });
    fireEvent.touchEnd(image, { changedTouches: [{ clientX: 100 }] });
    expect(image).toHaveAttribute("src", "https://cdn.example.test/p1.webp");

    // Свайп вправо -> зациклено назад на останнє
    fireEvent.touchStart(image, { touches: [{ clientX: 100 }] });
    fireEvent.touchEnd(image, { changedTouches: [{ clientX: 200 }] });
    expect(image).toHaveAttribute("src", "https://cdn.example.test/p2.webp");
  });

  it("a small touch movement below the swipe threshold does not navigate", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([twoPhotoProduct()]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Сукня");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Сукня"));

    const image = await openGalleryViewer(0);
    fireEvent.touchStart(image, { touches: [{ clientX: 200 }] });
    fireEvent.touchEnd(image, { changedTouches: [{ clientX: 185 }] });

    expect(image).toHaveAttribute("src", "https://cdn.example.test/p1.webp");
  });

  it("desktop arrow buttons navigate the viewer", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([twoPhotoProduct()]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Сукня");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Сукня"));

    const image = await openGalleryViewer(0);
    fireEvent.click(screen.getByRole("button", { name: "Наступне фото" }));
    expect(image).toHaveAttribute("src", "https://cdn.example.test/p2.webp");

    fireEvent.click(screen.getByRole("button", { name: "Попереднє фото" }));
    expect(image).toHaveAttribute("src", "https://cdn.example.test/p1.webp");
  });

  it("closes on the close button", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([twoPhotoProduct()]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Сукня");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Сукня"));
    await openGalleryViewer(0);

    const dialog = screen.getByRole("dialog", { name: "Перегляд фото" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Закрити" }));

    expect(screen.queryByRole("dialog", { name: "Перегляд фото" })).not.toBeInTheDocument();
  });
});

describe("Продано (VariantSheet)", () => {
  it("without shipping calls adjust with reason=sold — no duplicated write-off logic", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 71, sku: "SKU-71", on_hand: 5, available: 5 });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ name: "Кепка", variants: [variant] }),
    ]);
    vi.mocked(api.adjust).mockResolvedValue({ ...variant, on_hand: 3, reserved: 0 });

    render(<App />);
    await goToSklad();
    await screen.findByText("Кепка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Кепка"));
    await screen.findByTestId("available-71");
    await openSheet("M");

    fireEvent.click(screen.getByRole("button", { name: "Продано" }));
    const sellForm = document.querySelector(".sell-form") as HTMLElement;
    fireEvent.change(within(sellForm).getByLabelText("Кількість (доступно 5)"), {
      target: { value: "2" },
    });
    fireEvent.click(within(sellForm).getByRole("button", { name: "Продано" }));

    await waitFor(() => {
      expect(api.adjust).toHaveBeenCalledWith(71, { qty: 2, reason: "sold" });
    });
    expect(api.reserve).not.toHaveBeenCalled();
  });

  it("with 'Оформити відправку' reserves then opens ShipSheet, and submitting ships it", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 72, sku: "SKU-72", on_hand: 5, available: 5, price: "300.00" });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ name: "Штани", variants: [variant] }),
    ]);
    const reservation = makeReservation({ id: 210, variant_id: 72, qty: 1 });
    vi.mocked(api.reserve).mockResolvedValue(reservation);
    vi.mocked(api.shipReservation).mockResolvedValue({
      ...reservation,
      status: "shipped",
      ttn: "20450123456789",
    });

    render(<App />);
    await goToSklad();
    await screen.findByText("Штани");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Штани"));
    await screen.findByTestId("available-72");
    await openSheet("M");

    fireEvent.click(screen.getByRole("button", { name: "Продано" }));
    const sellForm = document.querySelector(".sell-form") as HTMLElement;
    fireEvent.click(within(sellForm).getByRole("checkbox", { name: "Оформити відправку" }));
    fireEvent.click(within(sellForm).getByRole("button", { name: "Продано" }));

    await waitFor(() => {
      expect(api.reserve).toHaveBeenCalledWith(72, { qty: 1 });
    });
    expect(api.adjust).not.toHaveBeenCalled();

    const shipDialog = await screen.findByRole("dialog", { name: /Відправити:/ });
    fireEvent.change(within(shipDialog).getByLabelText("ТТН (можна додати пізніше)"), {
      target: { value: "20450123456789" },
    });
    fireEvent.click(within(shipDialog).getByRole("button", { name: "Відправлено" }));

    await waitFor(() => {
      expect(api.shipReservation).toHaveBeenCalledWith(210, { ttn: "20450123456789" });
    });
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
    await goToSklad();
    await screen.findByText("Сукня");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Сукня"));
    await screen.findByTestId("available-61");

    await openSheet("M");

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
    expect(screen.getByText("M · 2 шт. × 450 ₴ = 900 ₴")).toBeInTheDocument();
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
    await goToSklad();
    await screen.findByText("Футболка");
    // Open modal so available-71 enters the DOM (visible in VariantTag without opening sheet)
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-71");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    await openReservationSheet("Футболка");
    fireEvent.click(screen.getByRole("button", { name: "Зняти" }));
    // ReleaseSheet is code-split — first open in a test run resolves async.
    fireEvent.click(await screen.findByText("Клієнт передумав"));
    fireEvent.click(screen.getByRole("button", { name: "Підтвердити" }));

    await waitFor(() => {
      expect(api.releaseReservation).toHaveBeenCalledWith(300, {
        reason: "customer_changed_mind",
        comment: undefined,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("available-71")).toHaveTextContent("5 шт.");
    });
    expect(screen.getByText("Активних резервів немає")).toBeInTheDocument();
  });

  it("release dialog: 'other' reason without a comment is rejected client-side", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 72, sku: "SKU-72", on_hand: 5, reserved: 2, available: 3 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    const reservation = makeReservation({ id: 301, variant_id: 72, qty: 2 });
    vi.mocked(api.getReservations).mockResolvedValue([reservation]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-72");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    await openReservationSheet("Футболка");
    fireEvent.click(screen.getByRole("button", { name: "Зняти" }));
    fireEvent.click(screen.getByText("❓ Інша причина"));
    fireEvent.click(screen.getByRole("button", { name: "Підтвердити" }));

    expect(screen.getByLabelText("Коментар (обов'язково)")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(api.releaseReservation).not.toHaveBeenCalled();
  });

  it("tapping the badge opens a bottom sheet (portal), and 'Зняти' opens a second one on top", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 73, sku: "SKU-73", on_hand: 5, reserved: 2, available: 3 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    const reservation = makeReservation({ id: 302, variant_id: 73, qty: 2 });
    vi.mocked(api.getReservations).mockResolvedValue([reservation]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-73");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    const cardButton = screen.getByRole("button", { name: "Резерв: Футболка" });
    const card = cardButton.closest("li") as HTMLElement;
    fireEvent.click(cardButton);

    const infoDialog = await screen.findByRole("dialog", { name: /Резерв: Футболка/ });
    expect(infoDialog).toBeInTheDocument();
    // Портал (createPortal у document.body) — sheet НЕ вкладений у саму бирку,
    // на відміну від старого інлайн-ReleaseForm, який розсипався поверх карток.
    expect(card.contains(infoDialog)).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Зняти" }));

    const releaseDialog = await screen.findByRole("dialog", { name: /Зняти резерв/ });
    expect(card.contains(releaseDialog)).toBe(false);
    expect(screen.getByText("Клієнт передумав")).toBeInTheDocument();
  });

  it("reservation card falls back to '#variant_id' when products haven't loaded/resolved", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const reservation = makeReservation({ id: 303, variant_id: 999, qty: 4 });
    vi.mocked(api.getReservations).mockResolvedValue([reservation]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Тестовий магазин");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));

    expect(screen.getByText("Варіант #999")).toBeInTheDocument();
    expect(screen.getByText("4 шт.")).toBeInTheDocument();
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
    await goToSklad();
    await screen.findByText("Футболка");
    // Open modal so available-81 enters the DOM (visible in VariantTag without opening sheet)
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-81");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    await openReservationSheet("Футболка");
    fireEvent.click(screen.getByRole("button", { name: "Продано" }));

    await waitFor(() => {
      expect(api.fulfillReservation).toHaveBeenCalledWith(400);
    });
    await waitFor(() => {
      expect(screen.getByTestId("available-81")).toHaveTextContent("3 шт.");
    });
    expect(screen.getByText("Активних резервів немає")).toBeInTheDocument();
  });

  it("fulfill success refetches the finance summary (Дохід не лишається застарілим)", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 82, sku: "SKU-82", on_hand: 5, reserved: 2, available: 3 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    const reservation = makeReservation({ id: 401, variant_id: 82, qty: 2 });
    vi.mocked(api.getReservations).mockResolvedValue([reservation]);
    vi.mocked(api.fulfillReservation).mockResolvedValue({
      ...reservation,
      status: "fulfilled",
    });
    vi.mocked(api.getFinanceSummary)
      .mockResolvedValueOnce(makeFinance())
      .mockResolvedValueOnce(makeFinance({ revenue_uah: "400.00", sales_count: 1, units_sold: 2 }));

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-82");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    await openReservationSheet("Футболка");
    fireEvent.click(screen.getByRole("button", { name: "Продано" }));

    await waitFor(() => {
      expect(api.fulfillReservation).toHaveBeenCalledWith(401);
    });
    await waitFor(() => {
      expect(api.getFinanceSummary).toHaveBeenCalledTimes(2);
    });
  });

  it("reservation card renders variant photo and axis label", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({
      id: 83,
      sku: "SKU-83",
      axis_values: { size: "XL", color: "Рожевий" },
      photo_url: "https://example.com/photo.jpg",
    });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ name: "Сукня", variants: [variant] }),
    ]);
    const reservation = makeReservation({
      id: 402,
      variant_id: 83,
      qty: 3,
      customer_note: "Оксана, +380501112233",
    });
    vi.mocked(api.getReservations).mockResolvedValue([reservation]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Сукня");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Сукня"));
    await screen.findByTestId("available-83");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));

    const row2 = screen.getByText("XL / Рожевий · 3 шт. × 450 ₴ = 1350 ₴");
    expect(row2).toBeInTheDocument();
    const card = row2.closest("li");
    expect(card).not.toBeNull();
    expect(within(card as HTMLElement).getByText("Сукня")).toBeInTheDocument();
    const photo = (card as HTMLElement).querySelector("img");
    expect(photo).toHaveAttribute("src", "https://example.com/photo.jpg");
    expect(within(card as HTMLElement).getByText("Оксана, +380501112233")).toBeInTheDocument();
  });

  it("shipped reservation card shows the np_status tracking line", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 84, sku: "SKU-84" });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ name: "Кросівки", variants: [variant] }),
    ]);
    const reservation = makeReservation({
      id: 403,
      variant_id: 84,
      qty: 1,
      status: "shipped",
      ttn: "20450000000009",
      np_status: "Прибув у відділення",
    });
    vi.mocked(api.getReservations).mockResolvedValue([reservation]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Кросівки");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Кросівки"));
    await screen.findByTestId("available-84");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));

    expect(screen.getByText("📍 Прибув у відділення")).toBeInTheDocument();
  });

  it("badge tap opens an info sheet with full details and active-state actions", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 91, sku: "SKU-91", price: "450.00" });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ name: "Сукня", variants: [variant] }),
    ]);
    const reservation = makeReservation({
      id: 500,
      variant_id: 91,
      qty: 2,
      customer_note: "Оксана, +380501112233",
    });
    vi.mocked(api.getReservations).mockResolvedValue([reservation]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Сукня");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Сукня"));
    await screen.findByTestId("available-91");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    await openReservationSheet("Сукня");

    const dialog = screen.getByRole("dialog", { name: "Резерв: Сукня" });
    expect(within(dialog).getByText("2 шт. × 450 ₴ = 900 ₴")).toBeInTheDocument();
    expect(within(dialog).getByText("Оксана, +380501112233")).toBeInTheDocument();
    expect(within(dialog).getByText("Активний")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Відправлено" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Продано" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Зняти" })).toBeInTheDocument();
  });

  it("shipped reservation info sheet exposes Забрав / Не забрав, and Забрав calls the endpoint", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 92, sku: "SKU-92" });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ name: "Кепка", variants: [variant] }),
    ]);
    const reservation = makeReservation({
      id: 501,
      variant_id: 92,
      qty: 1,
      status: "shipped",
      ttn: "20450000000099",
    });
    vi.mocked(api.getReservations).mockResolvedValue([reservation]);
    vi.mocked(api.pickUpReservation).mockResolvedValue({ ...reservation, status: "fulfilled" });

    render(<App />);
    await goToSklad();
    await screen.findByText("Кепка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Кепка"));
    await screen.findByTestId("available-92");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    await openReservationSheet("Кепка");

    const dialog = screen.getByRole("dialog", { name: "Резерв: Кепка" });
    expect(within(dialog).getByText("🚚 Відправлено")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Забрав" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Не забрав" })).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Забрав" }));

    await waitFor(() => {
      expect(api.pickUpReservation).toHaveBeenCalledWith(501);
    });
  });

  it("shipped reservation sheet shows the np_recipient line when present", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 93, sku: "SKU-93" });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ name: "Шапка", variants: [variant] }),
    ]);
    const reservation = makeReservation({
      id: 502,
      variant_id: 93,
      qty: 1,
      status: "shipped",
      ttn: "20450000000098",
      np_recipient: "Іваненко Іван · Львів, Відділення №5",
    });
    vi.mocked(api.getReservations).mockResolvedValue([reservation]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Шапка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Шапка"));
    await screen.findByTestId("available-93");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    await openReservationSheet("Шапка");

    const dialog = screen.getByRole("dialog", { name: "Резерв: Шапка" });
    expect(dialog.textContent).toContain("📮 Іваненко Іван · Львів, Відділення №5");
  });

  it("ship: manual TTN with an invalid format is rejected client-side", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 94, sku: "SKU-94" });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ name: "Кофта", variants: [variant] }),
    ]);
    const reservation = makeReservation({ id: 503, variant_id: 94, qty: 1 });
    vi.mocked(api.getReservations).mockResolvedValue([reservation]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Кофта");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Кофта"));
    await screen.findByTestId("available-94");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    await openReservationSheet("Кофта");
    fireEvent.click(screen.getByRole("button", { name: "Відправлено" }));

    const shipDialog = await screen.findByRole("dialog", { name: /Відправити:/ });
    fireEvent.change(within(shipDialog).getByLabelText("ТТН (можна додати пізніше)"), {
      target: { value: "12345" },
    });
    fireEvent.click(within(shipDialog).getByRole("button", { name: "Відправлено" }));

    expect(
      await within(shipDialog).findByText(
        "ТТН Нової Пошти — 14 цифр, починається з 20 або 59",
      ),
    ).toBeInTheDocument();
    expect(api.shipReservation).not.toHaveBeenCalled();
  });

  it("ship: a valid manual TTN is accepted", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 95, sku: "SKU-95" });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ name: "Штани", variants: [variant] }),
    ]);
    const reservation = makeReservation({ id: 504, variant_id: 95, qty: 1 });
    vi.mocked(api.getReservations).mockResolvedValue([reservation]);
    vi.mocked(api.shipReservation).mockResolvedValue({
      ...reservation,
      status: "shipped",
      ttn: "20450123456789",
    });

    render(<App />);
    await goToSklad();
    await screen.findByText("Штани");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Штани"));
    await screen.findByTestId("available-95");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    await openReservationSheet("Штани");
    fireEvent.click(screen.getByRole("button", { name: "Відправлено" }));

    const shipDialog = await screen.findByRole("dialog", { name: /Відправити:/ });
    fireEvent.change(within(shipDialog).getByLabelText("ТТН (можна додати пізніше)"), {
      target: { value: "20450123456789" },
    });
    fireEvent.click(within(shipDialog).getByRole("button", { name: "Відправлено" }));

    await waitFor(() => {
      expect(api.shipReservation).toHaveBeenCalledWith(504, { ttn: "20450123456789" });
    });
  });
});

describe("Trial banner", () => {
  it("shows days remaining for a live trial", async () => {
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

  it("does not render when trial_ends_at is in the past (expired trial)", async () => {
    const expiredAt = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    vi.mocked(api.getMe).mockResolvedValue({
      ...shopFixture,
      status: "trial",
      is_writable: false,
      trial_ends_at: expiredAt,
    });
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await screen.findByText("Тестовий магазин");

    expect(screen.queryByText(/Тріал:/)).not.toBeInTheDocument();
  });
});

describe("Free plan limits and upgrade prompt", () => {
  it("shows slot counter when max_products is set", async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      ...shopFixture,
      max_products: 5,
      active_count: 3,
    });
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await goToSklad();

    expect(screen.getByText("3/5 активних")).toBeInTheDocument();
  });

  it("does not show slot counter when max_products is null (unlimited)", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await screen.findByText("Тестовий магазин");

    expect(screen.queryByText(/активних/)).not.toBeInTheDocument();
  });

  it("clicking 'Додати товар' at limit shows UpgradePrompt instead of the form", async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      ...shopFixture,
      max_products: 3,
      active_count: 3,
    });
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await goToSklad();

    fireEvent.click(screen.getByRole("button", { name: "Додати товар" }));

    expect(await screen.findByText(/Ліміт плану/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Обрати тариф" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Назва")).not.toBeInTheDocument();
  });

  it("restock 402 shows UpgradePrompt with the server error message", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 101, sku: "SKU-101" });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.restock).mockRejectedValue(
      new ApiError(402, "Ліміт товарів вичерпано"),
    );

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-101");

    await openSheet("M");
    fireEvent.click(screen.getByLabelText("Збільшити залишок: SKU-101"));

    expect(await screen.findByText("Ліміт товарів вичерпано")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Обрати тариф" })).toBeInTheDocument();
  });

  it("'Обрати тариф' in UpgradePrompt opens the paywall modal", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 102, sku: "SKU-102" });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.getPlans).mockResolvedValue([planFixture]);
    vi.mocked(api.restock).mockRejectedValue(
      new ApiError(402, "Ліміт товарів вичерпано"),
    );

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-102");

    await openSheet("M");
    fireEvent.click(screen.getByLabelText("Збільшити залишок: SKU-102"));
    await screen.findByRole("button", { name: "Обрати тариф" });

    fireEvent.click(screen.getByRole("button", { name: "Обрати тариф" }));

    expect(await screen.findByText("Pro")).toBeInTheDocument();
  });

  it("hides billing UI for managers in the paywall modal", async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      ...shopFixture,
      role: "manager",
    });
    const variant = makeVariant({ id: 103, sku: "SKU-103" });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.getPlans).mockResolvedValue([planFixture]);
    vi.mocked(api.restock).mockRejectedValue(
      new ApiError(402, "Ліміт товарів вичерпано"),
    );

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-103");

    await openSheet("M");
    fireEvent.click(screen.getByLabelText("Збільшити залишок: SKU-103"));
    await screen.findByRole("button", { name: "Обрати тариф" });

    fireEvent.click(screen.getByRole("button", { name: "Обрати тариф" }));

    expect(await screen.findByText("Підписку призупинено")).toBeInTheDocument();
    expect(screen.getByText("Оформлення доступне лише власнику магазину.")).toBeInTheDocument();
    expect(screen.queryByText("Pro")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Оформити через Stars" })).not.toBeInTheDocument();
  });
});

describe("Promo code redemption (SubscriptionPaywall)", () => {
  async function goToSettings() {
    await screen.findByText("Тестовий магазин");
    fireEvent.click(screen.getByRole("tab", { name: "Налаштування" }));
  }

  async function openPaywall() {
    await goToSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Змінити тариф" }));
    await screen.findByRole("dialog", { name: "Оберіть тариф" });
  }

  it("redeeming a promo code closes the paywall, refetches the subscription, and shows a success banner", async () => {
    vi.mocked(api.getMe)
      .mockResolvedValueOnce(shopFixture)
      .mockResolvedValueOnce({ ...shopFixture, current_period_end: "2026-12-31T00:00:00Z" });
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getPlans).mockResolvedValue([planFixture]);
    vi.mocked(api.redeemPromo).mockResolvedValue({ current_period_end: "2026-12-31T00:00:00Z" });

    render(<App />);
    await openPaywall();

    fireEvent.change(screen.getByLabelText("Промокод"), { target: { value: "welcome60" } });
    fireEvent.click(screen.getByRole("button", { name: "Активувати" }));

    await waitFor(() => {
      expect(api.redeemPromo).toHaveBeenCalledWith("welcome60");
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Оберіть тариф" })).not.toBeInTheDocument();
    });
    expect(
      await screen.findByText(/Промокод застосовано до/),
    ).toBeInTheDocument();
    expect(api.getMe).toHaveBeenCalledTimes(2); // рефетч після успіху
  });

  it("shows an inline error from the backend when redeem fails, without closing the paywall", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getPlans).mockResolvedValue([planFixture]);
    vi.mocked(api.redeemPromo).mockRejectedValue(new ApiError(404, "Код не знайдено"));

    render(<App />);
    await openPaywall();

    fireEvent.change(screen.getByLabelText("Промокод"), { target: { value: "NOSUCH" } });
    fireEvent.click(screen.getByRole("button", { name: "Активувати" }));

    expect(await screen.findByText("Код не знайдено")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Оберіть тариф" })).toBeInTheDocument();
  });

  it("disables the Активувати button until a code is entered", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getPlans).mockResolvedValue([planFixture]);

    render(<App />);
    await openPaywall();

    expect(screen.getByRole("button", { name: "Активувати" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Промокод"), { target: { value: "X" } });
    expect(screen.getByRole("button", { name: "Активувати" })).not.toBeDisabled();
  });
});

describe("Frozen products", () => {
  it("renders frozen badge for a frozen product", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ id: 1, name: "Заморожений товар", is_frozen: true }),
    ]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Заморожений товар");

    expect(screen.getByText("Заморожено")).toBeInTheDocument();
  });

  it("clicking + on a frozen variant shows UpgradePrompt instead of calling restock", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 111, sku: "SKU-111" });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ is_frozen: true, variants: [variant] }),
    ]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    // Frozen product: modal opens (pencil does NOT block), frozen check is inside VariantSheet stepper
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-111");

    await openSheet("M");
    fireEvent.click(screen.getByLabelText("Збільшити залишок: SKU-111"));

    expect(
      await screen.findByText("Цей товар заморожено. Оформіть тариф, щоб редагувати."),
    ).toBeInTheDocument();
    expect(api.restock).not.toHaveBeenCalled();
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
    await goToSklad();
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
    await goToSklad();
    await screen.findByText("Демо товар");

    expect(screen.getByText(/Це приклади/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Очистити приклади" })).not.toBeInTheDocument();
  });
});

describe("Tab navigation", () => {
  it("renders Дашборд screen by default with MetricCarousel", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);

    await screen.findByText("Товари");
    expect(screen.getByRole("tab", { name: "Дашборд" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByLabelText("Пошук товарів")).not.toBeInTheDocument();
  });

  it("double-tap on a stat card: 1st tap selects it, 2nd tap navigates to Склад", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    const card = await screen.findByRole("button", { name: "Товари" });
    expect(card).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(card);
    expect(await screen.findByRole("button", { name: "Товари" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("tab", { name: "Дашборд" })).toHaveAttribute("aria-selected", "true");

    fireEvent.click(screen.getByRole("button", { name: "Товари" }));
    expect(screen.getByRole("tab", { name: "Склад" })).toHaveAttribute("aria-selected", "true");
  });

  // Framer layoutId переносить активну картку у featured-блок (окремий DOM-
  // вузол) і, поки виходить стара featured-картка, AnimatePresence лишає
  // ЇЇ в DOM на час exit-переходу (jsdom matchMedia завжди matches:false —
  // це реальна spring-анімація, а не миттєва; чекати завершення waitFor'ом
  // ненадійно, бо RAF-фізика springs у jsdom не гарантовано "доходить" за
  // фіксований таймаут). Тому шукаємо серед УСІХ збігів саме потрібний за
  // aria-pressed, а не покладаємось на єдиний матч.
  function statCard(name: string, pressed: "true" | "false") {
    return screen
      .getAllByRole("button", { name })
      .find((el) => el.getAttribute("aria-pressed") === pressed);
  }

  it("selecting a different stat card deselects the previous one", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await screen.findByRole("button", { name: "Товари" });

    fireEvent.click(statCard("Товари", "false")!);
    expect(statCard("Товари", "true")).toBeInTheDocument();

    fireEvent.click(statCard("Резерви", "false")!);
    expect(statCard("Товари", "false")).toBeInTheDocument();
    expect(statCard("Резерви", "true")).toBeInTheDocument();
  });

  it("tapping outside a stat card deselects it", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await screen.findByRole("button", { name: "Товари" });

    fireEvent.click(statCard("Товари", "false")!);
    expect(statCard("Товари", "true")).toBeInTheDocument();

    fireEvent.pointerDown(document.body);
    expect(statCard("Товари", "false")).toBeInTheDocument();
  });

  it("switches to Склад tab and shows search input and catalog section", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct()]);

    render(<App />);
    await screen.findByText("Тестовий магазин");

    fireEvent.click(screen.getByRole("tab", { name: "Склад" }));

    await screen.findByText("Футболка");
    expect(screen.getByLabelText("Пошук товарів")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Додати товар" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Склад" })).toHaveAttribute("aria-selected", "true");
  });

  it("switches to Налаштування tab and shows subscription info", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getPlans).mockResolvedValue([planFixture]);

    render(<App />);
    await screen.findByText("Тестовий магазин");

    fireEvent.click(screen.getByRole("tab", { name: "Налаштування" }));

    expect(screen.getByText("Підписка")).toBeInTheDocument();
    expect(screen.getByText("Зараз активний")).toBeInTheDocument();
    expect(screen.getByText("Pro")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Налаштування" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});

describe("Team section (Settings, owner-only)", () => {
  const ownerRoleFixture: Role = {
    id: 10, name: "Власник", is_system: true, members_count: 1,
    can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
    can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
  };
  const managerRoleFixture: Role = {
    id: 20, name: "Менеджер", is_system: true, members_count: 1,
    can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
    can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
  };

  async function goToSettings() {
    await screen.findByText("Тестовий магазин");
    fireEvent.click(screen.getByRole("tab", { name: "Налаштування" }));
  }

  it("is visible for owner", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await goToSettings();

    expect(await screen.findByText("Команда")).toBeInTheDocument();
  });

  it("is hidden for manager", async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...shopFixture, role: "manager" });
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await goToSettings();

    await screen.findByText("Підписка");
    expect(screen.queryByText("Команда")).not.toBeInTheDocument();
  });

  it("creates an invite and shows the url", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.createInvite).mockResolvedValue({
      id: 1,
      token: "tok-123",
      url: "https://t.me/sklad_base_bot?startapp=invite_tok-123",
      expires_at: new Date(Date.now() + 48 * 3600 * 1000).toISOString(),
    });

    render(<App />);
    await goToSettings();
    await screen.findByText("Команда");

    fireEvent.click(screen.getByRole("button", { name: "Запросити людину" }));

    await waitFor(() => {
      expect(api.createInvite).toHaveBeenCalled();
    });
    expect(
      await screen.findByDisplayValue("https://t.me/sklad_base_bot?startapp=invite_tok-123"),
    ).toBeInTheDocument();
  });

  it("revokes an invite via two-step confirm", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.listInvites).mockResolvedValue([
      {
        id: 42,
        token: "tok-42",
        url: "https://t.me/sklad_base_bot?startapp=invite_tok-42",
        expires_at: new Date(Date.now() + 47 * 3600 * 1000).toISOString(),
      },
    ]);
    vi.mocked(api.revokeInvite).mockResolvedValue(undefined);

    render(<App />);
    await goToSettings();
    await screen.findByText(/Діє ще/);

    fireEvent.click(screen.getByRole("button", { name: "Скасувати" }));
    fireEvent.click(screen.getByRole("button", { name: "Так, скасувати" }));

    await waitFor(() => {
      expect(api.revokeInvite).toHaveBeenCalledWith(42);
    });
  });

  it("removes a manager via two-step confirm", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 1, tg_id: 1001, display_name: "Дмитро", role: "owner",
        role_id: 10, role_name: "Власник",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
        overridden: [],
      },
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        role_id: 20, role_name: "Менеджер",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
        overridden: [],
      },
    ]);
    vi.mocked(api.removeMember).mockResolvedValue(undefined);

    render(<App />);
    await goToSettings();
    const managerRow = (await screen.findByText("Менеджер Іван")).closest("li");
    expect(managerRow).not.toBeNull();

    fireEvent.click(within(managerRow as HTMLElement).getByRole("button", { name: "Видалити" }));
    fireEvent.click(
      within(managerRow as HTMLElement).getByRole("button", { name: "Так, видалити" }),
    );

    await waitFor(() => {
      expect(api.removeMember).toHaveBeenCalledWith(2);
    });
  });

  it("does not show a delete button for the owner's own row", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 1, tg_id: 1001, display_name: "Дмитро", role: "owner",
        role_id: 10, role_name: "Власник",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
        overridden: [],
      },
    ]);

    render(<App />);
    await goToSettings();
    const ownerRow = (await screen.findByText("Дмитро")).closest("li");
    expect(ownerRow).not.toBeNull();

    expect(
      within(ownerRow as HTMLElement).queryByRole("button", { name: "Видалити" }),
    ).not.toBeInTheDocument();
  });

  it("shows 'повний доступ' for the owner instead of a role name", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 1, tg_id: 1001, display_name: "Дмитро", role: "owner",
        role_id: 10, role_name: "Власник",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
        overridden: [],
      },
    ]);

    render(<App />);
    await goToSettings();

    expect(await screen.findByText("повний доступ")).toBeInTheDocument();
  });

  it("does not expand a role selector for the owner's own row", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 1, tg_id: 1001, display_name: "Дмитро", role: "owner",
        role_id: 10, role_name: "Власник",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
        overridden: [],
      },
    ]);
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture]);

    render(<App />);
    await goToSettings();
    fireEvent.click(await screen.findByText("Дмитро"));

    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
    expect(api.setMemberRole).not.toHaveBeenCalled();
  });

  it("expands a role selector on tap and reassigns via PATCH", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const noFinanceRole: Role = {
      id: 30, name: "Без фінансів", is_system: false, members_count: 0,
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
    };
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        role_id: 20, role_name: "Менеджер",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
        overridden: [],
      },
    ]);
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture, noFinanceRole]);
    vi.mocked(api.setMemberRole).mockResolvedValue({
      id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
      role_id: 30, role_name: "Без фінансів",
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
      overridden: [],
    });

    render(<App />);
    await goToSettings();
    const managerRow = (await screen.findByText("Менеджер Іван")).closest("li");
    expect(managerRow).not.toBeNull();

    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Менеджер Іван"));

    const targetRoleRadio = within(managerRow as HTMLElement).getByLabelText("Без фінансів");
    fireEvent.click(targetRoleRadio);

    await waitFor(() => {
      expect(api.setMemberRole).toHaveBeenCalledWith(2, 30);
    });
  });

  it("rolls back the role selection when setMemberRole fails", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const noFinanceRole: Role = {
      id: 30, name: "Без фінансів", is_system: false, members_count: 0,
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
    };
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        role_id: 20, role_name: "Менеджер",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
        overridden: [],
      },
    ]);
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture, noFinanceRole]);
    vi.mocked(api.setMemberRole).mockRejectedValue(new ApiError(500, "боляче"));

    render(<App />);
    await goToSettings();
    fireEvent.click(await screen.findByText("Менеджер Іван"));

    const targetRoleRadio = screen.getByLabelText("Без фінансів") as HTMLInputElement;
    fireEvent.click(targetRoleRadio);
    expect(targetRoleRadio.checked).toBe(true);

    await waitFor(() => {
      expect(targetRoleRadio.checked).toBe(false);
    });
    expect(await screen.findByText("боляче")).toBeInTheDocument();
  });

  it("shows an override marker next to the member's name in the collapsed list", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        role_id: 20, role_name: "Менеджер",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
        overridden: ["can_view_finance"],
      },
      {
        id: 3, tg_id: 1003, display_name: "Менеджер Петро", role: "manager",
        role_id: 20, role_name: "Менеджер",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
        overridden: [],
      },
    ]);

    render(<App />);
    await goToSettings();

    const ivanRow = (await screen.findByText("Менеджер Іван")).closest("li") as HTMLElement;
    const petroRow = (await screen.findByText("Менеджер Петро")).closest("li") as HTMLElement;
    expect(within(ivanRow).getByLabelText("Змінені права")).toBeInTheDocument();
    expect(within(petroRow).queryByLabelText("Змінені права")).not.toBeInTheDocument();
  });

  it("highlights an overridden permission checkbox and lets others be toggled normally", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        role_id: 20, role_name: "Менеджер",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
        overridden: ["can_view_finance"],
      },
    ]);
    vi.mocked(api.patchMemberPermissions).mockResolvedValue({
      id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
      role_id: 20, role_name: "Менеджер",
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: false, can_manage_billing: false,
      overridden: ["can_view_finance", "can_manage_billing"],
    });

    render(<App />);
    await goToSettings();
    fireEvent.click(await screen.findByText("Менеджер Іван"));

    const financeCheckbox = screen.getByLabelText("Фінанси") as HTMLInputElement;
    expect(financeCheckbox.checked).toBe(false); // override, не роль (роль дозволяє)
    expect(screen.getByLabelText('Скинути "Фінанси" до ролі')).toBeInTheDocument();
    // Неторкнуте поле — без крапки override.
    expect(screen.queryByLabelText('Скинути "Оплата й тариф" до ролі')).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Оплата й тариф"));

    await waitFor(() => {
      expect(api.patchMemberPermissions).toHaveBeenCalledWith(2, { can_manage_billing: false });
    });
  });

  it("clicking the override dot resets that field to the role's value (PATCH null)", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        role_id: 20, role_name: "Менеджер",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
        overridden: ["can_view_finance"],
      },
    ]);
    vi.mocked(api.patchMemberPermissions).mockResolvedValue({
      id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
      role_id: 20, role_name: "Менеджер",
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
      overridden: [],
    });

    render(<App />);
    await goToSettings();
    fireEvent.click(await screen.findByText("Менеджер Іван"));

    fireEvent.click(screen.getByLabelText('Скинути "Фінанси" до ролі'));

    await waitFor(() => {
      expect(api.patchMemberPermissions).toHaveBeenCalledWith(2, { can_view_finance: null });
    });
    expect(await screen.findByLabelText("Фінанси")).toBeChecked();
    expect(screen.queryByLabelText('Скинути "Фінанси" до ролі')).not.toBeInTheDocument();
  });

  it("'Скинути до ролі' is visible only with overrides and resets all fields to null", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        role_id: 20, role_name: "Менеджер",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: false, can_manage_billing: false,
        overridden: ["can_view_finance", "can_manage_billing"],
      },
    ]);
    vi.mocked(api.patchMemberPermissions).mockResolvedValue({
      id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
      role_id: 20, role_name: "Менеджер",
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
      overridden: [],
    });

    render(<App />);
    await goToSettings();
    fireEvent.click(await screen.findByText("Менеджер Іван"));

    const resetButton = screen.getByRole("button", { name: "Скинути до ролі" });
    fireEvent.click(resetButton);

    await waitFor(() => {
      expect(api.patchMemberPermissions).toHaveBeenCalledWith(2, {
        can_view_inventory: null,
        can_edit_products: null,
        can_manage_reservations: null,
        can_manage_stock: null,
        can_view_finance: null,
        can_manage_billing: null,
      });
    });
    expect(
      await screen.findByRole("checkbox", { name: "Фінанси" }),
    ).toBeChecked();
    expect(screen.queryByRole("button", { name: "Скинути до ролі" })).not.toBeInTheDocument();
  });

  it("does not show 'Скинути до ролі' when the member has no overrides", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        role_id: 20, role_name: "Менеджер",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
        overridden: [],
      },
    ]);

    render(<App />);
    await goToSettings();
    fireEvent.click(await screen.findByText("Менеджер Іван"));

    expect(screen.queryByRole("button", { name: "Скинути до ролі" })).not.toBeInTheDocument();
  });

  it("asks for confirmation before changing role when the member has overrides", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const noFinanceRole: Role = {
      id: 30, name: "Без фінансів", is_system: false, members_count: 0,
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
    };
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture, noFinanceRole]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        role_id: 20, role_name: "Менеджер",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
        overridden: ["can_view_finance"],
      },
    ]);
    vi.mocked(api.setMemberRole).mockResolvedValue({
      id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
      role_id: 30, role_name: "Без фінансів",
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
      overridden: [],
    });

    render(<App />);
    await goToSettings();
    fireEvent.click(await screen.findByText("Менеджер Іван"));

    fireEvent.click(screen.getByLabelText("Без фінансів"));

    expect(screen.getByText("Індивідуальні права буде скинуто")).toBeInTheDocument();
    expect(api.setMemberRole).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Так, змінити" }));

    await waitFor(() => {
      expect(api.setMemberRole).toHaveBeenCalledWith(2, 30);
    });
  });

  it("cancelling the role-change confirmation does not call the API", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const noFinanceRole: Role = {
      id: 30, name: "Без фінансів", is_system: false, members_count: 0,
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
    };
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture, noFinanceRole]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        role_id: 20, role_name: "Менеджер",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
        overridden: ["can_view_finance"],
      },
    ]);

    render(<App />);
    await goToSettings();
    fireEvent.click(await screen.findByText("Менеджер Іван"));

    fireEvent.click(screen.getByLabelText("Без фінансів"));
    fireEvent.click(screen.getByRole("button", { name: "Скасувати" }));

    expect(screen.queryByText("Індивідуальні права буде скинуто")).not.toBeInTheDocument();
    expect(api.setMemberRole).not.toHaveBeenCalled();
    // Радіо лишається на попередній ролі — зміна не відбулась.
    expect((screen.getByLabelText("Менеджер") as HTMLInputElement).checked).toBe(true);
  });

  it("renders the roles list with member counts and a system badge", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getRoles).mockResolvedValue([
      { ...ownerRoleFixture, members_count: 1 },
      { ...managerRoleFixture, members_count: 2 },
    ]);

    render(<App />);
    await goToSettings();

    expect(await screen.findByText("Власник")).toBeInTheDocument();
    expect(screen.getByText("1 учасник")).toBeInTheDocument();
    expect(screen.getByText("2 учасники")).toBeInTheDocument();
    expect(screen.getAllByText("системна")).toHaveLength(2);
  });

  it("creates a custom role via the create-role form", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture]);
    vi.mocked(api.createRole).mockResolvedValue({
      id: 30, name: "Продавець", is_system: false, members_count: 0,
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
    });

    render(<App />);
    await goToSettings();
    await screen.findByText("Ролі");

    fireEvent.click(screen.getByRole("button", { name: "+ Створити роль" }));
    fireEvent.change(screen.getByLabelText("Назва нової ролі"), {
      target: { value: "Продавець" },
    });
    fireEvent.click(screen.getByLabelText("Фінанси"));
    fireEvent.click(screen.getByRole("button", { name: "Створити" }));

    await waitFor(() => {
      expect(api.createRole).toHaveBeenCalledWith({
        name: "Продавець",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
      });
    });
    expect(await screen.findByText("Продавець")).toBeInTheDocument();
  });

  it("shows an inline message when creating a role with a duplicate name (409)", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture]);
    vi.mocked(api.createRole).mockRejectedValue(
      new ApiError(409, "роль з такою назвою вже існує"),
    );

    render(<App />);
    await goToSettings();
    await screen.findByText("Ролі");

    fireEvent.click(screen.getByRole("button", { name: "+ Створити роль" }));
    fireEvent.change(screen.getByLabelText("Назва нової ролі"), {
      target: { value: "Менеджер" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Створити" }));

    expect(await screen.findByText("Роль з такою назвою вже є")).toBeInTheDocument();
  });

  it("does not expand the Власник role for editing, and shows a self-dismissing hint instead", async () => {
    // Розворот рішення (фіча 3c): "Менеджер" — теж is_system, але тепер
    // редагується як звичайна кастомна роль. Незмінна лишається тільки
    // "Власник" — саме на ній тепер тост.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture]);

    render(<App />);
    await goToSettings();
    fireEvent.click(await screen.findByText("Власник"));

    expect(screen.queryByLabelText(/Назва ролі/)).not.toBeInTheDocument();
    expect(api.patchRole).not.toHaveBeenCalled();
    expect(screen.getByText("Роль власника завжди має всі права")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.queryByText("Роль власника завжди має всі права")).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  it("dismisses the owner-role hint immediately when tapped", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture]);

    render(<App />);
    await goToSettings();
    fireEvent.click(await screen.findByText("Власник"));

    const hint = screen.getByText("Роль власника завжди має всі права");
    fireEvent.click(screen.getByRole("button", { name: "Закрити" }));
    expect(hint).not.toBeInTheDocument();
  });

  it("expands the Менеджер role for editing like a custom role (badge stays, just not locked)", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture]);
    vi.mocked(api.patchRole).mockResolvedValue({ ...managerRoleFixture, can_view_finance: false });

    render(<App />);
    await goToSettings();
    const roleRow = (await screen.findByText("Менеджер")).closest("li");
    expect(roleRow).not.toBeNull();

    fireEvent.click(screen.getByText("Менеджер"));

    expect(within(roleRow as HTMLElement).getByText("системна")).toBeInTheDocument();
    expect(screen.queryByText("Роль власника завжди має всі права")).not.toBeInTheDocument();
    const financeCheckbox = within(roleRow as HTMLElement).getByLabelText("Фінанси");
    fireEvent.click(financeCheckbox);

    await waitFor(() => {
      expect(api.patchRole).toHaveBeenCalledWith(managerRoleFixture.id, { can_view_finance: false });
    });
    // "Менеджер" — все одно системна, тож без кнопки видалення.
    expect(
      within(roleRow as HTMLElement).queryByRole("button", { name: "Видалити роль" }),
    ).not.toBeInTheDocument();
  });

  it("edits a custom role's permissions via checkbox PATCH", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const customRole: Role = {
      id: 30, name: "Продавець", is_system: false, members_count: 0,
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
    };
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture, customRole]);
    vi.mocked(api.patchRole).mockResolvedValue({ ...customRole, can_view_finance: false });

    render(<App />);
    await goToSettings();
    const roleRow = (await screen.findByText("Продавець")).closest("li");
    expect(roleRow).not.toBeNull();

    fireEvent.click(screen.getByText("Продавець"));
    const financeCheckbox = within(roleRow as HTMLElement).getByLabelText("Фінанси");
    fireEvent.click(financeCheckbox);

    await waitFor(() => {
      expect(api.patchRole).toHaveBeenCalledWith(30, { can_view_finance: false });
    });
  });

  it("expands and collapses a custom role by clicking the row container itself", async () => {
    // Regression: the row's onClick used to nest a second setState call
    // (setRoleNameDraft) inside setExpandedRoleId's functional updater. React
    // requires updater functions to stay pure — it may invoke them more than
    // once per commit — so this only misbehaved intermittently on real
    // devices, never in a fast synchronous test. Click the actual clickable
    // container (role="button"), not the inner <p>, to match how a real tap
    // hits the DOM.
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const customRole: Role = {
      id: 30, name: "Продавець", is_system: false, members_count: 0,
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
    };
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture, customRole]);

    render(<App />);
    await goToSettings();
    const nameNode = await screen.findByText("Продавець");
    const rowContainer = nameNode.closest('[role="button"]');
    expect(rowContainer).not.toBeNull();

    expect(screen.queryByLabelText(/Назва ролі/)).not.toBeInTheDocument();

    fireEvent.click(rowContainer as HTMLElement);
    expect(await screen.findByLabelText("Назва ролі: Продавець")).toBeInTheDocument();

    fireEvent.click(rowContainer as HTMLElement);
    // Розгортка тепер закривається через AnimatePresence exit-анімацію
    // (скрол-згортання, фіча 3d) — елемент лишається в DOM до кінця
    // transition, тож перевіряємо асинхронно, не одразу.
    await waitFor(() => {
      expect(screen.queryByLabelText(/Назва ролі/)).not.toBeInTheDocument();
    });
  });

  it("opening a second expandable row closes the first — one accordion for roles AND members", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const roleA: Role = {
      id: 30, name: "Роль А", is_system: false, members_count: 0,
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
    };
    const roleB: Role = {
      id: 31, name: "Роль Б", is_system: false, members_count: 0,
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
    };
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture, roleA, roleB]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        role_id: 20, role_name: "Менеджер",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
        overridden: [],
      },
    ]);

    render(<App />);
    await goToSettings();

    // Капчуримо самі клікабельні рядки один раз — після відкриття члена
    // команди назва "Роль А" з'являється ВДРУГЕ (у радіогрупі вибору ролі),
    // тож повторний пошук по тексту після цього був би неоднозначним.
    const roleARow = (await screen.findByText("Роль А")).closest('[role="button"]') as HTMLElement;
    const roleBRow = screen.getByText("Роль Б").closest('[role="button"]') as HTMLElement;

    // Роль А, потім роль Б — А закривається.
    fireEvent.click(roleARow);
    expect(await screen.findByLabelText("Назва ролі: Роль А")).toBeInTheDocument();

    fireEvent.click(roleBRow);
    expect(await screen.findByLabelText("Назва ролі: Роль Б")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByLabelText("Назва ролі: Роль А")).not.toBeInTheDocument();
    });

    // Тепер відкриваємо члена команди — роль Б закривається (один акордеон
    // на розгортки ролей І членів разом).
    fireEvent.click(screen.getByText("Менеджер Іван"));
    expect(await screen.findByRole("radiogroup")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByLabelText("Назва ролі: Роль Б")).not.toBeInTheDocument();
    });

    // І назад: відкриття ролі закриває розгортку члена.
    fireEvent.click(roleARow);
    expect(await screen.findByLabelText("Назва ролі: Роль А")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
    });
  });

  it("closes an expanded role panel when it scrolls fully out of view, but not while partially visible", async () => {
    // Контрольований IntersectionObserver: тест сам вирішує, коли "викликати"
    // callback з isIntersecting true/false, замість реального скролу
    // (jsdom його не рахує).
    let observedCallback: IntersectionObserverCallback | null = null;
    const observe = vi.fn();
    const disconnect = vi.fn();
    class ControlledIntersectionObserver implements IntersectionObserver {
      readonly root: Element | Document | null = null;
      readonly rootMargin = "";
      readonly scrollMargin = "";
      readonly thresholds: ReadonlyArray<number> = [];
      constructor(callback: IntersectionObserverCallback) {
        observedCallback = callback;
      }
      observe = observe;
      unobserve = vi.fn();
      disconnect = disconnect;
      takeRecords = () => [];
    }
    const OriginalIntersectionObserver = window.IntersectionObserver;
    window.IntersectionObserver = ControlledIntersectionObserver as unknown as typeof IntersectionObserver;

    try {
      vi.mocked(api.getMe).mockResolvedValue(shopFixture);
      vi.mocked(api.getProducts).mockResolvedValue([]);
      const customRole: Role = {
        id: 30, name: "Продавець", is_system: false, members_count: 0,
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
      };
      vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture, customRole]);

      render(<App />);
      await goToSettings();
      fireEvent.click(await screen.findByText("Продавець"));
      expect(await screen.findByLabelText("Назва ролі: Продавець")).toBeInTheDocument();

      expect(observe).toHaveBeenCalled();
      expect(observedCallback).not.toBeNull();

      // Частково видима — НЕ закриваємо (інакше зникло б "під пальцем").
      observedCallback!(
        [{ isIntersecting: true } as IntersectionObserverEntry],
        {} as IntersectionObserver,
      );
      expect(screen.getByLabelText("Назва ролі: Продавець")).toBeInTheDocument();

      // Повністю за межами скрол-контейнера — закриваємо.
      observedCallback!(
        [{ isIntersecting: false } as IntersectionObserverEntry],
        {} as IntersectionObserver,
      );
      await waitFor(() => {
        expect(screen.queryByLabelText("Назва ролі: Продавець")).not.toBeInTheDocument();
      });
    } finally {
      window.IntersectionObserver = OriginalIntersectionObserver;
    }
  });

  it("deletes a role without holders via two-step confirm", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const customRole: Role = {
      id: 30, name: "Порожня роль", is_system: false, members_count: 0,
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
    };
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture, customRole]);
    vi.mocked(api.deleteRole).mockResolvedValue(undefined);

    render(<App />);
    await goToSettings();
    const roleRow = (await screen.findByText("Порожня роль")).closest("li");
    expect(roleRow).not.toBeNull();

    fireEvent.click(screen.getByText("Порожня роль"));
    fireEvent.click(within(roleRow as HTMLElement).getByRole("button", { name: "Видалити роль" }));
    fireEvent.click(
      within(roleRow as HTMLElement).getByRole("button", { name: "Так, видалити" }),
    );

    await waitFor(() => {
      expect(api.deleteRole).toHaveBeenCalledWith(30);
    });
  });

  it("shows the backend's 409 message when deleting a role that has holders", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const customRole: Role = {
      id: 30, name: "Роль з носієм", is_system: false, members_count: 1,
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
    };
    vi.mocked(api.getRoles).mockResolvedValue([ownerRoleFixture, managerRoleFixture, customRole]);
    vi.mocked(api.deleteRole).mockRejectedValue(
      new ApiError(409, "Спершу переведіть учасників на іншу роль"),
    );

    render(<App />);
    await goToSettings();
    const roleRow = (await screen.findByText("Роль з носієм")).closest("li");
    expect(roleRow).not.toBeNull();

    fireEvent.click(screen.getByText("Роль з носієм"));
    fireEvent.click(within(roleRow as HTMLElement).getByRole("button", { name: "Видалити роль" }));
    fireEvent.click(
      within(roleRow as HTMLElement).getByRole("button", { name: "Так, видалити" }),
    );

    expect(
      await screen.findByText("Спершу переведіть учасників на іншу роль"),
    ).toBeInTheDocument();
  });
});

describe("Nova Poshta key section (Settings, owner-only)", () => {
  async function goToSettings() {
    await screen.findByText("Тестовий магазин");
    fireEvent.click(screen.getByRole("tab", { name: "Налаштування" }));
  }

  it("is visible for owner", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await goToSettings();

    expect(await screen.findByText("Нова Пошта")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Підключити" })).toBeInTheDocument();
  });

  it("is hidden for manager", async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...shopFixture, role: "manager" });
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await goToSettings();

    await screen.findByText("Підписка");
    expect(screen.queryByText("Нова Пошта")).not.toBeInTheDocument();
  });

  it("connects a valid key and shows the connected badge", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.putNpKey).mockResolvedValue({ connected: true });

    render(<App />);
    await goToSettings();
    await screen.findByText("Нова Пошта");

    fireEvent.change(screen.getByLabelText("API-ключ"), {
      target: { value: "np-live-key-123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Підключити" }));

    await waitFor(() => {
      expect(api.putNpKey).toHaveBeenCalledWith("np-live-key-123");
    });
    expect(await screen.findByText("Підключено ✅")).toBeInTheDocument();
    expect(
      screen.getByText("Статуси відправлень оновлюються автоматично кожні 10 хв"),
    ).toBeInTheDocument();
  });

  it("shows an inline error when the key fails validation (422)", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.putNpKey).mockRejectedValue(
      new api.ApiError(422, "Ключ не пройшов перевірку"),
    );

    render(<App />);
    await goToSettings();
    await screen.findByText("Нова Пошта");

    fireEvent.change(screen.getByLabelText("API-ключ"), { target: { value: "bad-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Підключити" }));

    expect(await screen.findByText("Ключ не пройшов перевірку")).toBeInTheDocument();
    expect(screen.queryByText("Підключено ✅")).not.toBeInTheDocument();
  });

  it("shows the disconnect flow when already connected", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getNpStatus).mockResolvedValue({ connected: true });
    vi.mocked(api.deleteNpKey).mockResolvedValue(undefined);

    render(<App />);
    await goToSettings();

    expect(await screen.findByText("Підключено ✅")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Відключити" }));
    fireEvent.click(screen.getByRole("button", { name: "Так, відключити" }));

    await waitFor(() => {
      expect(api.deleteNpKey).toHaveBeenCalled();
    });
    expect(await screen.findByRole("button", { name: "Підключити" })).toBeInTheDocument();
  });
});

describe("invite_status banner", () => {
  it("shows a success banner when invite_status is joined", async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...shopFixture, invite_status: "joined" });
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);

    expect(
      await screen.findByText("Вітаємо! Ви приєднались до магазину Тестовий магазин"),
    ).toBeInTheDocument();
  });

  it("shows a neutral banner when invite_status is already_member", async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...shopFixture, invite_status: "already_member" });
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);

    expect(
      await screen.findByText("Ви вже маєте магазин — запрошення не застосовано"),
    ).toBeInTheDocument();
  });

  it("shows a warning banner when invite_status is invite_invalid", async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...shopFixture, invite_status: "invite_invalid" });
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);

    expect(
      await screen.findByText("Запрошення недійсне або прострочене. Створено ваш власний магазин."),
    ).toBeInTheDocument();
  });

  it("shows a neutral banner when invite_status is already_in_shop", async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...shopFixture, invite_status: "already_in_shop" });
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);

    expect(await screen.findByText("Ви вже учасник цього магазину")).toBeInTheDocument();
  });

  it("shows no banner when invite_status is null", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await screen.findByText("Тестовий магазин");

    expect(screen.queryByText(/приєднались|запрошення|учасник/i)).not.toBeInTheDocument();
  });

  it("dismisses the banner on click", async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...shopFixture, invite_status: "already_member" });
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    const message = await screen.findByText("Ви вже маєте магазин — запрошення не застосовано");

    fireEvent.click(screen.getByRole("button", { name: "Закрити" }));

    expect(message).not.toBeInTheDocument();
  });
});

describe("Shop switcher (multi-shop, Стадія 3б)", () => {
  const shopBSummary = { shop_id: 2, shop_name: "Другий магазин", logo_url: null, role: "manager" as const };
  const multiShopFixture: Shop = {
    ...shopFixture,
    shops: [
      { shop_id: 1, shop_name: "Тестовий магазин", logo_url: null, role: "owner" as const },
      shopBSummary,
    ],
  };
  const shopBActiveFixture: Shop = {
    ...multiShopFixture,
    shop_id: 2,
    shop_name: "Другий магазин",
    active_shop_id: 2,
  };

  it("shows no switcher when the user has only one shop", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await screen.findByText("Тестовий магазин");

    expect(screen.queryByRole("button", { name: /Тестовий магазин/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("opens the switcher list when tapping the shop name with multiple shops", async () => {
    vi.mocked(api.getMe).mockResolvedValue(multiShopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    const nameButton = await screen.findByRole("button", { name: /Тестовий магазин/ });

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    fireEvent.click(nameButton);

    expect(screen.getByRole("listbox")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Другий магазин/ })).toBeInTheDocument();
  });

  it("selecting a shop calls setActiveShopId and refetches", async () => {
    vi.mocked(api.getMe).mockResolvedValueOnce(multiShopFixture).mockResolvedValue(
      shopBActiveFixture,
    );
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    const nameButton = await screen.findByRole("button", { name: /Тестовий магазин/ });
    fireEvent.click(nameButton);
    fireEvent.click(screen.getByRole("option", { name: /Другий магазин/ }));

    await waitFor(() => {
      expect(api.setActiveShopId).toHaveBeenCalledWith(2);
    });
    expect(await screen.findByText("Другий магазин")).toBeInTheDocument();
    expect(api.getProducts).toHaveBeenCalledTimes(2);
  });

  it("restores a persisted shop selection if still a member", async () => {
    localStorage.setItem("skladbase:activeShopId", "2");
    vi.mocked(api.getMe).mockResolvedValueOnce(multiShopFixture).mockResolvedValueOnce(
      shopBActiveFixture,
    );
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);

    expect(await screen.findByText("Другий магазин")).toBeInTheDocument();
    expect(api.setActiveShopId).toHaveBeenCalledWith(2);
  });

  it("ignores a persisted shop id that is no longer a membership", async () => {
    localStorage.setItem("skladbase:activeShopId", "999");
    vi.mocked(api.getMe).mockResolvedValue(multiShopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);

    expect(await screen.findByText("Тестовий магазин")).toBeInTheDocument();
    expect(api.getMe).toHaveBeenCalledTimes(1);
  });
});

describe("Variant CRUD in modal (tag → sheet)", () => {
  it("edit variant: tap tag → sheet → change price → Зберегти → patchVariant called", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 201, sku: "SKU-201", price: "450.00" });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.patchVariant).mockResolvedValue({ ...variant, price: "500" });

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");

    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-201");

    await openSheet("M");
    fireEvent.change(screen.getByLabelText("Ціна"), { target: { value: "500" } });
    fireEvent.click(screen.getByRole("button", { name: "Зберегти" }));

    await waitFor(() => {
      expect(api.patchVariant).toHaveBeenCalledWith(201, expect.objectContaining({ price: "500" }));
    });
  });

  it("add variant: '+ Додати варіант' calls addVariant with last price, no sku", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 202, sku: "SKU-202", price: "450.00", axis_values: { size: "M" } });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ id: 1, variants: [variant] })]);
    vi.mocked(api.addVariant).mockResolvedValue(makeVariant({ id: 203, sku: null, price: "450.00" }));

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");

    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-202");

    fireEvent.click(screen.getByRole("button", { name: "+ Додати варіант" }));

    await waitFor(() => {
      expect(api.addVariant).toHaveBeenCalled();
    });

    const [calledProductId, calledPayload] = vi.mocked(api.addVariant).mock.calls[0];
    expect(calledProductId).toBe(1);
    expect(calledPayload.price).toBe("450.00");
    expect(calledPayload).not.toHaveProperty("sku");
  });

  it("add variant 402 shows UpgradePrompt instead of a silent failure", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 210, sku: "SKU-210" });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ id: 1, variants: [variant] })]);
    vi.mocked(api.addVariant).mockRejectedValue(new ApiError(402, "Ліміт плану вичерпано"));

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");

    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-210");

    fireEvent.click(screen.getByRole("button", { name: "+ Додати варіант" }));

    expect(await screen.findByText("Ліміт плану вичерпано")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Обрати тариф" })).toBeInTheDocument();
  });

  it("'+ Додати варіант' on a frozen product shows UpgradePrompt without calling addVariant", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 211, sku: "SKU-211" });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ id: 1, is_frozen: true, variants: [variant] }),
    ]);

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");

    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-211");

    fireEvent.click(screen.getByRole("button", { name: "+ Додати варіант" }));

    expect(
      await screen.findByText("Цей товар заморожено. Оформіть тариф, щоб редагувати."),
    ).toBeInTheDocument();
    expect(api.addVariant).not.toHaveBeenCalled();
  });

  it("patch variant 402 shows UpgradePrompt, not the sheet's generic error banner", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 212, sku: "SKU-212", price: "450.00" });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.patchVariant).mockRejectedValue(new ApiError(402, "Товар заморожено"));

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");

    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-212");

    await openSheet("M");
    fireEvent.change(screen.getByLabelText("Ціна"), { target: { value: "500" } });
    fireEvent.click(screen.getByRole("button", { name: "Зберегти" }));

    expect(await screen.findByText("Товар заморожено")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Обрати тариф" })).toBeInTheDocument();
    expect(screen.queryByText("Не вдалося зберегти варіант")).not.toBeInTheDocument();
  });

  it("delete variant 402 shows UpgradePrompt, not the sheet's generic error banner", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 213, sku: "SKU-213" });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.deleteVariant).mockRejectedValue(new ApiError(402, "Товар заморожено"));

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");

    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-213");

    await openSheet("M");
    fireEvent.click(screen.getByRole("button", { name: "Видалити варіант" }));
    fireEvent.click(screen.getByRole("button", { name: "Так, видалити" }));

    expect(await screen.findByText("Товар заморожено")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Обрати тариф" })).toBeInTheDocument();
    expect(screen.queryByText("Не вдалося видалити варіант")).not.toBeInTheDocument();
  });

  it("delete variant: tag → sheet → Видалити → Так → deleteVariant called", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 204, sku: "SKU-204" });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.deleteVariant).mockResolvedValue(undefined);

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");

    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-204");

    await openSheet("M");
    fireEvent.click(screen.getByRole("button", { name: "Видалити варіант" }));
    fireEvent.click(screen.getByRole("button", { name: "Так, видалити" }));

    await waitFor(() => {
      expect(api.deleteVariant).toHaveBeenCalledWith(204);
    });
  });

  it("409 on delete shows inline error banner in the sheet", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 205, sku: "SKU-205" });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.deleteVariant).mockRejectedValue(
      new ApiError(409, "Неможливо видалити останній варіант"),
    );

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");

    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-205");

    await openSheet("M");
    fireEvent.click(screen.getByRole("button", { name: "Видалити варіант" }));
    fireEvent.click(screen.getByRole("button", { name: "Так, видалити" }));

    expect(
      await screen.findByText("Неможливо видалити останній варіант"),
    ).toBeInTheDocument();
    expect(api.deleteVariant).toHaveBeenCalledWith(205);
  });

  it("write-off dialog: 409 (more than available) shows inline error banner", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({ id: 206, sku: "SKU-206", on_hand: 5, available: 5 });
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ variants: [variant] })]);
    vi.mocked(api.adjust).mockRejectedValue(
      new ApiError(409, "Недостатньо доступного залишку"),
    );

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-206");

    await openSheet("M");
    fireEvent.click(screen.getByLabelText("Зменшити залишок: SKU-206"));

    fireEvent.change(screen.getByLabelText("Кількість (доступно 5)"), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByText("💰 Продано"));
    fireEvent.click(screen.getByText("Списати"));

    expect(await screen.findByText("Недостатньо доступного залишку")).toBeInTheDocument();
  });
});

describe("Edit-mode Info tab: template attributes", () => {
  it("renders attribute fields seeded from product.attributes and saves changes via PATCH", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getTemplates).mockResolvedValue([clothingTemplate]);
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({
        template_id: clothingTemplate.id,
        attributes: { product_type: "Худі", material: "Бавовна" },
      }),
    ]);
    vi.mocked(api.updateProduct).mockResolvedValue(
      makeProduct({
        template_id: clothingTemplate.id,
        attributes: { product_type: "Футболка", material: "Бавовна" },
      }),
    );

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");

    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    fireEvent.click(screen.getByRole("tab", { name: "Інфо" }));

    const typeSelect = screen.getByLabelText("Тип") as HTMLSelectElement;
    const materialInput = screen.getByLabelText("Матеріал") as HTMLInputElement;
    expect(typeSelect.value).toBe("Худі");
    expect(materialInput.value).toBe("Бавовна");

    fireEvent.change(typeSelect, { target: { value: "Футболка" } });
    fireEvent.click(screen.getByRole("button", { name: "Зберегти" }));

    await waitFor(() => {
      expect(api.updateProduct).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          attributes: { product_type: "Футболка", material: "Бавовна" },
        }),
      );
    });
  });
});

describe("Finance summary (Dashboard)", () => {
  it("renders revenue, sales count and units sold from the finance summary", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(
      makeFinance({ revenue_uah: "450.00", sales_count: 2, units_sold: 3 }),
    );

    render(<App />);

    expect(await screen.findByText("Дохід")).toBeInTheDocument();
    expect(screen.getByText("2 · 3")).toBeInTheDocument();
  });

  it("shows the empty-period message instead of bare zeros when there are no sales", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(makeFinance());

    render(<App />);

    expect(await screen.findByText("Немає продажів за цей період")).toBeInTheDocument();
    expect(screen.queryByText("Дохід")).not.toBeInTheDocument();
  });

  it("switching the period chip refetches the summary with the chosen period", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(makeFinance());

    render(<App />);
    await screen.findByText("Фінанси");

    fireEvent.click(screen.getByRole("button", { name: "Тиждень" }));

    await waitFor(() => {
      expect(api.getFinanceSummary).toHaveBeenLastCalledWith("week");
    });

    fireEvent.click(screen.getByRole("button", { name: "Рік" }));
    await waitFor(() => {
      expect(api.getFinanceSummary).toHaveBeenLastCalledWith("year");
    });
  });

  it("renders revenue bars for each day in the chart", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const today = new Date().toISOString().slice(0, 10);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(
      makeFinance({
        revenue_uah: "100.00",
        sales_count: 1,
        units_sold: 1,
        chart: [{ date: today, revenue: "100.00", units: 1 }],
      }),
    );

    render(<App />);

    expect(await screen.findByRole("img", { name: "Графік доходу за період" })).toBeInTheDocument();
    const bars = document.querySelectorAll(".revenue-chart-bar");
    expect(bars.length).toBeGreaterThan(0);
  });

  it("chart tooltip shows units sold alongside revenue", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const today = new Date().toISOString().slice(0, 10);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(
      makeFinance({
        revenue_uah: "300.00",
        sales_count: 2,
        units_sold: 3,
        chart: [{ date: today, revenue: "300.00", units: 3 }],
      }),
    );

    render(<App />);
    await screen.findByText("Фінанси");
    fireEvent.click(screen.getByRole("button", { name: "Тиждень" })); // денні бакети
    await screen.findByRole("img", { name: "Графік доходу за період" });

    const bars = document.querySelectorAll(".revenue-chart-bar");
    fireEvent.mouseEnter(bars[bars.length - 1]);

    expect(await screen.findByText(/продано 3 шт/)).toBeInTheDocument();
  });

  it("double-tapping the same daily bar opens History filtered to that date", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const today = new Date().toISOString().slice(0, 10);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(
      makeFinance({ sales_count: 1, chart: [{ date: today, revenue: "100.00", units: 1 }] }),
    );

    render(<App />);
    await screen.findByText("Фінанси");
    fireEvent.click(screen.getByRole("button", { name: "Тиждень" })); // денні бакети
    await screen.findByRole("img", { name: "Графік доходу за період" });

    const bars = document.querySelectorAll(".revenue-chart-bar");
    const todayBar = bars[bars.length - 1];
    fireEvent.click(todayBar);
    fireEvent.click(todayBar);

    await screen.findByRole("dialog", { name: "Історія" });
    await waitFor(() => {
      expect(api.getFinanceHistory).toHaveBeenCalledWith("week", today);
    });
  });

  it("a single tap on a bar does not open History", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const today = new Date().toISOString().slice(0, 10);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(
      makeFinance({ sales_count: 1, chart: [{ date: today, revenue: "100.00", units: 1 }] }),
    );

    render(<App />);
    await screen.findByText("Фінанси");
    await screen.findByRole("img", { name: "Графік доходу за період" });

    const bars = document.querySelectorAll(".revenue-chart-bar");
    fireEvent.click(bars[bars.length - 1]);

    expect(screen.queryByRole("dialog", { name: "Історія" })).not.toBeInTheDocument();
  });

  it("'Історія' button opens History without a date filter", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);

    render(<App />);
    await screen.findByText("Фінанси");
    fireEvent.click(screen.getByRole("button", { name: "Історія" }));

    await screen.findByRole("dialog", { name: "Історія" });
    await waitFor(() => {
      expect(api.getFinanceHistory).toHaveBeenCalledWith("all", undefined);
    });
  });

  it("History sheet renders an event row with product/variant/qty/amount", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getFinanceHistory).mockResolvedValue([
      makeHistoryEvent({ product_name: "Сукня", variant_label: "M", qty: 2, amount: "900.00" }),
    ]);

    render(<App />);
    await screen.findByText("Фінанси");
    fireEvent.click(screen.getByRole("button", { name: "Історія" }));

    expect(await screen.findByText(/Сукня.*M.*2 шт/)).toBeInTheDocument();
    expect(screen.getByText(/900.00 ₴/)).toBeInTheDocument();
  });

  it("History sheet shows a colored event-type badge and resolves the product photo/chip", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({
        id: 1,
        name: "Футболка",
        photos: [{ id: 1, url: "https://cdn.example.test/tshirt.webp", position: 0 }],
      }),
    ]);
    vi.mocked(api.getFinanceHistory).mockResolvedValue([
      makeHistoryEvent({ id: 1, type: "sale", product_name: "Футболка" }),
      makeHistoryEvent({ id: 2, type: "return", product_name: "Футболка" }),
      makeHistoryEvent({ id: 3, type: "release", product_name: "Невідомий товар" }),
    ]);

    render(<App />);
    await screen.findByText("Фінанси");
    fireEvent.click(screen.getByRole("button", { name: "Історія" }));

    expect(await screen.findByText("Продано")).toHaveClass("badge-event-sale");
    expect(screen.getByText("Повернено")).toHaveClass("badge-event-return");
    expect(screen.getByText("Знято")).toHaveClass("badge-event-release");

    // HistorySheet рендериться через createPortal у document.body — RTL's
    // container його не бачить, шукаємо напряму по document.
    const photoImg = document.querySelector<HTMLImageElement>("img.history-row-photo");
    expect(photoImg?.src).toBe("https://cdn.example.test/tshirt.webp");
    expect(screen.getByText("Н")).toHaveClass("history-row-photo--neutral");
  });

  it("History sheet shows 'Немає подій' when there are none", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getFinanceHistory).mockResolvedValue([]);

    render(<App />);
    await screen.findByText("Фінанси");
    fireEvent.click(screen.getByRole("button", { name: "Історія" }));

    expect(await screen.findByText("Немає подій")).toBeInTheDocument();
  });

  it("'Показати всі дати' clears the day filter and refetches without date", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    const today = new Date().toISOString().slice(0, 10);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(
      makeFinance({ sales_count: 1, chart: [{ date: today, revenue: "100.00", units: 1 }] }),
    );
    vi.mocked(api.getFinanceHistory).mockResolvedValue([]);

    render(<App />);
    await screen.findByText("Фінанси");
    fireEvent.click(screen.getByRole("button", { name: "Тиждень" }));
    await screen.findByRole("img", { name: "Графік доходу за період" });

    const bars = document.querySelectorAll(".revenue-chart-bar");
    const todayBar = bars[bars.length - 1];
    fireEvent.click(todayBar);
    fireEvent.click(todayBar);
    await screen.findByRole("dialog", { name: "Історія" });

    fireEvent.click(await screen.findByRole("button", { name: "Показати всі дати" }));

    await waitFor(() => {
      expect(api.getFinanceHistory).toHaveBeenLastCalledWith("week", undefined);
    });
  });

  it("renders the top products list sorted by revenue", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(
      makeFinance({
        revenue_uah: "700.00",
        sales_count: 2,
        units_sold: 4,
        top_products: [
          { product_id: 1, name: "Кепка", revenue_uah: "500.00", units: 1 },
          { product_id: 2, name: "Футболка", revenue_uah: "200.00", units: 3 },
        ],
      }),
    );

    render(<App />);

    expect(await screen.findByText("Топ товарів")).toBeInTheDocument();
    expect(screen.getByText("Кепка")).toBeInTheDocument();
    expect(screen.getByText("Футболка")).toBeInTheDocument();
  });

  it("renders release/return reasons with human-readable labels, only when present", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(
      makeFinance({
        release_reasons: [{ reason: "customer_changed_mind", count: 2 }],
      }),
    );

    render(<App />);

    expect(await screen.findByText("Зняття резервів")).toBeInTheDocument();
    expect(screen.getByText("Клієнт передумав — 2")).toBeInTheDocument();
    expect(screen.queryByText("Повернення")).not.toBeInTheDocument();
  });

  it("persists the selected period to localStorage", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(makeFinance());
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");

    render(<App />);
    await screen.findByText("Фінанси");

    fireEvent.click(screen.getByRole("button", { name: "Рік" }));

    await waitFor(() => {
      expect(setItemSpy).toHaveBeenCalledWith("skladbase:financePeriod", "year");
    });
  });

  it("restores the previously selected period on load", async () => {
    localStorage.setItem("skladbase:financePeriod", "year");
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(makeFinance());

    render(<App />);
    await screen.findByText("Фінанси");

    await waitFor(() => {
      expect(api.getFinanceSummary).toHaveBeenCalledWith("year");
    });
    expect(screen.getByRole("button", { name: "Рік" })).toHaveAttribute("aria-pressed", "true");
  });

  it("defaults to 'all time' when no period was ever saved", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(makeFinance());

    render(<App />);
    await screen.findByText("Фінанси");

    expect(screen.getByRole("button", { name: "Весь час" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("renders Top Products as its own section, separate from the finance card", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(
      makeFinance({
        revenue_uah: "700.00",
        sales_count: 2,
        units_sold: 4,
        top_products: [{ product_id: 1, name: "Кепка", revenue_uah: "500.00", units: 1 }],
      }),
    );

    render(<App />);
    await screen.findByText("Фінанси");

    const topProductsHeading = await screen.findByText("Топ товарів");
    const financeCard = screen.getByText("Фінанси").closest(".glass-card");
    const topProductsCard = topProductsHeading.closest(".glass-card");

    expect(topProductsCard).not.toBeNull();
    expect(topProductsCard).not.toBe(financeCard);
    expect(financeCard?.contains(topProductsHeading)).toBe(false);
  });

  it("opens ProductModal when clicking a top product row; a deleted product's row is not clickable", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([makeProduct({ id: 1, name: "Кепка" })]);
    vi.mocked(api.getFinanceSummary).mockResolvedValue(
      makeFinance({
        top_products: [
          { product_id: 1, name: "Кепка", revenue_uah: "500.00", units: 1 },
          { product_id: 99, name: "Видалений товар", revenue_uah: "10.00", units: 1 },
        ],
      }),
    );

    render(<App />);
    await screen.findByText("Топ товарів");

    const deletedRow = screen.getByText("Видалений товар").closest("li");
    expect(deletedRow).not.toHaveAttribute("role", "button");
    fireEvent.click(screen.getByText("Видалений товар"));
    expect(screen.queryByRole("dialog", { name: "Редагувати товар" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Кепка"));

    expect(await screen.findByRole("dialog", { name: "Редагувати товар" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Інфо" }));
    expect(screen.getByLabelText("Назва")).toHaveValue("Кепка");
  });
});

describe("Nova Poshta sender profile (Settings, owner-only)", () => {
  async function goToSettings() {
    await screen.findByText("Тестовий магазин");
    fireEvent.click(screen.getByRole("tab", { name: "Налаштування" }));
  }

  it("is shown only once the NP key is connected", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getNpStatus).mockResolvedValue({ connected: false });

    render(<App />);
    await goToSettings();
    await screen.findByText("Нова Пошта");

    expect(screen.queryByText("Дані відправника")).not.toBeInTheDocument();
  });

  it("searches a city with a debounce, picks a warehouse and saves the sender profile", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getNpStatus).mockResolvedValue({ connected: true });
    vi.mocked(api.searchNpCities).mockResolvedValue([{ ref: "city-ref-1", name: "Київ" }]);
    vi.mocked(api.getNpWarehouses).mockResolvedValue([{ ref: "wh-ref-1", name: "Відділення №1" }]);
    vi.mocked(api.putNpSender).mockResolvedValue({
      city_ref: "city-ref-1",
      city_name: "Київ",
      warehouse_ref: "wh-ref-1",
      warehouse_name: "Відділення №1",
      phone: "380501112233",
      name: "ФОП Іваненко",
    });

    render(<App />);
    await goToSettings();
    // "Дані відправника" рендериться одразу, поля форми — лише після того,
    // як SenderSection сама довантажить getNpSender() (власний loading-стан).
    await screen.findByLabelText("ПІБ / ФОП");

    fireEvent.change(screen.getByLabelText("ПІБ / ФОП"), { target: { value: "ФОП Іваненко" } });
    fireEvent.change(screen.getByLabelText("Телефон"), { target: { value: "380501112233" } });

    fireEvent.change(screen.getByLabelText("Місто"), { target: { value: "Ки" } });
    expect(api.searchNpCities).not.toHaveBeenCalled(); // дебаунс — не одразу
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(api.searchNpCities).toHaveBeenCalledWith("Ки");
    fireEvent.click(await screen.findByText("Київ"));

    fireEvent.focus(screen.getByLabelText("Відділення"));
    fireEvent.click(await screen.findByText("Відділення №1"));

    // "Зберегти" неоднозначне на цьому екрані (є ще й у профілі магазину) —
    // звужуємо пошук до самої секції відправника.
    const senderSection = screen.getByText("Дані відправника").closest(".np-sender-section");
    fireEvent.click(within(senderSection as HTMLElement).getByRole("button", { name: "Зберегти" }));

    await waitFor(() => {
      expect(api.putNpSender).toHaveBeenCalledWith({
        city_ref: "city-ref-1",
        city_name: "Київ",
        warehouse_ref: "wh-ref-1",
        warehouse_name: "Відділення №1",
        phone: "380501112233",
        name: "ФОП Іваненко",
      });
    });
    expect(await screen.findByText("Відправник налаштований ✅")).toBeInTheDocument();
  });
});

describe("ShipSheet — automatic TTN creation", () => {
  function mockShipReadyShop() {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    const variant = makeVariant({
      id: 501,
      sku: "SKU-501",
      on_hand: 5,
      reserved: 2,
      available: 3,
      price: "300.00",
    });
    vi.mocked(api.getProducts).mockResolvedValue([
      makeProduct({ name: "Кросівки", variants: [variant] }),
    ]);
    vi.mocked(api.getReservations).mockResolvedValue([
      makeReservation({ id: 900, variant_id: 501, qty: 2 }),
    ]);
  }

  async function openAutoShipForm() {
    render(<App />);
    await goToSklad();
    await screen.findByText("Кросівки");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Кросівки"));
    await screen.findByTestId("available-501");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
    await openReservationSheet("Кросівки");
    fireEvent.click(screen.getByRole("button", { name: "Відправлено" }));
    fireEvent.click(await screen.findByRole("button", { name: "Створити ТТН автоматично" }));
  }

  async function fillRecipientForm() {
    await screen.findByLabelText("ПІБ одержувача");
    fireEvent.change(screen.getByLabelText("ПІБ одержувача"), {
      target: { value: "Петро Сидоренко" },
    });
    fireEvent.change(screen.getByLabelText("Телефон одержувача"), {
      target: { value: "380671112233" },
    });

    fireEvent.change(screen.getByLabelText("Місто"), { target: { value: "Льв" } });
    await new Promise((resolve) => setTimeout(resolve, 350));
    fireEvent.click(await screen.findByText("Львів"));

    fireEvent.focus(screen.getByLabelText("Відділення"));
    fireEvent.click(await screen.findByText("Відділення №5"));
  }

  function mockRecipientLookups() {
    vi.mocked(api.getNpSender).mockResolvedValue({
      city_ref: "sender-city",
      city_name: "Київ",
      warehouse_ref: "sender-wh",
      warehouse_name: "Відділення №1",
      phone: "380501112233",
      name: "ФОП Іваненко",
    });
    vi.mocked(api.searchNpCities).mockResolvedValue([{ ref: "rec-city", name: "Львів" }]);
    vi.mocked(api.getNpWarehouses).mockResolvedValue([{ ref: "rec-wh", name: "Відділення №5" }]);
  }

  it("shows a hint and a settings-navigation button when sender is not configured", async () => {
    mockShipReadyShop();
    vi.mocked(api.getNpSender).mockResolvedValue({
      city_ref: null,
      city_name: null,
      warehouse_ref: null,
      warehouse_name: null,
      phone: null,
      name: null,
    });

    await openAutoShipForm();

    expect(
      await screen.findByText("Заповніть дані відправника в Налаштуваннях"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Перейти в Налаштування" }));
    expect(screen.getByRole("tab", { name: "Налаштування" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("submits create-ttn with weight/description defaults, cod unchecked -> no cod_amount", async () => {
    mockShipReadyShop();
    mockRecipientLookups();
    vi.mocked(api.createTtn).mockResolvedValue({ ttn: "20450000000123", delivery_cost: "80.00" });

    await openAutoShipForm();
    await fillRecipientForm();

    fireEvent.click(screen.getByRole("button", { name: "Створити накладну" }));

    await waitFor(() => {
      expect(api.createTtn).toHaveBeenCalledWith(900, {
        recipient_name: "Петро Сидоренко",
        recipient_phone: "380671112233",
        recipient_city_ref: "rec-city",
        recipient_warehouse_ref: "rec-wh",
        weight: 0.5,
        cod: false,
        cod_amount: undefined,
        description: "Кросівки",
      });
    });

    expect(
      await screen.findByText("ТТН 20450000000123 створено, доставка ~80.00 грн"),
    ).toBeInTheDocument();
  });

  it("cod checkbox defaults cod_amount to the reservation total (price * qty)", async () => {
    mockShipReadyShop();
    mockRecipientLookups();
    vi.mocked(api.createTtn).mockResolvedValue({ ttn: "20450000000124", delivery_cost: "80.00" });

    await openAutoShipForm();
    await fillRecipientForm();

    fireEvent.click(screen.getByRole("checkbox", { name: "Накладений платіж" }));
    fireEvent.click(screen.getByRole("button", { name: "Створити накладну" }));

    await waitFor(() => {
      expect(api.createTtn).toHaveBeenCalledWith(
        900,
        expect.objectContaining({ cod: true, cod_amount: "600.00" }), // 300 * 2
      );
    });
  });

  it("shows the НП error text as an inline banner on 422", async () => {
    mockShipReadyShop();
    mockRecipientLookups();
    vi.mocked(api.createTtn).mockRejectedValue(
      new ApiError(422, "НП: невірний формат телефону одержувача"),
    );

    await openAutoShipForm();
    await fillRecipientForm();

    fireEvent.click(screen.getByRole("button", { name: "Створити накладну" }));

    expect(
      await screen.findByText("НП: невірний формат телефону одержувача"),
    ).toBeInTheDocument();
  });
});

describe("i18n language switcher", () => {
  afterEach(async () => {
    // i18n is a module-level singleton — reset it back to uk so later tests
    // in this file (which assert Ukrainian text) aren't affected.
    const { default: i18n } = await import("../i18n");
    await i18n.changeLanguage("uk");
  });

  async function goToSettings() {
    await screen.findByText("Тестовий магазин");
    fireEvent.click(screen.getByRole("tab", { name: "Налаштування" }));
  }

  it("switches the tab bar language when a language chip is selected", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getPlans).mockResolvedValue([planFixture]);

    render(<App />);
    await goToSettings();

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(await screen.findByRole("tab", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Inventory" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Settings" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Русский" }));

    expect(await screen.findByRole("tab", { name: "Настройки" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Дашборд" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Склад" })).toBeInTheDocument();
  });

  it("persists the selected language in localStorage across a remount", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getPlans).mockResolvedValue([planFixture]);

    const { unmount } = render(<App />);
    await goToSettings();
    fireEvent.click(screen.getByRole("button", { name: "English" }));
    await screen.findByRole("tab", { name: "Dashboard" });
    unmount();

    expect(localStorage.getItem("skladbase:lang")).toBe("en");

    render(<App />);
    expect(await screen.findByRole("tab", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("falls back to Ukrainian text for keys not yet translated", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getPlans).mockResolvedValue([planFixture]);

    render(<App />);
    await goToSettings();

    fireEvent.click(screen.getByRole("button", { name: "English" }));
    await screen.findByRole("tab", { name: "Dashboard" });

    // "Підписка" (subscription card heading) has no en/ru translation yet —
    // it must still fall back to the Ukrainian source string.
    expect(screen.getByText("Підписка")).toBeInTheDocument();
  });
});
