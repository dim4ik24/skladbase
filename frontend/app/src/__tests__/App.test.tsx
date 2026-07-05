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
  clearDemos: vi.fn(),
  getFinanceSummary: vi.fn(),
  patchVariant: vi.fn(),
  addVariant: vi.fn(),
  deleteVariant: vi.fn(),
  createInvite: vi.fn(),
  listInvites: vi.fn(),
  revokeInvite: vi.fn(),
  listMembers: vi.fn(),
  removeMember: vi.fn(),
  updateMemberPermissions: vi.fn(),
  setActiveShopId: vi.fn(),
  getNpStatus: vi.fn(),
  putNpKey: vi.fn(),
  deleteNpKey: vi.fn(),
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
  vi.mocked(api.clearDemos).mockReset();
  vi.mocked(api.getFinanceSummary)
    .mockReset()
    .mockResolvedValue({ shop_id: 1, revenue_uah: "0.00", sales_count: 0, units_sold: 0 });
  vi.mocked(api.patchVariant).mockReset();
  vi.mocked(api.addVariant).mockReset();
  vi.mocked(api.deleteVariant).mockReset();
  vi.mocked(api.createInvite).mockReset();
  vi.mocked(api.listInvites).mockReset().mockResolvedValue([]);
  vi.mocked(api.revokeInvite).mockReset();
  vi.mocked(api.listMembers).mockReset().mockResolvedValue([]);
  vi.mocked(api.removeMember).mockReset();
  vi.mocked(api.updateMemberPermissions).mockReset();
  vi.mocked(api.setActiveShopId).mockReset();
  vi.mocked(api.getNpStatus).mockReset().mockResolvedValue({ connected: false });
  vi.mocked(api.putNpKey).mockReset();
  vi.mocked(api.deleteNpKey).mockReset();
  document.documentElement.style.removeProperty("--accent-color");
  localStorage.clear();
});

// Default tab is Dashboard; navigate to Sklad when tests need catalog content.
async function goToSklad() {
  await screen.findByText("Тестовий магазин");
  fireEvent.click(screen.getByRole("tab", { name: "Склад" }));
}

// Open modal, then open the variant sheet for the tag with the given axisLabel.
async function openSheet(tagLabel: string) {
  fireEvent.click(await screen.findByLabelText(`Варіант: ${tagLabel}`));
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
      .mockResolvedValueOnce({ shop_id: 1, revenue_uah: "0.00", sales_count: 0, units_sold: 0 })
      .mockResolvedValueOnce({ shop_id: 1, revenue_uah: "150.00", sales_count: 1, units_sold: 1 });

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
    fireEvent.click(screen.getByRole("button", { name: "Зняти" }));
    fireEvent.click(screen.getByText("Клієнт передумав"));
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
    fireEvent.click(screen.getByRole("button", { name: "Зняти" }));
    fireEvent.click(screen.getByText("❓ Інше"));
    fireEvent.click(screen.getByRole("button", { name: "Підтвердити" }));

    expect(screen.getByLabelText("Коментар (обов'язково)")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(api.releaseReservation).not.toHaveBeenCalled();
  });

  it("'Зняти' opens a bottom sheet (portal), not an inline dialog inside the card", async () => {
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
    const cardButton = screen.getByRole("button", { name: "Зняти" });
    const card = cardButton.closest("li") as HTMLElement;
    fireEvent.click(cardButton);

    const dialog = screen.getByRole("dialog", { name: /Зняти резерв/ });
    expect(dialog).toBeInTheDocument();
    // Портал (createPortal у document.body) — sheet НЕ вкладений у саму бирку,
    // на відміну від старого інлайн-ReleaseForm, який розсипався поверх карток.
    expect(card.contains(dialog)).toBe(false);
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
      .mockResolvedValueOnce({ shop_id: 1, revenue_uah: "0.00", sales_count: 0, units_sold: 0 })
      .mockResolvedValueOnce({ shop_id: 1, revenue_uah: "400.00", sales_count: 1, units_sold: 2 });

    render(<App />);
    await goToSklad();
    await screen.findByText("Футболка");
    fireEvent.click(screen.getByLabelText("Редагувати товар: Футболка"));
    await screen.findByTestId("available-82");

    fireEvent.click(screen.getByRole("button", { name: "Резерви (1)" }));
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
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
      },
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
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
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
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

  it("expands permission checkboxes on tap and updates one via PATCH", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
      },
    ]);
    vi.mocked(api.updateMemberPermissions).mockResolvedValue({
      id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
      can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
      can_manage_stock: true, can_view_finance: false, can_manage_billing: true,
    });

    render(<App />);
    await goToSettings();
    const managerRow = (await screen.findByText("Менеджер Іван")).closest("li");
    expect(managerRow).not.toBeNull();

    expect(within(managerRow as HTMLElement).queryByText("Фінанси")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Менеджер Іван"));

    const financeCheckbox = within(managerRow as HTMLElement).getByLabelText("Фінанси");
    expect(financeCheckbox).toBeInTheDocument();

    fireEvent.click(financeCheckbox);

    await waitFor(() => {
      expect(api.updateMemberPermissions).toHaveBeenCalledWith(2, { can_view_finance: false });
    });
  });

  it("rolls back the checkbox when the permission PATCH fails", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 2, tg_id: 1002, display_name: "Менеджер Іван", role: "manager",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
      },
    ]);
    vi.mocked(api.updateMemberPermissions).mockRejectedValue(new ApiError(500, "боляче"));

    render(<App />);
    await goToSettings();
    fireEvent.click(await screen.findByText("Менеджер Іван"));

    const financeCheckbox = screen.getByLabelText("Фінанси") as HTMLInputElement;
    fireEvent.click(financeCheckbox);
    expect(financeCheckbox.checked).toBe(false);

    await waitFor(() => {
      expect(financeCheckbox.checked).toBe(true);
    });
    expect(await screen.findByText("боляче")).toBeInTheDocument();
  });

  it("does not expand permissions for the owner's own row", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.listMembers).mockResolvedValue([
      {
        id: 1, tg_id: 1001, display_name: "Дмитро", role: "owner",
        can_view_inventory: true, can_edit_products: true, can_manage_reservations: true,
        can_manage_stock: true, can_view_finance: true, can_manage_billing: true,
      },
    ]);

    render(<App />);
    await goToSettings();
    fireEvent.click(await screen.findByText("Дмитро"));

    expect(screen.queryByText("Фінанси")).not.toBeInTheDocument();
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

describe("Finance summary (Dashboard)", () => {
  it("renders revenue, sales count and units sold from the finance summary", async () => {
    vi.mocked(api.getMe).mockResolvedValue(shopFixture);
    vi.mocked(api.getProducts).mockResolvedValue([]);
    vi.mocked(api.getFinanceSummary).mockResolvedValue({
      shop_id: 1,
      revenue_uah: "450.00",
      sales_count: 2,
      units_sold: 3,
    });

    render(<App />);

    expect(await screen.findByText("Продажів")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Одиниць продано")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });
});
