/**
 * EditableRow — один рядок інлайн-редагування (іконка + лейбл + поле,
 * перемикач view/edit). Адаптовано з пасти EditableRow (motion/react):
 * прибрано @hugeicons (стандартизація на lucide-react per CLAUDE-бриф),
 * прибрано event-специфічні варіанти (time-range/url) — лишились
 * текстове/multiline поля, потрібні для назви/опису товару.
 */
import { useId, useState } from "react";
import type { LucideIcon } from "lucide-react";
import { Check, Pencil, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import type { Transition } from "motion/react";

interface EditableRowProps {
  icon: LucideIcon;
  label: string;
  value: string;
  multiline?: boolean;
  onSave: (value: string) => void;
}

const spring: Transition = { type: "spring", stiffness: 420, damping: 28, mass: 0.6 };

export function EditableRow({ icon: Icon, label, value, multiline = false, onSave }: EditableRowProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputId = useId();

  function handleSave() {
    onSave(draft);
    setEditing(false);
  }

  function handleCancel() {
    setDraft(value);
    setEditing(false);
  }

  return (
    <motion.div
      layout
      transition={spring}
      className="flex w-full flex-col gap-2 sm:flex-row sm:items-center sm:gap-4"
    >
      <div className="flex w-full shrink-0 items-center gap-2 sm:w-[110px]">
        <Icon size={18} className="text-cream/45" strokeWidth={1.5} />
        <label htmlFor={inputId} className="cursor-pointer text-[13px] font-medium text-cream/60">
          {label}
        </label>
      </div>

      <div className="group/content relative flex min-h-[38px] w-full items-center gap-2 rounded-xl px-2 transition-colors hover:bg-white/[0.03]">
        {multiline ? (
          <textarea
            id={inputId}
            readOnly={!editing}
            rows={2}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="w-full resize-none bg-transparent py-2 text-[14px] font-medium text-cream outline-none"
          />
        ) : (
          <input
            id={inputId}
            type="text"
            readOnly={!editing}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && handleSave()}
            className="h-9 w-full bg-transparent text-[14px] font-medium text-cream outline-none"
          />
        )}

        <div className="flex shrink-0 items-center justify-end">
          <AnimatePresence mode="popLayout" initial={false}>
            {editing ? (
              <motion.div
                key="edit"
                className="flex gap-1"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
                transition={{ duration: 0.2 }}
              >
                <motion.button
                  type="button"
                  whileTap={{ scale: 0.95 }}
                  onClick={handleSave}
                  aria-label={`Зберегти: ${label}`}
                  className="flex size-7 items-center justify-center rounded-lg bg-green text-ink"
                >
                  <Check size={15} />
                </motion.button>
                <motion.button
                  type="button"
                  whileTap={{ scale: 0.95 }}
                  onClick={handleCancel}
                  aria-label={`Скасувати: ${label}`}
                  className="flex size-7 items-center justify-center rounded-lg bg-ink-2 text-cream"
                >
                  <X size={15} />
                </motion.button>
              </motion.div>
            ) : (
              <motion.button
                key="view"
                type="button"
                exit={{ opacity: 0 }}
                onClick={() => setEditing(true)}
                aria-label={`Редагувати: ${label}`}
                className="flex size-7 items-center justify-center rounded-lg border border-[var(--line)] opacity-0 transition-opacity group-hover/content:opacity-100"
              >
                <Pencil size={14} className="text-cream/60" />
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}
