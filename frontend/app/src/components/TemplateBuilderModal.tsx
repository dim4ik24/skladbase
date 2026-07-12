import { useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, createTemplate } from "../api";
import type { Template } from "../types";

interface FieldDraft {
  id: string;
  label: string;
  type: "enum" | "string";
  options: string[];
}

interface TemplateBuilderModalProps {
  onSave: (template: Template) => void;
  onClose: () => void;
}

const UKRL: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "h", ґ: "g",
  д: "d", е: "e", є: "ye", ж: "zh", з: "z",
  и: "y", і: "i", ї: "yi", й: "y", к: "k",
  л: "l", м: "m", н: "n", о: "o", п: "p",
  р: "r", с: "s", т: "t", у: "u", ф: "f",
  х: "kh", ц: "ts", ч: "ch", ш: "sh", щ: "shch",
  ь: "", ю: "yu", я: "ya",
  "'": "", "’": "", "ʼ": "",
};

function toKey(label: string, fallback: string, used: Set<string>): string {
  let key = label
    .toLowerCase()
    .split("")
    .map((c) => UKRL[c] ?? (/[a-z0-9]/.test(c) ? c : " "))
    .join("")
    .trim()
    .replace(/\s+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_+/g, "_");
  if (!key || !/^[a-z]/.test(key)) key = fallback;
  if (used.has(key)) {
    let n = 2;
    while (used.has(`${key}_${n}`)) n++;
    key = `${key}_${n}`;
  }
  used.add(key);
  return key;
}

function draftsToSchema(
  axes: FieldDraft[],
  attrs: FieldDraft[],
): Record<string, unknown> {
  const used = new Set<string>();
  const buildField = (d: FieldDraft, fallback: string) => {
    const key = toKey(d.label, fallback, used);
    const f: Record<string, unknown> = { key, label: d.label.trim(), type: d.type };
    if (d.type === "enum") f.options = d.options.filter((o) => o.trim());
    return f;
  };
  return {
    variant_axes: axes.map((d, i) => buildField(d, `axis_${i + 1}`)),
    attributes: attrs.map((d, i) => buildField(d, `attr_${i + 1}`)),
  };
}

function newDraft(): FieldDraft {
  return { id: crypto.randomUUID(), label: "", type: "string", options: [] };
}

function updateField(
  setter: Dispatch<SetStateAction<FieldDraft[]>>,
  idx: number,
  patch: Partial<FieldDraft>,
) {
  setter((prev) => prev.map((f, i) => (i === idx ? { ...f, ...patch } : f)));
}

function removeField(setter: Dispatch<SetStateAction<FieldDraft[]>>, idx: number) {
  setter((prev) => prev.filter((_, i) => i !== idx));
}

function updateOption(
  setter: Dispatch<SetStateAction<FieldDraft[]>>,
  fieldIdx: number,
  optIdx: number,
  value: string,
) {
  setter((prev) =>
    prev.map((f, i) =>
      i === fieldIdx
        ? { ...f, options: f.options.map((o, j) => (j === optIdx ? value : o)) }
        : f,
    ),
  );
}

function addOption(setter: Dispatch<SetStateAction<FieldDraft[]>>, fieldIdx: number) {
  setter((prev) =>
    prev.map((f, i) => (i === fieldIdx ? { ...f, options: [...f.options, ""] } : f)),
  );
}

function removeOption(
  setter: Dispatch<SetStateAction<FieldDraft[]>>,
  fieldIdx: number,
  optIdx: number,
) {
  setter((prev) =>
    prev.map((f, i) =>
      i === fieldIdx ? { ...f, options: f.options.filter((_, j) => j !== optIdx) } : f,
    ),
  );
}

