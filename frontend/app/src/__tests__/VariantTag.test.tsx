import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VariantTag } from "../components/VariantTag";
import type { TemplateField, Variant } from "../types";

function makeVariant(overrides: Partial<Variant> = {}): Variant {
  return {
    id: 1,
    sku: "SKU-1",
    axis_values: {},
    price: "100.00",
    on_hand: 5,
    reserved: 0,
    available: 5,
    low_stock_threshold: 2,
    photo_url: null,
    ...overrides,
  };
}

describe("VariantTag chip fallback (no photo, no resolvable color)", () => {
  it("renders a neutral lavender letter chip, never a black/empty square, when the color axis value isn't in COLOR_MAP", () => {
    const axes: TemplateField[] = [{ key: "колір", label: "Колір", type: "text" }];
    const variant = makeVariant({ axis_values: { колір: "Travis Scott" } });

    render(<VariantTag variant={variant} axes={axes} photoUrl={null} onClick={() => {}} />);

    const chip = document.querySelector(".variant-chip");
    expect(chip).not.toBeNull();
    expect(chip).toHaveClass("variant-chip--neutral");
    expect(chip).toHaveTextContent("T");
    // Neutral fallback never sets an inline background — it's the CSS class's
    // pastel token. An inline style here would mean an unmapped color leaked
    // through as a raw (possibly black) background instead of falling back.
    expect((chip as HTMLElement).style.background).toBe("");
  });

  it("renders a neutral lavender letter chip when there is no color axis at all", () => {
    const axes: TemplateField[] = [{ key: "розмір", label: "Розмір", type: "text" }];
    const variant = makeVariant({ axis_values: { розмір: "M" } });

    render(<VariantTag variant={variant} axes={axes} photoUrl={null} onClick={() => {}} />);

    const chip = document.querySelector(".variant-chip");
    expect(chip).toHaveClass("variant-chip--neutral");
    expect(chip).toHaveTextContent("M");
    expect((chip as HTMLElement).style.background).toBe("");
  });

  it("falls back to the neutral chip with '?' when axis_values is completely empty", () => {
    const axes: TemplateField[] = [{ key: "колір", label: "Колір", type: "text" }];
    const variant = makeVariant({ axis_values: {} });

    render(<VariantTag variant={variant} axes={axes} photoUrl={null} onClick={() => {}} />);

    const chip = document.querySelector(".variant-chip");
    expect(chip).toHaveClass("variant-chip--neutral");
    expect(chip).toHaveTextContent("?");
  });

  it("still renders a real background color when the axis value matches COLOR_MAP", () => {
    const axes: TemplateField[] = [{ key: "колір", label: "Колір", type: "text" }];
    const variant = makeVariant({ axis_values: { колір: "чорний" } });

    render(<VariantTag variant={variant} axes={axes} photoUrl={null} onClick={() => {}} />);

    const chip = document.querySelector(".variant-chip");
    expect(chip).not.toHaveClass("variant-chip--neutral");
    expect((chip as HTMLElement).style.background).toBe("rgb(28, 37, 32)");
  });

  it("uses the photo when no color resolves but a photo is available", () => {
    const axes: TemplateField[] = [{ key: "колір", label: "Колір", type: "text" }];
    const variant = makeVariant({ axis_values: { колір: "Travis Scott" } });

    render(
      <VariantTag
        variant={variant}
        axes={axes}
        photoUrl="https://cdn.example.test/photo.webp"
        onClick={() => {}}
      />,
    );

    expect(document.querySelector("img")).toHaveClass("variant-chip--photo");
  });
});
