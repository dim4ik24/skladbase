import { useState } from "react";
import { createPortal } from "react-dom";
import type { ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../errors";
import { chipLetter, resolveChipColor } from "../lib/variantColor";
import type {
  AdjustPayload,
  CreateTtnPayload,
  CreateTtnResult,
  Reservation,
  ReserveInput,
  ShipPayload,
  TemplateField,
  Variant,
  VariantPatchPayload,
} from "../types";
import { ReserveForm } from "./ReserveForm";
import { SellForm } from "./SellForm";
import { ShipSheet } from "./ShipSheet";
import { WriteOffForm } from "./WriteOffForm";

interface VariantSheetProps {
  variant: Variant;
  axes: TemplateField[];
  photoUrl: string | null;
  productName: string;
  isFrozen?: boolean;
  onFrozenAction?: () => void;
  onRestock: (variantId: number, qty: number) => void;
  onAdjust: (variantId: number, payload: AdjustPayload) => Promise<void>;
  onUploadPhoto: (variantId: number, file: File) => Promise<void>;
  onReserve: (variantId: number, payload: ReserveInput) => Promise<Reservation | undefined>;
  onPatchVariant: (variantId: number, patch: VariantPatchPayload) => Promise<void>;
  onDeleteVariant: (variantId: number) => Promise<void>;
  onShip: (reservationId: number, payload: ShipPayload) => Promise<void>;
  onCreateTtn: (reservationId: number, payload: CreateTtnPayload) => Promise<CreateTtnResult>;
  onNavigateToSettings: () => void;
  onClose: () => void;
}

export function VariantSheet({
  variant,
  axes,
  photoUrl,
  productName,
  isFrozen = false,
  onFrozenAction,
  onRestock,
  onAdjust,
  onUploadPhoto,
  onReserve,
  onPatchVariant,
  onDeleteVariant,
  onShip,
  onCreateTtn,
  onNavigateToSettings,
  onClose,
}: VariantSheetProps) {
  const { t } = useTranslation();
  const [isClosing, setIsClosing] = useState(false);

  // Edit fields
  const [price, setPrice] = useState(variant.price);
  const [sku, setSku] = useState(variant.sku ?? "");
  const [axisValues, setAxisValues] = useState<Record<string, string>>({
    ...variant.axis_values,
  });
  const [saving, setSaving] = useState(false);
  const [patchError, setPatchError] = useState<string | null>(null);

  // Delete
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Reserve
  const [showReserveForm, setShowReserveForm] = useState(false);

  // Write-off (списання з причиною)
  const [showWriteOffForm, setShowWriteOffForm] = useState(false);

  // Продано: без відправки -> write_off(reason=sold); з відправкою -> reserve + ship
  const [showSellForm, setShowSellForm] = useState(false);
  const [sellReservation, setSellReservation] = useState<Reservation | null>(null);

  // Photo upload
  const [photoUploading, setPhotoUploading] = useState(false);
  const [photoError, setPhotoError] = useState<string | null>(null);

  const axisLabel = Object.values(variant.axis_values).filter(Boolean).join(" / ");
  const chipColor = resolveChipColor(axes, variant.axis_values);
  const letter = chipLetter(axes, variant.axis_values);
  const isWhite = chipColor === "#FFFFFF";

  function handleClose() {
    setIsClosing(true);
    setTimeout(onClose, 250);
  }

  async function handleSave() {
    setPatchError(null);
    setSaving(true);
    const patch: VariantPatchPayload = { price };
    patch.sku = sku.trim() || null;
    if (axes.length > 0) patch.axis_values = axisValues;
    try {
      await onPatchVariant(variant.id, patch);
    } catch (err) {
      setPatchError(errorMessage(err, t("variant.saveFailed")));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setDeleteError(null);
    setDeleting(true);
    try {
      await onDeleteVariant(variant.id);
      onClose();
    } catch (err) {
      setDeleteError(errorMessage(err, t("variant.deleteFailed")));
      setConfirmDelete(false);
    } finally {
      setDeleting(false);
    }
  }

  async function handlePhotoChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setPhotoError(null);
    setPhotoUploading(true);
    try {
      await onUploadPhoto(variant.id, file);
    } catch (err) {
      setPhotoError(errorMessage(err, t("variant.photoUploadFailed")));
    } finally {
      setPhotoUploading(false);
    }
  }

  async function handleReserveSubmit(variantId: number, payload: ReserveInput) {
    await onReserve(variantId, payload);
    setShowReserveForm(false);
  }

  async function handleWriteOffSubmit(variantId: number, payload: AdjustPayload) {
    await onAdjust(variantId, payload);
    setShowWriteOffForm(false);
  }

  async function handleSellSubmit(variantId: number, qty: number, withShipping: boolean) {
    if (!withShipping) {
      await onAdjust(variantId, { qty, reason: "sold" });
      setShowSellForm(false);
      return;
    }
    const reservation = await onReserve(variantId, { qty });
    setShowSellForm(false);
    if (reservation) setSellReservation(reservation);
  }

  const sheet = (
    <>
      <div
        className={`sheet-backdrop${isClosing ? " sheet-backdrop--closing" : ""}`}
        onClick={handleClose}
      />
      <div
        role="dialog"
        aria-label={t("variant.ariaLabel", {
          label: axisLabel || variant.sku || String(variant.id),
        })}
        className={`variant-sheet${isClosing ? " variant-sheet--closing" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="sheet-header">
          {chipColor !== null ? (
            <span
              className="variant-chip"
              style={{
                background: chipColor,
                border: isWhite ? "1.5px solid var(--line)" : undefined,
              }}
            />
          ) : photoUrl ? (
            <img src={photoUrl} alt="" className="variant-chip variant-chip--photo" />
          ) : (
            <span className="variant-chip variant-chip--neutral">{letter}</span>
          )}
          <span className="sheet-axis-label">
            {axisLabel || variant.sku || `#${variant.id}`}
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

        {/* ── Photo upload ── */}
        <div className="variant-photo">
          {photoUrl ? (
            <img src={photoUrl} alt="" />
          ) : (
            <div className="variant-photo-placeholder" aria-hidden="true">📦</div>
          )}
          <label
            className="variant-photo-upload"
            onClick={
              isFrozen
                ? (e) => { e.preventDefault(); onFrozenAction?.(); }
                : undefined
            }
          >
            {photoUploading ? "..." : "📷"}
            <input
              type="file"
              accept="image/*"
              hidden
              disabled={photoUploading}
              onChange={handlePhotoChange}
              aria-label={t("variant.uploadPhotoAriaLabel", {
                sku: variant.sku ?? String(variant.id),
              })}
            />
          </label>
        </div>
        {photoError ? <p className="error-banner">{photoError}</p> : null}

        {/* ── Stock stepper ── */}
        <div className="sheet-stepper">
          <button
            type="button"
            className="sheet-stepper-btn"
            aria-label={t("variant.decreaseAriaLabel", { sku: variant.sku ?? variant.id })}
            aria-disabled={isFrozen}
            disabled={variant.on_hand <= 0}
            onClick={() => {
              if (isFrozen) { onFrozenAction?.(); return; }
              setShowWriteOffForm((prev) => !prev);
            }}
          >
            −
          </button>
          <span className="sheet-stock-count" data-testid={`stepper-${variant.id}`}>
            {variant.on_hand} {t("common.unitsShort")}
          </span>
          <button
            type="button"
            className="sheet-stepper-btn"
            aria-label={t("variant.increaseAriaLabel", { sku: variant.sku ?? variant.id })}
            aria-disabled={isFrozen}
            onClick={() => {
              if (isFrozen) { onFrozenAction?.(); return; }
              onRestock(variant.id, 1);
            }}
          >
            +
          </button>
        </div>
        {showWriteOffForm ? (
          <WriteOffForm
            variantId={variant.id}
            maxQty={variant.available}
            onSubmit={handleWriteOffSubmit}
            onCancel={() => setShowWriteOffForm(false)}
          />
        ) : null}

        {/* ── Reserve / Продано ── */}
        <div className="sheet-action-row">
          <button
            type="button"
            className="sheet-reserve-btn"
            aria-disabled={isFrozen}
            disabled={variant.available <= 0}
            onClick={() => {
              if (isFrozen) { onFrozenAction?.(); return; }
              setShowReserveForm((prev) => !prev);
            }}
          >
            {t("variant.reserveButton")}
          </button>
          <button
            type="button"
            className="sheet-sell-btn"
            aria-disabled={isFrozen}
            disabled={variant.available <= 0}
            onClick={() => {
              if (isFrozen) { onFrozenAction?.(); return; }
              setShowSellForm((prev) => !prev);
            }}
          >
            {t("variant.sellButton")}
          </button>
        </div>
        {showReserveForm ? (
          <ReserveForm
            variantId={variant.id}
            maxQty={variant.available}
            onSubmit={handleReserveSubmit}
            onCancel={() => setShowReserveForm(false)}
          />
        ) : null}
        {showSellForm ? (
          <SellForm
            variantId={variant.id}
            maxQty={variant.available}
            onSubmit={handleSellSubmit}
            onCancel={() => setShowSellForm(false)}
          />
        ) : null}

        <div className="sheet-divider" />

        {/* ── Edit fields ── */}
        <p className="sheet-section-label">{t("variant.editSectionLabel")}</p>
        {patchError ? <p className="error-banner">{patchError}</p> : null}
        <label className="form-field">
          <span>{t("variant.priceLabel")}</span>
          <input
            aria-label={t("variant.priceLabel")}
            type="number"
            min="0"
            step="0.01"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
          />
        </label>
        <label className="form-field">
          <span>{t("variant.skuLabel")}</span>
          <input
            aria-label={t("variant.skuLabel")}
            type="text"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
            placeholder={t("variant.skuPlaceholder")}
          />
        </label>
        {axes.map((axis) => (
          <label className="form-field" key={axis.key}>
            <span>{axis.label}</span>
            {axis.type === "enum" ? (
              <select
                aria-label={axis.label}
                value={axisValues[axis.key] ?? ""}
                onChange={(e) =>
                  setAxisValues((prev) => ({ ...prev, [axis.key]: e.target.value }))
                }
              >
                {(axis.options ?? []).map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            ) : (
              <input
                aria-label={axis.label}
                type="text"
                value={axisValues[axis.key] ?? ""}
                onChange={(e) =>
                  setAxisValues((prev) => ({ ...prev, [axis.key]: e.target.value }))
                }
              />
            )}
          </label>
        ))}
        <button
          type="button"
          className="sheet-save-btn"
          onClick={() => void handleSave()}
          disabled={saving || deleting}
        >
          {saving ? t("variant.saving") : t("variant.saveButton")}
        </button>

        <div className="sheet-divider" />

        {/* ── Delete ── */}
        {deleteError ? <p className="error-banner">{deleteError}</p> : null}
        {confirmDelete ? (
          <div className="variant-delete-confirm">
            <p>
              {t("variant.deleteConfirmPrefix")}
              <strong>{axisLabel || `#${variant.id}`}</strong>
              {t("variant.deleteConfirmSuffix")}
            </p>
            <div className="variant-edit-actions">
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                disabled={deleting}
              >
                {t("variant.deleteNo")}
              </button>
              <button
                type="button"
                className="btn-danger"
                onClick={() => void handleDelete()}
                disabled={deleting}
              >
                {deleting ? t("variant.deleting") : t("variant.deleteYes")}
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="btn-danger-outline"
            onClick={() => setConfirmDelete(true)}
            disabled={saving}
          >
            {t("variant.deleteButton")}
          </button>
        )}
      </div>

      {sellReservation ? (
        <ShipSheet
          reservationId={sellReservation.id}
          title={`${productName} (${[axisLabel, `${sellReservation.qty} ${t("common.unitsShort")}`].filter(Boolean).join(", ")})`}
          productName={productName}
          defaultCodAmount={Number(variant.price) * sellReservation.qty}
          onSubmit={onShip}
          onCreateTtn={onCreateTtn}
          onNavigateToSettings={onNavigateToSettings}
          onClose={() => setSellReservation(null)}
        />
      ) : null}
    </>
  );

  return createPortal(sheet, document.body);
}
