/**
 * InlineEditCard — green-deep блок редагування всередині cream product-card.
 * Інверсний зі scheme: cream картка → dark green edit-zone → cream text.
 */
import type { LucideIcon } from "lucide-react";
import { EditableRow } from "./EditableRow";

export interface InlineEditField {
  key: string;
  icon: LucideIcon;
  label: string;
  value: string;
  multiline?: boolean;
}

interface InlineEditCardProps {
  title: string;
  fields: InlineEditField[];
  onSave: (key: string, value: string) => void;
}

export function InlineEditCard({ title, fields, onSave }: InlineEditCardProps) {
  return (
    <div className="mt-2 rounded-[18px] bg-green-deep p-3">
      <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-cream/50">
        {title}
      </h4>
      <div className="flex flex-col gap-1">
        {fields.map((field) => (
          <EditableRow
            key={field.key}
            icon={field.icon}
            label={field.label}
            value={field.value}
            multiline={field.multiline}
            onSave={(value) => onSave(field.key, value)}
          />
        ))}
      </div>
    </div>
  );
}
