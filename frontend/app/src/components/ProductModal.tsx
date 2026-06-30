import { useState } from "react";
import { createPortal } from "react-dom";
import type { FormEvent } from "react";
import { ApiError } from "../api";
import { errorMessage } from "../errors";
import type { Product, ProductInput, ProductPatch, ReserveInput, Template, TemplateField, Variant, VariantAddPayload, VariantInput, VariantPatchPayload } from "../types";
import { Panel } from "./ui/Panel";
import { ProductPhotoGallery } from "./ProductPhotoGallery";
import { TemplateBuilderModal } from "./TemplateBuilderModal";
import { VariantRow } from "./VariantRow";

interface ProductModalProps {
  product: Product | null;
  products: Product[];
  templates: Template[];
  photosAllowed: boolean;
  isOwner?: boolean;
  onTemplateAdded?: (template: Template) => void;
  onCreateProduct: (payload: ProductInput) => Promise<Product>;
  onUpdateProduct: (id: number, patch: ProductPatch) => Promise<void>;
  onUploadProductPhoto: (productId: number, file: File) => Promise<void>;
  onDeleteProductPhoto: (productId: number, photoId: number) => Promise<void>;
  onRestock: (variantId: number, qty: number) => void;
  onAdjust: (variantId: number, newOnHand: number) => void;
  onUploadPhoto: (variantId: number, file: File) => Promise<void>;
  onReserve: (variantId: number, payload: ReserveInput) => Promise<void>;
  onPatchVariant: (variantId: number, patch: VariantPatchPayload) => Promise<void>;
  onAddVariant: (productId: number, payload: VariantAddPayload) => Promise<Variant>;
  onDeleteVariant: (variantId: number) => Promise<void>;
  onFrozenAction?: () => void;
  onClose: () => void;
}

interface VariantRowState {
  axisValues: Record<string, string>;
  price: string;
  onHand: string;
  sku: string;
}

function defaultAxisValues(axes: TemplateField[]): Record<string, string> {
  const values: Record<string, string> = {};
  for (const axis of axes) {
    values[axis.key] = axis.type === "enum" ? (axis.options?.[0] ?? "") : "";
  }
  return values;
}

function emptyRow(axes: TemplateField[]): VariantRowState {
  return { axisValues: defaultAxisValues(axes), price: "", onHand: "0", sku: "" };
}

// ─── Create mode ─────────────────────────────────────────────────────────────

interface CreateFormProps {
  templates: Template[];
  isOwner?: boolean;
  onTemplateAdded?: (template: Template) => void;
  onCreated: (product: Product) => void;
  onCreateProduct: (payload: ProductInput) => Promise<Product>;
  onClose: () => void;
}

