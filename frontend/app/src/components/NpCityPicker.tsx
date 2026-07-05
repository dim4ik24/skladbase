import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { createPortal } from "react-dom";
import * as api from "../api";
import { errorMessage } from "../errors";
import { useAnchoredDropdown } from "../hooks/useAnchoredDropdown";
import type { NpCity } from "../types";

const DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 2;

interface NpCityPickerProps {
  label: string;
  value: NpCity | null;
  onChange: (city: NpCity | null) => void;
  disabled?: boolean;
}

export function NpCityPicker({ label, value, onChange, disabled }: NpCityPickerProps) {
  const [query, setQuery] = useState(value?.name ?? "");
  const [results, setResults] = useState<NpCity[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);
  const rect = useAnchoredDropdown(inputRef, open);

  // Синхронізація query з зовнішнім value (напр. форма підвантажила
  // збережений профіль) — навмисно ПІД ЧАС рендеру, не в ефекті (React-
  // рекомендований патерн "adjusting state when a prop changes", уникає
  // зайвого re-render циклу через useEffect+setState).
  const [syncedRef, setSyncedRef] = useState(value?.ref ?? null);
  if ((value?.ref ?? null) !== syncedRef) {
    setSyncedRef(value?.ref ?? null);
    setQuery(value?.name ?? "");
  }

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  function scheduleSearch(q: string) {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (q.trim().length < MIN_QUERY_LENGTH) {
      setResults([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(() => {
      void runSearch(q);
    }, DEBOUNCE_MS);
  }

  async function runSearch(q: string) {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const cities = await api.searchNpCities(q);
      if (requestId !== requestIdRef.current) return; // стара відповідь після нового запиту
      setResults(cities);
      setOpen(true);
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      setError(errorMessage(err, "Не вдалося знайти місто"));
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.value;
    setQuery(next);
    if (value) onChange(null);
    scheduleSearch(next);
  }

  function handleFocus() {
    inputRef.current?.select();
    if (query.trim().length >= MIN_QUERY_LENGTH) {
      void runSearch(query);
    }
  }

  function handleBlur() {
    // Невелика затримка, щоб клік по пункту списку встиг спрацювати раніше за закриття.
    setTimeout(() => setOpen(false), 150);
  }

  function handleSelect(city: NpCity) {
    onChange(city);
    setQuery(city.name);
    setResults([]);
    setOpen(false);
  }

  return (
    <div className="np-picker">
      <label className="form-field">
        <span>{label}</span>
        <input
          ref={inputRef}
          type="text"
          value={query}
          disabled={disabled}
          autoComplete="off"
          onChange={handleChange}
          onFocus={handleFocus}
          onBlur={handleBlur}
          placeholder="Почніть вводити назву міста"
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
                <li className="np-picker-option np-picker-option--status">Пошук...</li>
              ) : results.length === 0 ? (
                <li className="np-picker-option np-picker-option--status">Нічого не знайдено</li>
              ) : (
                results.map((city) => (
                  <li key={city.ref}>
                    <button
                      type="button"
                      className="np-picker-option"
                      onClick={() => handleSelect(city)}
                    >
                      {city.name}
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
