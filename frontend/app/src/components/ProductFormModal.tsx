import { useState } from "react";
import type { FormEvent } from "react";
import { errorMessage } from "../errors";
import type { ProductInput, Template, TemplateField, VariantInput } from "../types";

interface ProductFormModalProps {
  templates: Template[];
  onSubmit: (payload: ProductInput) => Promise<void>;
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
    values[axis.key] = axis.type === "enum" ? axis.options?.[0] ?? "" : "";
  }
  return values;
}

function emptyRow(axes: TemplateField[]): VariantRowState {
  return { axisValues: defaultAxisValues(axes), price: "", onHand: "0", sku: "" };
}

export function ProductFormModal({ templates, onSubmit, onClose }: ProductFormModalProps) {
  const [templateId, setTemplateId] = useState<string>("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [attributeValues, setAttributeValues] = useState<Record<string, string>>({});
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [rows, setRows] = useState<VariantRowState[]>([emptyRow([])]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedTemplate = templates.find((t) => String(t.id) === templateId) ?? null;
  const axes = selectedTemplate?.field_schema.variant_axes ?? [];
  const attributeFields = selectedTemplate?.field_schema.attributes ?? [];

  function handleTemplateChange(value: string) {
    setTemplateId(value);
    const template = templates.find((t) => String(t.id) === value) ?? null;
    setRows([emptyRow(template?.field_schema.variant_axes ?? [])]);
    setAttributeValues({});
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
      await onSubmit(payload);
    } catch (err) {
      setError(errorMessage(err, "Не вдалося створити товар"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="modal-card"
        role="dialog"
        aria-modal="true"
        aria-label="Додати товар"
        onClick={(event) => event.stopPropagation()}
      >
        <h2>Додати товар</h2>
        <form onSubmit={handleSubmit}>
          {error ? <p className="error-banner">{error}</p> : null}

          <label className="form-field">
            <span>Шаблон</span>
            <select
              value={templateId}
              onChange={(event) => handleTemplateChange(event.target.value)}
            >
              <option value="">Без шаблону</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          </label>

          <label className="form-field">
            <span>Назва</span>
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
          </label>

          <label className="form-field">
            <span>Опис</span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
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
                        onChange={(event) =>
                          setAttributeValues((prev) => ({
                            ...prev,
                            [field.key]: event.target.value,
                          }))
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
                      value={row.axisValues[axis.key] ?? ""}
                      onChange={(event) => updateRowAxis(index, axis.key, event.target.value)}
                    >
                      {(axis.options ?? []).map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={row.axisValues[axis.key] ?? ""}
                      onChange={(event) => updateRowAxis(index, axis.key, event.target.value)}
                    />
                  )}
                </label>
              ))}

              <label className="form-field">
                <span>Ціна</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={row.price}
                  onChange={(event) => updateRow(index, { price: event.target.value })}
                  required
                />
              </label>

              <label className="form-field">
                <span>Початковий залишок</span>
                <input
                  type="number"
                  min="0"
                  value={row.onHand}
                  onChange={(event) => updateRow(index, { onHand: event.target.value })}
                />
              </label>

              <label className="form-field">
                <span>SKU</span>
                <input
                  type="text"
                  value={row.sku}
                  onChange={(event) => updateRow(index, { sku: event.target.value })}
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
              {submitting ? "Зберігаємо..." : "Зберегти"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