function CreateForm({
  templates,
  isOwner,
  onTemplateAdded,
  onCreated,
  onCreateProduct,
  onClose,
}: CreateFormProps) {
  const [templateId, setTemplateId] = useState<string>("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [attributeValues, setAttributeValues] = useState<Record<string, string>>({});
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [rows, setRows] = useState<VariantRowState[]>([emptyRow([])]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localTemplates, setLocalTemplates] = useState<Template[]>(templates);
  const [showBuilder, setShowBuilder] = useState(false);

  const selectedTemplate = localTemplates.find((t) => String(t.id) === templateId) ?? null;
  const axes = selectedTemplate?.field_schema.variant_axes ?? [];
  const attributeFields = selectedTemplate?.field_schema.attributes ?? [];

  function handleTemplateChange(value: string) {
    setTemplateId(value);
    const template = localTemplates.find((t) => String(t.id) === value) ?? null;
    setRows([emptyRow(template?.field_schema.variant_axes ?? [])]);
    setAttributeValues({});
  }

  function handleBuilderSave(template: Template) {
    setLocalTemplates((prev) => [...prev, template]);
    setTemplateId(String(template.id));
    setRows([emptyRow(template.field_schema.variant_axes)]);
    setAttributeValues({});
    setShowBuilder(false);
    onTemplateAdded?.(template);
  }

  function updateRow(index: number, patch: Partial<VariantRowState>) {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function updateRowAxis(index: number, axisKey: string, value: string) {
    setRows((prev) =>
      prev.map((row, i) =>
        i === index ? { ...row, axisValues: { ...row.axisValues, [axisKey]: value } } : row,
      ),
    );
  }

  function addRow() {
    setRows((prev) => [...prev, emptyRow(axes)]);
  }

  function removeRow(index: number) {
    setRows((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError("Вкажіть назву товару");
      return;
    }
    if (rows.some((row) => !row.price.trim())) {
      setError("Вкажіть ціну для кожного варіанта");
      return;
    }

    const variants: VariantInput[] = rows.map((row) => ({
      axis_values: row.axisValues,
      price: row.price.trim(),
      sku: row.sku.trim() || undefined,
      on_hand: row.onHand.trim() === "" ? 0 : Number(row.onHand),
    }));

    const payload: ProductInput = {
      name: name.trim(),
      description: description.trim() || undefined,
      template_id: selectedTemplate ? selectedTemplate.id : undefined,
      attributes: attributeValues,
      variants,
    };

    setSubmitting(true);
    try {
      const product = await onCreateProduct(payload);
      // Transition to Phase 2 ONLY on success:
      onCreated(product);
    } catch (err) {
      // 402 already handled by App (setUpgradePrompt); show other errors inline.
      if (!(err instanceof ApiError && err.status === 402)) {
        setError(errorMessage(err, "Не вдалося створити товар"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <h2>Додати товар</h2>
      <form onSubmit={handleSubmit}>
        {error ? <p className="error-banner">{error}</p> : null}

        <label className="form-field">
          <span>Шаблон</span>
          <select
            aria-label="Шаблон"
            value={templateId}
            onChange={(e) => handleTemplateChange(e.target.value)}
          >
            <option value="">Без шаблону</option>
            {localTemplates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>

        {isOwner ? (
          <button type="button" className="link-button" onClick={() => setShowBuilder(true)}>
            + Створити свій тип
          </button>
        ) : null}

        <label className="form-field">
          <span>Назва</span>
          <input
            aria-label="Назва"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>

        <label className="form-field">
          <span>Опис</span>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>

        {attributeFields.length > 0 ? (
          <>
            <button
              type="button"
              className="link-button"
              onClick={() => setShowAdvanced((prev) => !prev)}
            >
              {showAdvanced ? "Сховати додатково" : "Додатково"}
            </button>
            {showAdvanced ? (
              <div className="advanced-fields">
                {attributeFields.map((field) => (
                  <label className="form-field" key={field.key}>
                    <span>{field.label}</span>
                    <input
                      type="text"
                      value={attributeValues[field.key] ?? ""}
                      onChange={(e) =>
                        setAttributeValues((prev) => ({ ...prev, [field.key]: e.target.value }))
                      }
                    />
                  </label>
                ))}
              </div>
            ) : null}
          </>
        ) : null}

        <h3>Варіанти</h3>
        {rows.map((row, index) => (
          <div className="variant-builder-row" key={index}>
            {axes.map((axis) => (
              <label className="form-field" key={axis.key}>
                <span>{axis.label}</span>
                {axis.type === "enum" ? (
                  <select
                    aria-label={axis.label}
                    value={row.axisValues[axis.key] ?? ""}
                    onChange={(e) => updateRowAxis(index, axis.key, e.target.value)}
                  >
                    {(axis.options ?? []).map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    aria-label={axis.label}
                    value={row.axisValues[axis.key] ?? ""}
                    onChange={(e) => updateRowAxis(index, axis.key, e.target.value)}
                  />
                )}
              </label>
            ))}

            <label className="form-field">
              <span>Ціна</span>
              <input
                aria-label="Ціна"
                type="number"
                min="0"
                step="0.01"
                value={row.price}
                onChange={(e) => updateRow(index, { price: e.target.value })}
                required
              />
            </label>

            <label className="form-field">
              <span>Початковий залишок</span>
              <input
                aria-label="Початковий залишок"
                type="number"
                min="0"
                value={row.onHand}
                onChange={(e) => updateRow(index, { onHand: e.target.value })}
              />
            </label>

            <label className="form-field">
              <span>SKU</span>
              <input
                type="text"
                value={row.sku}
                onChange={(e) => updateRow(index, { sku: e.target.value })}
              />
            </label>

            {axes.length > 0 && rows.length > 1 ? (
              <button type="button" className="link-button" onClick={() => removeRow(index)}>
                Видалити варіант
              </button>
            ) : null}
          </div>
        ))}

        {axes.length > 0 ? (
          <button type="button" className="link-button" onClick={addRow}>
            + Додати варіант
          </button>
        ) : null}

        <div className="modal-actions">
          <button type="button" onClick={onClose} disabled={submitting}>
            Скасувати
          </button>
          <button type="submit" disabled={submitting}>
            {submitting ? "Створюємо..." : "Створити"}
          </button>
        </div>
      </form>

      {showBuilder
        ? createPortal(
            <TemplateBuilderModal
              onSave={handleBuilderSave}
              onClose={() => setShowBuilder(false)}
            />,
            document.body,
          )
        : null}
    </>
  );
}

// ─── Edit mode ────────────────────────────────────────────────────────────────

type EditTab = "variants" | "info" | "photo";

interface EditFormProps {
  product: Product;
  templates: Template[];
  photosAllowed: boolean;
  onUpdateProduct: (id: number, patch: ProductPatch) => Promise<void>;
  onUploadProductPhoto: (productId: number, file: File) => Promise<void>;
  onDeleteProductPhoto: (productId: number, photoId: number) => Promise<void>;
  onRestock: (variantId: number, qty: number) => void;
  onAdjust: (variantId: number, newOnHand: number) => void;
  onUploadPhoto: (variantId: number, file: File) => Promise<void>;
  onReserve: (variantId: number, payload: ReserveInput) => Promise<void>;
  onPatchVariant: (variantId: number, patch: VariantPatchPayload) => Promise<void>;
  onAddVariant: (productId: number, payload: VariantAddPayload) => Promise<Variant>;
  onDeleteVariant: (variantId: number) => Promise<void>;
  onFrozenAction?: () => void;
  onClose: () => void;
}

function EditForm({
  product,
  templates,
  photosAllowed,
  onUpdateProduct,
  onUploadProductPhoto,
  onDeleteProductPhoto,
  onRestock,
  onAdjust,
  onUploadPhoto,
  onReserve,
  onPatchVariant,
  onAddVariant,
  onDeleteVariant,
  onFrozenAction,
  onClose,
}: EditFormProps) {
  const [tab, setTab] = useState<EditTab>("variants");
  const [name, setName] = useState(product.name);
  const [description, setDescription] = useState(product.description ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addingVariant, setAddingVariant] = useState(false);
  const [justAddedId, setJustAddedId] = useState<number | null>(null);

  const axes: TemplateField[] =
    templates.find((t) => t.id === product.template_id)?.field_schema.variant_axes ?? [];

  async function handleSave() {
    setError(null);
    if (!name.trim()) {
      setError("Вкажіть назву товару");
      return;
    }
    setSaving(true);
    try {
      await onUpdateProduct(product.id, {
        name: name.trim(),
        description: description.trim() || null,
      });
      onClose();
    } catch (err) {
      setError(errorMessage(err, "Не вдалося зберегти"));
    } finally {
      setSaving(false);
    }
  }

  async function handleAddVariant() {
    setAddingVariant(true);
    try {
      const last = product.variants.at(-1);
      const payload: VariantAddPayload = {
        price: last?.price ?? "0",
        axis_values: { ...(last?.axis_values ?? {}) },
      };
      const newVariant = await onAddVariant(product.id, payload);
      setJustAddedId(newVariant.id);
    } finally {
      setAddingVariant(false);
    }
  }

  return (
    <>
      <h2>Редагувати товар</h2>

      <div className="modal-tabs" role="tablist">
        {(["variants", "info", "photo"] as EditTab[]).map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            className={`modal-tab${tab === t ? " modal-tab--active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t === "variants" ? "Варіанти" : t === "info" ? "Інфо" : "Фото"}
          </button>
        ))}
      </div>

      {tab === "variants" ? (
        <>
          <ul className="variant-list">
            {product.variants.map((variant) => (
              <VariantRow
                key={variant.id}
                variant={variant}
                axes={axes}
                autoOpenEdit={justAddedId === variant.id}
                isFrozen={product.is_frozen}
                onFrozenAction={onFrozenAction}
                onRestock={onRestock}
                onAdjust={onAdjust}
                onUploadPhoto={onUploadPhoto}
                onReserve={onReserve}
                onPatchVariant={onPatchVariant}
                onDeleteVariant={onDeleteVariant}
              />
            ))}
          </ul>
          <button
            type="button"
            className="link-button"
            disabled={addingVariant}
            onClick={() => void handleAddVariant()}
          >
            {addingVariant ? "Додаємо..." : "+ Додати варіант"}
          </button>
        </>
      ) : tab === "info" ? (
        <>
          {error ? <p className="error-banner">{error}</p> : null}
          <label className="form-field">
            <span>Назва</span>
            <input
              aria-label="Назва"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="form-field">
            <span>Опис</span>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
        </>
      ) : (
        <ProductPhotoGallery
          product={product}
          photosAllowed={photosAllowed}
          onUpload={(file) => onUploadProductPhoto(product.id, file)}
          onDelete={(photoId) => onDeleteProductPhoto(product.id, photoId)}
        />
      )}

      <div className="modal-actions">
        <button type="button" onClick={onClose} disabled={saving}>
          Закрити
        </button>
        {tab === "info" ? (
          <button type="button" onClick={() => void handleSave()} disabled={saving}>
            {saving ? "Зберігаємо..." : "Зберегти"}
          </button>
        ) : null}
      </div>
    </>
  );
}

// ─── Unified modal shell ──────────────────────────────────────────────────────

export function ProductModal({
  product,
  products,
  templates,
  photosAllowed,
  isOwner,
  onTemplateAdded,
  onCreateProduct,
  onUpdateProduct,
  onUploadProductPhoto,
  onDeleteProductPhoto,
  onRestock,
  onAdjust,
  onUploadPhoto,
  onReserve,
  onPatchVariant,
  onAddVariant,
  onDeleteVariant,
  onFrozenAction,
  onClose,
}: ProductModalProps) {
  const [createdProduct, setCreatedProduct] = useState<Product | null>(null);

  const isPhase2 = createdProduct !== null;

  // Always read the live version from App.products so gallery updates instantly after upload/delete.
  const targetId = createdProduct?.id ?? product?.id ?? null;
  const liveProduct =
    targetId !== null
      ? (products.find((p) => p.id === targetId) ?? createdProduct ?? product)
      : null;

  return (
    <div className="modal-overlay" role="presentation" onClick={isPhase2 ? undefined : onClose}>
      <Panel
        className="modal-card"
        role="dialog"
        aria-modal="true"
        aria-label={product ? "Редагувати товар" : "Додати товар"}
        onClick={(e) => e.stopPropagation()}
      >
        {product !== null && liveProduct !== null ? (
          // Edit mode — product exists, show tabs: Варіанти / Інфо / Фото
          <EditForm
            product={liveProduct}
            templates={templates}
            photosAllowed={photosAllowed}
            onUpdateProduct={onUpdateProduct}
            onUploadProductPhoto={onUploadProductPhoto}
            onDeleteProductPhoto={onDeleteProductPhoto}
            onRestock={onRestock}
            onAdjust={onAdjust}
            onUploadPhoto={onUploadPhoto}
            onReserve={onReserve}
            onPatchVariant={onPatchVariant}
            onAddVariant={onAddVariant}
            onDeleteVariant={onDeleteVariant}
            onFrozenAction={onFrozenAction}
            onClose={onClose}
          />
        ) : isPhase2 && liveProduct !== null ? (
          // Create mode Phase 2 — product created, upload photos
          <>
            <p className="product-modal-success">✓ Товар створено!</p>
            <ProductPhotoGallery
              product={liveProduct}
              photosAllowed={photosAllowed}
              onUpload={(file) => onUploadProductPhoto(liveProduct.id, file)}
              onDelete={(photoId) => onDeleteProductPhoto(liveProduct.id, photoId)}
            />
            <div className="modal-actions">
              <button type="button" onClick={onClose}>
                Готово
              </button>
            </div>
          </>
        ) : (
          // Create mode Phase 1 — empty form
          <CreateForm
            templates={templates}
            isOwner={isOwner}
            onTemplateAdded={onTemplateAdded}
            onCreated={(p) => setCreatedProduct(p)}
            onCreateProduct={onCreateProduct}
            onClose={onClose}
          />
        )}
      </Panel>
    </div>
  );
}