export function TemplateBuilderModal({ onSave, onClose }: TemplateBuilderModalProps) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [axes, setAxes] = useState<FieldDraft[]>([]);
  const [attrs, setAttrs] = useState<FieldDraft[]>([]);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!name.trim()) errs["name"] = t("product.template.nameRequired");
    axes.forEach((f, i) => {
      if (!f.label.trim()) errs[`axis_${i}_label`] = t("product.template.axisNameRequired");
      if (f.type === "enum" && f.options.filter((o) => o.trim()).length === 0)
        errs[`axis_${i}_options`] = t("product.template.optionRequired");
    });
    attrs.forEach((f, i) => {
      if (!f.label.trim()) errs[`attr_${i}_label`] = t("product.template.attrNameRequired");
      if (f.type === "enum" && f.options.filter((o) => o.trim()).length === 0)
        errs[`attr_${i}_options`] = t("product.template.optionRequired");
    });
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function handleSave() {
    if (!validate()) return;
    setSubmitting(true);
    setApiError(null);
    try {
      const schema = draftsToSchema(axes, attrs);
      const created = await createTemplate(name.trim(), schema);
      onSave(created);
    } catch (err) {
      setApiError(err instanceof ApiError ? err.detail : t("product.template.saveFailed"));
    } finally {
      setSubmitting(false);
    }
  }

  function renderField(
    field: FieldDraft,
    idx: number,
    setter: Dispatch<SetStateAction<FieldDraft[]>>,
    prefix: "axis" | "attr",
  ) {
    const labelKey = `${prefix}_${idx}_label`;
    const optionsKey = `${prefix}_${idx}_options`;
    const isAxis = prefix === "axis";

    return (
      <div key={field.id} className="builder-field-card">
        <div className="builder-field-row">
          <input
            className="builder-field-input"
            type="text"
            placeholder={
              isAxis ? t("product.template.axisNamePlaceholder") : t("product.template.attrNamePlaceholder")
            }
            value={field.label}
            onChange={(e) => updateField(setter, idx, { label: e.target.value })}
            aria-label={
              isAxis
                ? t("product.template.axisNameAriaLabel", { n: idx + 1 })
                : t("product.template.attrNameAriaLabel", { n: idx + 1 })
            }
          />
          <select
            value={field.type}
            onChange={(e) => {
              const newType = e.target.value as "enum" | "string";
              updateField(setter, idx, { type: newType, options: newType === "enum" ? [""] : [] });
            }}
          >
            <option value="string">{t("product.template.typeText")}</option>
            <option value="enum">{t("product.template.typeList")}</option>
          </select>
          <button
            type="button"
            className="builder-remove-btn"
            onClick={() => removeField(setter, idx)}
            aria-label={t("product.template.removeFieldAriaLabel")}
          >
            ✕
          </button>
        </div>

        {fieldErrors[labelKey] ? (
          <p className="field-error">{fieldErrors[labelKey]}</p>
        ) : null}

        {field.type === "enum" ? (
          <div className="builder-options">
            {field.options.map((opt, j) => (
              <div key={j} className="builder-option-row">
                <input
                  type="text"
                  className="builder-field-input"
                  placeholder={t("product.template.optionPlaceholder")}
                  value={opt}
                  onChange={(e) => updateOption(setter, idx, j, e.target.value)}
                  aria-label={t("product.template.optionAriaLabel", { n: j + 1 })}
                />
                <button
                  type="button"
                  className="builder-remove-btn"
                  onClick={() => removeOption(setter, idx, j)}
                  aria-label={t("product.template.removeOptionAriaLabel")}
                >
                  ✕
                </button>
              </div>
            ))}
            {fieldErrors[optionsKey] ? (
              <p className="field-error">{fieldErrors[optionsKey]}</p>
            ) : null}
            <button
              type="button"
              className="link-button"
              onClick={() => addOption(setter, idx)}
            >
              {t("product.template.addOption")}
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="builder-overlay" role="presentation" onClick={onClose}>
      <div
        className="builder-card"
        role="dialog"
        aria-modal="true"
        aria-label={t("product.template.title")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="builder-header">
          <h2>{t("product.template.title")}</h2>
          <button
            type="button"
            className="builder-close-btn"
            aria-label={t("common.close")}
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        {apiError ? <p className="error-banner">{apiError}</p> : null}

        <label className="form-field">
          <span>{t("product.template.typeNameLabel")}</span>
          <input
            type="text"
            placeholder={t("product.template.typeNamePlaceholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          {fieldErrors["name"] ? <p className="field-error">{fieldErrors["name"]}</p> : null}
        </label>

        <div className="builder-section">
          <div className="builder-section-header">
            <h3>{t("product.template.axesTitle")}</h3>
            <span className="builder-hint">{t("product.template.axesHint")}</span>
          </div>
          {axes.map((f, i) => renderField(f, i, setAxes, "axis"))}
          <button
            type="button"
            className="link-button"
            onClick={() => setAxes((prev) => [...prev, newDraft()])}
          >
            {t("product.template.addAxis")}
          </button>
        </div>

        <div className="builder-section">
          <div className="builder-section-header">
            <h3>{t("product.template.attrsTitle")}</h3>
            <span className="builder-hint">{t("product.template.attrsHint")}</span>
          </div>
          {attrs.map((f, i) => renderField(f, i, setAttrs, "attr"))}
          <button
            type="button"
            className="link-button"
            onClick={() => setAttrs((prev) => [...prev, newDraft()])}
          >
            {t("product.template.addAttr")}
          </button>
        </div>

        <div className="modal-actions">
          <button type="button" onClick={onClose} disabled={submitting}>
            {t("common.cancel")}
          </button>
          <button type="button" onClick={handleSave} disabled={submitting}>
            {submitting ? t("product.template.saving") : t("product.template.saveButton")}
          </button>
        </div>
      </div>
    </div>
  );
}
