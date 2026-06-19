/**
 * InlineEditCard — картка з рядками EditableRow. Адаптовано з пасти
 * InlineEditCard (motion/react): узагальнено під довільний список полів
 * (раніше — жорстко event/date/time/url), бо тут редагуємо назву/опис
 * товару через наявний `api.updateProduct`, нових мутацій не вигадуємо.
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
    <div className="mt-2 rounded-[22px] border border-[var(--line)] bg-[var(--panel)] p-1.5 backdrop-blur-xl">
      <div className="rounded-[18px] border border-[var(--line)] bg-ink-2/60 px-3 py-3">
        <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-cream/45">
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
    </div>
  );
}
