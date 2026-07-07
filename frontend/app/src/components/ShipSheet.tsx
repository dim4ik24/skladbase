import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { FormEvent } from "react";
import * as api from "../api";
import { errorMessage } from "../errors";
import { isValidTtn, TTN_ERROR_MESSAGE } from "../lib/ttn";
import { NpCityPicker } from "./NpCityPicker";
import { NpWarehousePicker } from "./NpWarehousePicker";
import type { CreateTtnPayload, CreateTtnResult, NpCity, NpWarehouse, ShipPayload } from "../types";

const DEFAULT_WEIGHT_KG = "0.5";

type ShipMode = "manual" | "auto";

interface ShipSheetProps {
  reservationId: number;
  title: string;
  productName: string;
  defaultCodAmount: number;
  onSubmit: (reservationId: number, payload: ShipPayload) => Promise<void>;
  onCreateTtn: (reservationId: number, payload: CreateTtnPayload) => Promise<CreateTtnResult>;
  onNavigateToSettings: () => void;
  onClose: () => void;
}

export function ShipSheet({
  reservationId,
  title,
  productName,
  defaultCodAmount,
  onSubmit,
  onCreateTtn,
  onNavigateToSettings,
  onClose,
}: ShipSheetProps) {
  const [isClosing, setIsClosing] = useState(false);
  const [mode, setMode] = useState<ShipMode>("manual");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Manual mode (як і раніше)
  const [ttn, setTtn] = useState("");
  const [ttnInvalid, setTtnInvalid] = useState(false);

  // Auto mode
  const [senderConfigured, setSenderConfigured] = useState<boolean | null>(null);
  const [recipientName, setRecipientName] = useState("");
  const [recipientPhone, setRecipientPhone] = useState("");
  const [recipientCity, setRecipientCity] = useState<NpCity | null>(null);
  const [recipientWarehouse, setRecipientWarehouse] = useState<NpWarehouse | null>(null);
  const [weight, setWeight] = useState(DEFAULT_WEIGHT_KG);
  const [cod, setCod] = useState(false);
  const [codAmount, setCodAmount] = useState(defaultCodAmount.toFixed(2));
  const [description, setDescription] = useState(productName);
  const [successResult, setSuccessResult] = useState<CreateTtnResult | null>(null);

  useEffect(() => {
    if (mode !== "auto" || senderConfigured !== null) return;
    let mounted = true;
    async function checkSender() {
      try {
        const profile = await api.getNpSender();
        if (!mounted) return;
        setSenderConfigured(
          profile.city_ref !== null &&
            profile.warehouse_ref !== null &&
            profile.phone !== null &&
            profile.name !== null,
        );
      } catch {
        if (!mounted) return;
        setSenderConfigured(false);
      }
    }
    void checkSender();
    return () => {
      mounted = false;
    };
  }, [mode, senderConfigured]);

  function handleClose() {
    setIsClosing(true);
    setTimeout(onClose, 250);
  }

  async function handleManualSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setTtnInvalid(false);

    const trimmedTtn = ttn.trim();
    if (trimmedTtn && !isValidTtn(trimmedTtn)) {
      setTtnInvalid(true);
      setError(TTN_ERROR_MESSAGE);
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(reservationId, { ttn: trimmedTtn || undefined });
      handleClose();
    } catch (err) {
      setError(errorMessage(err, "Не вдалося відправити резерв"));
      setSubmitting(false);
    }
  }

  async function handleAutoSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!recipientName.trim() || !recipientPhone.trim() || !recipientCity || !recipientWarehouse) {
      setError("Заповніть усі поля одержувача");
      return;
    }

    setSubmitting(true);
    try {
      const result = await onCreateTtn(reservationId, {
        recipient_name: recipientName.trim(),
        recipient_phone: recipientPhone.trim(),
        recipient_city_ref: recipientCity.ref,
        recipient_warehouse_ref: recipientWarehouse.ref,
        weight: Number(weight) || Number(DEFAULT_WEIGHT_KG),
        cod,
        cod_amount: cod ? codAmount.trim() || undefined : undefined,
        description: description.trim() || undefined,
      });
      setSuccessResult(result);
    } catch (err) {
      setError(errorMessage(err, "Не вдалося створити накладну"));
    } finally {
      setSubmitting(false);
    }
  }

  const sheet = (
    <>
      <div
        className={`sheet-backdrop${isClosing ? " sheet-backdrop--closing" : ""}`}
        onClick={handleClose}
      />
      <div
        role="dialog"
        aria-label={`Відправити: ${title}`}
        className={`variant-sheet${isClosing ? " variant-sheet--closing" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-header">
          <span className="sheet-axis-label release-sheet-title">Відправити: {title}</span>
          <button type="button" className="sheet-close" aria-label="Закрити" onClick={handleClose}>
            ✕
          </button>
        </div>

        {successResult ? (
          <>
            <p className="ship-success-message">
              ТТН {successResult.ttn} створено, доставка ~{successResult.delivery_cost} грн
            </p>
            <div className="modal-actions">
              <button type="button" onClick={handleClose}>
                Готово
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={mode === "manual" ? handleManualSubmit : handleAutoSubmit}>
            {error ? <p className="error-banner">{error}</p> : null}

            <div className="ship-mode-toggle" role="group" aria-label="Спосіб відправки">
              <button
                type="button"
                className={`ship-mode-btn${mode === "auto" ? " ship-mode-btn--active" : ""}`}
                aria-pressed={mode === "auto"}
                onClick={() => setMode("auto")}
              >
                Створити ТТН автоматично
              </button>
              <button
                type="button"
                className={`ship-mode-btn${mode === "manual" ? " ship-mode-btn--active" : ""}`}
                aria-pressed={mode === "manual"}
                onClick={() => setMode("manual")}
              >
                Вписати ТТН вручну
              </button>
            </div>

            {mode === "manual" ? (
              <label className="form-field">
                <span>ТТН (можна додати пізніше)</span>
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={14}
                  value={ttn}
                  onChange={(event) => {
                    setTtn(event.target.value);
                    setTtnInvalid(false);
                  }}
                  placeholder="20450123456789"
                  aria-invalid={ttnInvalid}
                  className={ttnInvalid ? "input-error" : undefined}
                />
              </label>
            ) : senderConfigured === null ? (
              <p className="status-text">Перевіряємо дані відправника…</p>
            ) : senderConfigured === false ? (
              <div className="ship-sender-hint">
                <p>Заповніть дані відправника в Налаштуваннях</p>
                <button type="button" onClick={onNavigateToSettings}>
                  Перейти в Налаштування
                </button>
              </div>
            ) : (
              <>
                <label className="form-field">
                  <span>ПІБ одержувача</span>
                  <input
                    type="text"
                    value={recipientName}
                    onChange={(event) => setRecipientName(event.target.value)}
                  />
                </label>
                <label className="form-field">
                  <span>Телефон одержувача</span>
                  <input
                    type="tel"
                    value={recipientPhone}
                    onChange={(event) => setRecipientPhone(event.target.value)}
                    placeholder="380XXXXXXXXX"
                  />
                </label>
                <NpCityPicker label="Місто" value={recipientCity} onChange={setRecipientCity} />
                <NpWarehousePicker
                  label="Відділення"
                  cityRef={recipientCity?.ref ?? null}
                  value={recipientWarehouse}
                  onChange={setRecipientWarehouse}
                />
                <label className="form-field">
                  <span>Вага, кг</span>
                  <input
                    type="number"
                    min="0.1"
                    step="0.1"
                    value={weight}
                    onChange={(event) => setWeight(event.target.value)}
                  />
                </label>
                <label className="flex items-center gap-2 text-sm text-text mb-2">
                  <input
                    type="checkbox"
                    checked={cod}
                    onChange={(event) => setCod(event.target.checked)}
                  />
                  Накладений платіж
                </label>
                {cod ? (
                  <label className="form-field">
                    <span>Сума накладеного платежу</span>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={codAmount}
                      onChange={(event) => setCodAmount(event.target.value)}
                    />
                  </label>
                ) : null}
                <label className="form-field">
                  <span>Опис</span>
                  <input
                    type="text"
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                  />
                </label>
              </>
            )}

            <div className="modal-actions">
              <button type="button" onClick={handleClose} disabled={submitting}>
                Скасувати
              </button>
              {mode === "manual" ? (
                <button type="submit" disabled={submitting}>
                  {submitting ? "Відправляємо..." : "Відправлено"}
                </button>
              ) : senderConfigured ? (
                <button type="submit" disabled={submitting}>
                  {submitting ? "Створюємо..." : "Створити накладну"}
                </button>
              ) : null}
            </div>
          </form>
        )}
      </div>
    </>
  );

  return createPortal(sheet, document.body);
}
