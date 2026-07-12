import { useState } from "react";
import { createPortal } from "react-dom";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../errors";
import type { NotPickedUpPayload, NotPickedUpReason } from "../types";

interface NotPickedUpSheetProps {
  reservationId: number;
  title: string;
  onSubmit: (reservationId: number, payload: NotPickedUpPayload) => Promise<void>;
  onClose: () => void;
}

const REASONS: { value: NotPickedUpReason; labelKey: string }[] = [
  { value: "did_not_pick_up", labelKey: "reasons.didNotPickUp" },
  { value: "refused", labelKey: "reasons.refused" },
  { value: "other", labelKey: "reasons.otherWithEmoji" },
];

export function NotPickedUpSheet({
  reservationId,
  title,
  onSubmit,
  onClose,
}: NotPickedUpSheetProps) {
  const { t } = useTranslation();
  const [isClosing, setIsClosing] = useState(false);
  const [reason, setReason] = useState<NotPickedUpReason | null>(null);
  const [comment, setComment] = useState("");
  const [commentMissing, setCommentMissing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleClose() {
    setIsClosing(true);
    setTimeout(onClose, 250);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!reason) {
      setError(t("reservations.notPickedUp.reasonMissing"));
      return;
    }
    const trimmedComment = comment.trim();
    if (reason === "other" && !trimmedComment) {
      setCommentMissing(true);
      return;
    }
    setCommentMissing(false);

    setSubmitting(true);
    try {
      await onSubmit(reservationId, {
        reason,
        comment: trimmedComment || undefined,
      });
      handleClose();
    } catch (err) {
      setError(errorMessage(err, t("reservations.notPickedUp.failed")));
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
        aria-label={t("reservations.notPickedUp.ariaLabel", { title })}
        className={`variant-sheet${isClosing ? " variant-sheet--closing" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-header">
          <span className="sheet-axis-label release-sheet-title">
            {t("reservations.notPickedUp.prompt", { title })}
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

        <form onSubmit={handleSubmit}>
          {error ? <p className="error-banner">{error}</p> : null}

          <div
            className="write-off-reasons"
            role="group"
            aria-label={t("reservations.notPickedUp.reasonGroupAriaLabel")}
          >
            {REASONS.map((r) => (
              <button
                key={r.value}
                type="button"
                className={`write-off-reason-chip${
                  reason === r.value ? " write-off-reason-chip--active" : ""
                }`}
                aria-pressed={reason === r.value}
                onClick={() => setReason(r.value)}
              >
                {t(r.labelKey)}
              </button>
            ))}
          </div>

          {reason === "other" ? (
            <label className="form-field">
              <span>{t("reservations.commentLabel")}</span>
              <input
                type="text"
                value={comment}
                onChange={(event) => {
                  setComment(event.target.value);
                  setCommentMissing(false);
                }}
                aria-invalid={commentMissing}
                className={commentMissing ? "field-invalid" : undefined}
              />
            </label>
          ) : null}

          <div className="modal-actions">
            <button type="button" onClick={handleClose} disabled={submitting}>
              {t("common.cancel")}
            </button>
            <button type="submit" disabled={submitting}>
              {submitting ? t("reservations.notPickedUp.submitting") : t("common.confirm")}
            </button>
          </div>
        </form>
      </div>
    </>
  );

  return createPortal(sheet, document.body);
}
