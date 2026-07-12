import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import * as api from "../api";
import { errorMessage } from "../errors";
import { isValidTtn } from "../lib/ttn";
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
  const { t } = useTranslation();
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
      setError(t("shipping.ttnError"));
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(reservationId, { ttn: trimmedTtn || undefined });
      handleClose();
    } catch (err) {
      setError(errorMessage(err, t("shipping.sendFailed")));
      setSubmitting(false);
    }
  }

  async function handleAutoSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!recipientName.trim() || !recipientPhone.trim() || !recipientCity || !recipientWarehouse) {
      setError(t("shipping.recipientFieldsMissing"));
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
      setError(errorMessage(err, t("shipping.createFailed")));
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
        aria-label={t("shipping.ariaLabel", { title })}
        className={`variant-sheet${isClosing ? " variant-sheet--closing" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-header">
          <span className="sheet-axis-label release-sheet-title">
            {t("shipping.ariaLabel", { title })}
          </span>
          <button
            type="button"
            className="sheet-close"
            aria-label={t("common.close")}
            onClick={handleClose}
          >
            ✕
          </button>
        </div>

        {successResult ? (
          <>
            <p className="ship-success-message">
              {t("shipping.successMessage", {
                ttn: successResult.ttn,
                cost: successResult.delivery_cost,
              })}
            </p>
            <div className="modal-actions">
              <button type="button" onClick={handleClose}>
                {t("shipping.done")}
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={mode === "manual" ? handleManualSubmit : handleAutoSubmit}>
            {error ? <p className="error-banner">{error}</p> : null}

            <div className="ship-mode-toggle" role="group" aria-label={t("shipping.modeAriaLabel")}>
              <button
                type="button"
                className={`ship-mode-btn${mode === "auto" ? " ship-mode-btn--active" : ""}`}
                aria-pressed={mode === "auto"}
                onClick={() => setMode("auto")}
              >
                {t("shipping.modeAuto")}
              </button>
              <button
                type="button"
                className={`ship-mode-btn${mode === "manual" ? " ship-mode-btn--active" : ""}`}
                aria-pressed={mode === "manual"}
                onClick={() => setMode("manual")}
              >
                {t("shipping.modeManual")}
              </button>
            </div>

            {mode === "manual" ? (
              <label className="form-field">
                <span>{t("shipping.ttnFieldLabel")}</span>
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
              <p className="status-text">{t("shipping.checkingSender")}</p>
            ) : senderConfigured === false ? (
              <div className="ship-sender-hint">
                <p>{t("shipping.senderMissingHint")}</p>
                <button type="button" onClick={onNavigateToSettings}>
                  {t("shipping.goToSettings")}
                </button>
              </div>
            ) : (
              <>
                <label className="form-field">
                  <span>{t("shipping.recipientName")}</span>
                  <input
                    type="text"
                    value={recipientName}
                    onChange={(event) => setRecipientName(event.target.value)}
                  />
                </label>
                <label className="form-field">
                  <span>{t("shipping.recipientPhone")}</span>
                  <input
                    type="tel"
                    value={recipientPhone}
                    onChange={(event) => setRecipientPhone(event.target.value)}
                    placeholder="380XXXXXXXXX"
                  />
                </label>
                <NpCityPicker
                  label={t("shipping.city")}
                  value={recipientCity}
                  onChange={setRecipientCity}
                />
                <NpWarehousePicker
                  label={t("shipping.warehouse")}
                  cityRef={recipientCity?.ref ?? null}
                  value={recipientWarehouse}
                  onChange={setRecipientWarehouse}
                />
                <label className="form-field">
                  <span>{t("shipping.weight")}</span>
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
                  {t("shipping.cod")}
                </label>
                {cod ? (
                  <label className="form-field">
                    <span>{t("shipping.codAmount")}</span>
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
                  <span>{t("shipping.description")}</span>
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
                {t("common.cancel")}
              </button>
              {mode === "manual" ? (
                <button type="submit" disabled={submitting}>
                  {submitting ? t("shipping.sending") : t("shipping.sent")}
                </button>
              ) : senderConfigured ? (
                <button type="submit" disabled={submitting}>
                  {submitting ? t("shipping.creating") : t("shipping.createTtnButton")}
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
