import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({
  searchNpCities: vi.fn(),
}));

import * as api from "../api";
import { NpCityPicker } from "../components/NpCityPicker";

describe("NpCityPicker", () => {
  beforeEach(() => {
    vi.mocked(api.searchNpCities).mockReset();
  });

  it("debounces the search 300ms before calling searchNpCities", async () => {
    vi.mocked(api.searchNpCities).mockResolvedValue([{ ref: "city-ref-1", name: "Київ" }]);
    const onChange = vi.fn();
    render(<NpCityPicker label="Місто" value={null} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("Місто"), { target: { value: "Ки" } });
    expect(api.searchNpCities).not.toHaveBeenCalled();

    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(api.searchNpCities).toHaveBeenCalledWith("Ки");
  });

  it("does not search below the minimum query length", async () => {
    vi.mocked(api.searchNpCities).mockResolvedValue([]);
    render(<NpCityPicker label="Місто" value={null} onChange={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Місто"), { target: { value: "К" } });
    await new Promise((resolve) => setTimeout(resolve, 350));

    expect(api.searchNpCities).not.toHaveBeenCalled();
  });

  it("selecting a result fixes ref+name and closes the dropdown", async () => {
    vi.mocked(api.searchNpCities).mockResolvedValue([{ ref: "city-ref-1", name: "Київ" }]);
    const onChange = vi.fn();
    render(<NpCityPicker label="Місто" value={null} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("Місто"), { target: { value: "Ки" } });
    await new Promise((resolve) => setTimeout(resolve, 350));

    fireEvent.click(await screen.findByText("Київ"));

    expect(onChange).toHaveBeenCalledWith({ ref: "city-ref-1", name: "Київ" });
    expect(screen.getByLabelText("Місто")).toHaveValue("Київ");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("typing after a selection invalidates it until a new pick is made", async () => {
    vi.mocked(api.searchNpCities).mockResolvedValue([]);
    const onChange = vi.fn();
    render(
      <NpCityPicker label="Місто" value={{ ref: "city-ref-1", name: "Київ" }} onChange={onChange} />,
    );

    fireEvent.change(screen.getByLabelText("Місто"), { target: { value: "Ки" } });

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("re-searches on refocus when there is already a query typed", async () => {
    vi.mocked(api.searchNpCities).mockResolvedValue([{ ref: "city-ref-1", name: "Київ" }]);
    render(<NpCityPicker label="Місто" value={null} onChange={vi.fn()} />);

    const input = screen.getByLabelText("Місто");
    fireEvent.change(input, { target: { value: "Ки" } });
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(api.searchNpCities).toHaveBeenCalledTimes(1);

    fireEvent.blur(input);
    await new Promise((resolve) => setTimeout(resolve, 200));
    fireEvent.focus(input);

    expect(api.searchNpCities).toHaveBeenCalledTimes(2);
  });
});
