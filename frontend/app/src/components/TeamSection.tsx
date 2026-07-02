import { useEffect, useState } from "react";
import * as api from "../api";
import { errorMessage } from "../errors";
import { shareInviteLink } from "../telegram";
import type { Invite, TeamMember } from "../types";

const SHARE_TEXT = "Приєднуйся до мого магазину в SkladBase";

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
    } catch (err) {
      setError(errorMessage(err, "Не вдалося видалити учасника"));
    } finally {
      setConfirmRemoveId(null);
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
            {members.map((member) => (
              <li
                key={member.id}
                className="flex items-center justify-between gap-2 rounded-xl px-3 py-2 bg-[var(--glass-bg)] border border-[var(--line)]"
              >
                <div className="min-w-0">
                  <p className="text-sm text-text truncate">
                    {member.display_name ?? String(member.tg_id)}
                  </p>
                  <p className="text-xs text-text-soft">
                    {member.role === "owner" ? "Власник" : "Менеджер"}
                  </p>
                </div>
                {member.role !== "owner" ? (
                  confirmRemoveId === member.id ? (
                    <div className="flex gap-2 shrink-0">
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
                      onClick={() => setConfirmRemoveId(member.id)}
                    >
                      Видалити
                    </button>
                  )
                ) : null}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
