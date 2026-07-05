import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { createPortal } from "react-dom";
import * as api from "../api";
import { errorMessage } from "../errors";
import { useAnchoredDropdown } from "../hooks/useAnchoredDropdown";
import type { NpWarehouse } from "../types";

interface NpWarehousePickerProps {
  label: string;
  cityRef: string | null;
  value: NpWarehouse | null;
  onChange: (warehouse: NpWarehouse | null) => void;
  disabled?: boolean;
}

// На відміну від NpCityPicker (дебаунсений пошук на сервері), список
// відділень міста тягнеться ОДИН РАЗ при виборі міста (не дуже великий) і
// далі фільтрується локально під час вводу — зайвий round-trip на кожен
// символ тут не потрібен.
export function NpWarehousePicker({
  label,
  cityRef,
  value,
  onChange,
  disabled,
}: NpWarehousePickerProps) {
  const [query, setQuery] = useState(value?.name ?? "");
  const [warehouses, setWarehouses] = useState<NpWarehouse[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const prevCityRefRef = useRef(cityRef);
  const rect = useAnchoredDropdown(inputRef, open);

  // Синхронізація query з зовнішнім value ПІД ЧАС рендеру, не в ефекті —
  // той самий патерн, що й у NpCityPicker.
  const [syncedRef, setSyncedRef] = useState(value?.ref ?? null);
  if ((value?.ref ?? null) !== syncedRef) {
    setSyncedRef(value?.ref ?? null);
    setQuery(value?.name ?? "");
  }

  useEffect(() => {
    if (prevCityRefRef.current === cityRef) return; // не чіпаємо на початковому mount
    prevCityRefRef.current = cityRef;
    setWarehouses([]);
    setQuery("");
    onChange(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- скидаємо лише на зміну міста
  }, [cityRef]);

  async function loadWarehouses() {
    if (!cityRef) return;
    setLoading(true);
    setError(null);
    try {
      const rows = await api.getNpWarehouses(cityRef);
      setWarehouses(rows);
      setOpen(true);
    } catch (err) {
      setError(errorMessage(err, "Не вдалося завантажити відділення"));
    } finally {
      setLoading(false);
    }
  }

  async function handleFocus() {
    inputRef.current?.select();
    if (!cityRef) return;
    if (warehouses.length === 0) {
      await loadWarehouses();
    } else {
      setOpen(true);
    }
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    setQuery(event.target.value);
    if (value) onChange(null);
    setOpen(true);
  }

  function handleBlur() {
    setTimeout(() => setOpen(false), 150);
  }

  function handleSelect(warehouse: NpWarehouse) {
    onChange(warehouse);
    setQuery(warehouse.name);
    setOpen(false);
  }

  const filtered = query.trim()
    ? warehouses.filter((w) => w.name.toLowerCase().includes(query.trim().toLowerCase()))
    : warehouses;

  return (
    <div className="np-picker">
      <label className="form-field">
        <span>{label}</span>
        <input
          ref={inputRef}
          type="text"
          value={query}
          disabled={disabled || !cityRef}
          autoComplete="off"
          onChange={handleChange}
          onFocus={() => void handleFocus()}
          onBlur={handleBlur}
          placeholder={cityRef ? "Пошук відділення" : "Спершу оберіть місто"}
        />
      </label>
      {error ? <p className="error-banner np-picker-error">{error}</p> : null}
      {open && rect
        ? createPortal(
            <ul
              className="np-picker-dropdown"
              style={{ top: rect.top, left: rect.left, width: rect.width }}
              role="listbox"
              aria-label={label}
            >
              {loading ? (
                <li className="np-picker-option np-picker-option--status">Завантаження...</li>
              ) : filtered.length === 0 ? (
                <li className="np-picker-option np-picker-option--status">Нічого не знайдено</li>
              ) : (
                filtered.map((w) => (
                  <li key={w.ref}>
                    <button
                      type="button"
                      className="np-picker-option"
                      onClick={() => handleSelect(w)}
                    >
                      {w.name}
                    </button>
                  </li>
                ))
              )}
            </ul>,
            document.body,
          )
        : null}
    </div>
  );
}
