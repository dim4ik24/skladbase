import { useEffect, useState } from "react";
import * as api from "../api";
import { errorMessage } from "../errors";
import { shareInviteLink } from "../telegram";
import type { Invite, PermissionsPatch, TeamMember } from "../types";

const SHARE_TEXT = "Приєднуйся до мого магазину в SkladBase";

const PERMISSION_FIELDS: Array<{ key: keyof PermissionsPatch; label: string }> = [
  { key: "can_view_inventory", label: "Перегляд складу" },
  { key: "can_edit_products", label: "Редагування товарів" },
  { key: "can_manage_reservations", label: "Резерви й замовлення" },
  { key: "can_manage_stock", label: "Рух складу (прихід/списання)" },
  { key: "can_view_finance", label: "Фінанси" },
  { key: "can_manage_billing", label: "Оплата й тариф" },
];

function hoursLeft(expiresAt: string): number {
  const ms = new Date(expiresAt).getTime() - Date.now();
  return Math.max(0, Math.round(ms / (60 * 60 * 1000)));
}

export function TeamSection() {
  const [invites, setInvites] = useState<Invite[]>([]);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newInvite, setNewInvite] = useState<Invite | null>(null);
  const [confirmRevokeId, setConfirmRevokeId] = useState<number | null>(null);
  const [confirmRemoveId, setConfirmRemoveId] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const [invitesResult, membersResult] = await Promise.all([
          api.listInvites(),
          api.listMembers(),
        ]);
        if (!mounted) return;
        setInvites(invitesResult);
        setMembers(membersResult);
      } catch (err) {
        if (!mounted) return;
        setError(errorMessage(err, "Не вдалося завантажити команду"));
      } finally {
        if (mounted) setLoading(false);
      }
    }
    void load();
    return () => {
      mounted = false;
    };
  }, []);

  async function handleCreateInvite() {
    setError(null);
    setCreating(true);
    try {
      const invite = await api.createInvite();
      setNewInvite(invite);
      setInvites((prev) => [invite, ...prev]);
    } catch (err) {
      setError(errorMessage(err, "Не вдалося створити запрошення"));
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(id: number) {
    setError(null);
    try {
      await api.revokeInvite(id);
      setInvites((prev) => prev.filter((inv) => inv.id !== id));
      setNewInvite((prev) => (prev?.id === id ? null : prev));
    } catch (err) {
      setError(errorMessage(err, "Не вдалося скасувати запрошення"));
    } finally {
      setConfirmRevokeId(null);
    }
  }

  async function handleRemoveMember(id: number) {
    setError(null);
    try {
      await api.removeMember(id);
      setMembers((prev) => prev.filter((m) => m.id !== id));
      setExpandedId((prev) => (prev === id ? null : prev));
    } catch (err) {
      setError(errorMessage(err, "Не вдалося видалити учасника"));
    } finally {
      setConfirmRemoveId(null);
    }
  }

  async function handlePermissionChange(
    memberId: number,
    field: keyof PermissionsPatch,
    value: boolean,
  ) {
    setError(null);
    const previous = members.find((m) => m.id === memberId)?.[field];
    setMembers((prev) =>
      prev.map((m) => (m.id === memberId ? { ...m, [field]: value } : m)),
    );
    try {
      await api.updateMemberPermissions(memberId, { [field]: value });
    } catch (err) {
      setMembers((prev) =>
        prev.map((m) => (m.id === memberId ? { ...m, [field]: previous ?? !value } : m)),
      );
      setError(errorMessage(err, "Не вдалося оновити дозвіл"));
    }
  }

  function handleShare(url: string) {
    shareInviteLink(url, SHARE_TEXT);
  }

  function handleCopy(url: string) {
    void navigator.clipboard?.writeText(url);
  }

  return (
    <div className="glass-card rounded-[20px] p-4 shadow-[var(--shadow-card)]">
      <h3 className="text-sm font-bold text-text-soft uppercase tracking-wide mb-3">Команда</h3>

      {error ? <p className="error-banner">{error}</p> : null}

      <button
        type="button"
        disabled={creating}
        onClick={() => void handleCreateInvite()}
        className="w-full rounded-2xl py-2.5 text-sm font-bold text-white disabled:opacity-50"
        style={{
          background: "linear-gradient(135deg, var(--green) 0%, var(--green-deep) 100%)",
          boxShadow: "var(--shadow-cta)",
        }}
      >
        {creating ? "Створюємо…" : "Запросити людину"}
      </button>

      {newInvite ? (
        <div className="mt-3 flex flex-col gap-2">
          <input
            readOnly
            value={newInvite.url}
            onFocus={(e) => e.target.select()}
            className="rounded-xl px-3 py-2 text-xs bg-[var(--glass-bg)] border border-[var(--line)] text-text"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => handleCopy(newInvite.url)}
              className="flex-1 rounded-xl px-3 py-1.5 text-xs font-semibold text-green-deep border border-[var(--green)]"
            >
              Копіювати
            </button>
            <button
              type="button"
              onClick={() => handleShare(newInvite.url)}
              className="flex-1 rounded-xl px-3 py-1.5 text-xs font-semibold text-white"
              style={{
                background: "linear-gradient(135deg, var(--green) 0%, var(--green-deep) 100%)",
              }}
            >
              Поділитись
            </button>
          </div>
        </div>
      ) : null}

      {loading ? (
        <p className="status-text">Завантаження…</p>
      ) : (
        <>
          {invites.length > 0 ? (
            <ul className="mt-4 flex flex-col gap-2">
              {invites.map((invite) => (
                <li
                  key={invite.id}
                  className="flex items-center justify-between gap-2 rounded-xl px-3 py-2 bg-[var(--glass-bg)] border border-[var(--line)]"
                >
                  <span className="text-xs text-text-soft">
                    Діє ще {hoursLeft(invite.expires_at)} год
                  </span>
                  {confirmRevokeId === invite.id ? (
                    <div className="flex gap-2 shrink-0">
                      <button type="button" onClick={() => setConfirmRevokeId(null)}>
                        Ні
                      </button>
                      <button
                        type="button"
                        className="btn-danger"
                        onClick={() => void handleRevoke(invite.id)}
                      >
                        Так, скасувати
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="btn-danger-outline shrink-0"
                      onClick={() => setConfirmRevokeId(invite.id)}
                    >
                      Скасувати
                    </button>
                  )}
                </li>
              ))}
            </ul>
          ) : null}

          <ul className="mt-4 flex flex-col gap-2">
            {members.map((member) => {
              const isOwner = member.role === "owner";
              const isExpanded = expandedId === member.id;
              return (
                <li
                  key={member.id}
                  className="rounded-xl bg-[var(--glass-bg)] border border-[var(--line)] overflow-hidden"
                >
                  <div
                    role={isOwner ? undefined : "button"}
                    tabIndex={isOwner ? undefined : 0}
                    onClick={() => {
                      if (isOwner) return;
                      setExpandedId((prev) => (prev === member.id ? null : member.id));
                    }}
                    className={`flex items-center justify-between gap-2 px-3 py-2 ${
                      isOwner ? "" : "cursor-pointer"
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="text-sm text-text truncate">
                        {member.display_name ?? String(member.tg_id)}
                      </p>
                      <p className="text-xs text-text-soft">
                        {isOwner ? "Власник" : "Менеджер"}
                      </p>
                    </div>
                    {!isOwner ? (
                      confirmRemoveId === member.id ? (
                        <div
                          className="flex gap-2 shrink-0"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button type="button" onClick={() => setConfirmRemoveId(null)}>
                            Ні
                          </button>
                          <button
                            type="button"
                            className="btn-danger"
                            onClick={() => void handleRemoveMember(member.id)}
                          >
                            Так, видалити
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          className="btn-danger-outline shrink-0"
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmRemoveId(member.id);
                          }}
                        >
                          Видалити
                        </button>
                      )
                    ) : null}
                  </div>

                  {!isOwner && isExpanded ? (
                    <div className="flex flex-col gap-2 px-3 pb-3 pt-2 border-t border-[var(--line)]">
                      {PERMISSION_FIELDS.map((field) => (
                        <label
                          key={field.key}
                          className="flex items-center gap-2 text-sm text-text"
                        >
                          <input
                            type="checkbox"
                            checked={member[field.key]}
                            onChange={(e) =>
                              void handlePermissionChange(member.id, field.key, e.target.checked)
                            }
                          />
                          {field.label}
                        </label>
                      ))}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
