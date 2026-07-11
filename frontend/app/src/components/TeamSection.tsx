import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import * as api from "../api";
import { ApiError } from "../api";
import { errorMessage } from "../errors";
import { shareInviteLink } from "../telegram";
import type { Invite, Role, RolePermissions, TeamMember } from "../types";

const SHARE_TEXT = "Приєднуйся до мого магазину в SkladBase";

const PERMISSION_FIELDS: Array<{ key: keyof RolePermissions; label: string }> = [
  { key: "can_view_inventory", label: "Перегляд складу" },
  { key: "can_edit_products", label: "Редагування товарів" },
  { key: "can_manage_reservations", label: "Резерви й замовлення" },
  { key: "can_manage_stock", label: "Рух складу (прихід/списання)" },
  { key: "can_view_finance", label: "Фінанси" },
  { key: "can_manage_billing", label: "Оплата й тариф" },
];

const DEFAULT_ROLE_PERMS: RolePermissions = {
  can_view_inventory: true,
  can_edit_products: true,
  can_manage_reservations: true,
  can_manage_stock: true,
  can_view_finance: true,
  can_manage_billing: true,
};

function hoursLeft(expiresAt: string): number {
  const ms = new Date(expiresAt).getTime() - Date.now();
  return Math.max(0, Math.round(ms / (60 * 60 * 1000)));
}

// Українська плюралізація: 1 учасник / 2-4 учасники / 5+ (і 11-14) учасників.
function membersCountLabel(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return `${count} учасник`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} учасники`;
  return `${count} учасників`;
}

export function TeamSection() {
  const [invites, setInvites] = useState<Invite[]>([]);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newInvite, setNewInvite] = useState<Invite | null>(null);
  const [confirmRevokeId, setConfirmRevokeId] = useState<number | null>(null);
  const [confirmRemoveId, setConfirmRemoveId] = useState<number | null>(null);
  const [expandedMemberId, setExpandedMemberId] = useState<number | null>(null);

  const [showCreateRole, setShowCreateRole] = useState(false);
  const [newRoleName, setNewRoleName] = useState("");
  const [newRolePerms, setNewRolePerms] = useState<RolePermissions>(DEFAULT_ROLE_PERMS);
  const [creatingRole, setCreatingRole] = useState(false);
  const [roleFormError, setRoleFormError] = useState<string | null>(null);
  const [expandedRoleId, setExpandedRoleId] = useState<number | null>(null);
  const [roleNameDraft, setRoleNameDraft] = useState("");
  const [confirmDeleteRoleId, setConfirmDeleteRoleId] = useState<number | null>(null);
  const [systemRoleHint, setSystemRoleHint] = useState(false);

  useEffect(() => {
    if (!systemRoleHint) return;
    const timer = setTimeout(() => setSystemRoleHint(false), 3000);
    return () => clearTimeout(timer);
  }, [systemRoleHint]);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const [invitesResult, membersResult, rolesResult] = await Promise.all([
          api.listInvites(),
          api.listMembers(),
          api.getRoles(),
        ]);
        if (!mounted) return;
        setInvites(invitesResult);
        setMembers(membersResult);
        setRoles(rolesResult);
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
      setExpandedMemberId((prev) => (prev === id ? null : prev));
    } catch (err) {
      setError(errorMessage(err, "Не вдалося видалити учасника"));
    } finally {
      setConfirmRemoveId(null);
    }
  }

  async function handleMemberRoleChange(memberId: number, roleId: number) {
    setError(null);
    const previous = members.find((m) => m.id === memberId);
    const nextRole = roles.find((r) => r.id === roleId);
    if (!previous || !nextRole) return;
    setMembers((prev) =>
      prev.map((m) =>
        m.id === memberId
          ? {
              ...m,
              role_id: nextRole.id,
              role_name: nextRole.name,
              can_view_inventory: nextRole.can_view_inventory,
              can_edit_products: nextRole.can_edit_products,
              can_manage_reservations: nextRole.can_manage_reservations,
              can_manage_stock: nextRole.can_manage_stock,
              can_view_finance: nextRole.can_view_finance,
              can_manage_billing: nextRole.can_manage_billing,
            }
          : m,
      ),
    );
    try {
      const updated = await api.setMemberRole(memberId, roleId);
      setMembers((prev) => prev.map((m) => (m.id === memberId ? updated : m)));
    } catch (err) {
      setMembers((prev) => prev.map((m) => (m.id === memberId ? previous : m)));
      setError(errorMessage(err, "Не вдалося змінити роль"));
    }
  }

  function toggleNewRolePerm(key: keyof RolePermissions, value: boolean) {
    setNewRolePerms((prev) => ({ ...prev, [key]: value }));
  }

  async function handleCreateRoleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!newRoleName.trim()) return;
    setRoleFormError(null);
    setCreatingRole(true);
    try {
      const role = await api.createRole({ name: newRoleName.trim(), ...newRolePerms });
      setRoles((prev) => [...prev, role]);
      setShowCreateRole(false);
      setNewRoleName("");
      setNewRolePerms(DEFAULT_ROLE_PERMS);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setRoleFormError("Роль з такою назвою вже є");
      } else {
        setRoleFormError(errorMessage(err, "Не вдалося створити роль"));
      }
    } finally {
      setCreatingRole(false);
    }
  }

  async function handleRolePermToggle(
    roleId: number,
    field: keyof RolePermissions,
    value: boolean,
  ) {
    setError(null);
    const previous = roles.find((r) => r.id === roleId);
    if (!previous) return;
    setRoles((prev) => prev.map((r) => (r.id === roleId ? { ...r, [field]: value } : r)));
    try {
      await api.patchRole(roleId, { [field]: value });
    } catch (err) {
      setRoles((prev) => prev.map((r) => (r.id === roleId ? previous : r)));
      setError(errorMessage(err, "Не вдалося оновити роль"));
    }
  }

  async function handleRoleNameCommit(roleId: number) {
    const previous = roles.find((r) => r.id === roleId);
    const trimmed = roleNameDraft.trim();
    if (!previous || !trimmed || trimmed === previous.name) return;
    setError(null);
    setRoles((prev) => prev.map((r) => (r.id === roleId ? { ...r, name: trimmed } : r)));
    try {
      await api.patchRole(roleId, { name: trimmed });
    } catch (err) {
      setRoles((prev) => prev.map((r) => (r.id === roleId ? previous : r)));
      setRoleNameDraft(previous.name);
      setError(errorMessage(err, "Не вдалося оновити роль"));
    }
  }

  async function handleDeleteRole(roleId: number) {
    setError(null);
    try {
      await api.deleteRole(roleId);
      setRoles((prev) => prev.filter((r) => r.id !== roleId));
      setExpandedRoleId((prev) => (prev === roleId ? null : prev));
    } catch (err) {
      setError(errorMessage(err, "Не вдалося видалити роль"));
    } finally {
      setConfirmDeleteRoleId(null);
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

          <div className="mt-4">
            <h4 className="text-xs font-bold text-text-soft uppercase tracking-wide mb-2">
              Ролі
            </h4>

            {systemRoleHint ? (
              <div className="banner banner-neutral" onClick={() => setSystemRoleHint(false)}>
                <span>Системну роль не можна змінювати. Створіть власну роль</span>
                <button
                  type="button"
                  className="banner-dismiss"
                  aria-label="Закрити"
                  onClick={() => setSystemRoleHint(false)}
                >
                  ×
                </button>
              </div>
            ) : null}

            <ul className="flex flex-col gap-2">
              {roles.map((role) => {
                const isExpanded = expandedRoleId === role.id;
                return (
                  <li
                    key={role.id}
                    className="rounded-xl bg-[var(--glass-bg)] border border-[var(--line)] overflow-hidden"
                  >
                    <div
                      role={role.is_system ? undefined : "button"}
                      tabIndex={role.is_system ? undefined : 0}
                      onClick={() => {
                        if (role.is_system) {
                          setSystemRoleHint(true);
                          return;
                        }
                        const next = expandedRoleId === role.id ? null : role.id;
                        setExpandedRoleId(next);
                        setRoleNameDraft(next === role.id ? role.name : "");
                      }}
                      className={`flex items-center justify-between gap-2 px-3 py-2 ${
                        role.is_system ? "" : "cursor-pointer"
                      }`}
                    >
                      <div className="min-w-0 flex items-center gap-2">
                        <p className="text-sm text-text truncate">{role.name}</p>
                        {role.is_system ? <span className="badge">системна</span> : null}
                      </div>
                      <span className="text-xs text-text-soft shrink-0">
                        {membersCountLabel(role.members_count)}
                      </span>
                    </div>

                    {!role.is_system && isExpanded ? (
                      <div
                        className="flex flex-col gap-2 px-3 pb-3 pt-2 border-t border-[var(--line)]"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <label className="form-field">
                          <span>Назва</span>
                          <input
                            type="text"
                            value={roleNameDraft}
                            onChange={(e) => setRoleNameDraft(e.target.value)}
                            onBlur={() => void handleRoleNameCommit(role.id)}
                            aria-label={`Назва ролі: ${role.name}`}
                          />
                        </label>
                        {PERMISSION_FIELDS.map((field) => (
                          <label
                            key={field.key}
                            className="flex items-center gap-2 text-sm text-text"
                          >
                            <input
                              type="checkbox"
                              checked={role[field.key]}
                              onChange={(e) =>
                                void handleRolePermToggle(role.id, field.key, e.target.checked)
                              }
                            />
                            {field.label}
                          </label>
                        ))}

                        {confirmDeleteRoleId === role.id ? (
                          <div className="flex gap-2 mt-1">
                            <button type="button" onClick={() => setConfirmDeleteRoleId(null)}>
                              Ні
                            </button>
                            <button
                              type="button"
                              className="btn-danger"
                              onClick={() => void handleDeleteRole(role.id)}
                            >
                              Так, видалити
                            </button>
                          </div>
                        ) : (
                          <button
                            type="button"
                            className="btn-danger-outline mt-1"
                            onClick={() => setConfirmDeleteRoleId(role.id)}
                          >
                            Видалити роль
                          </button>
                        )}
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>

            {showCreateRole ? (
              <form
                onSubmit={(e) => void handleCreateRoleSubmit(e)}
                className="mt-2 flex flex-col gap-2 rounded-xl bg-[var(--glass-bg)] border border-[var(--line)] px-3 py-2"
              >
                {roleFormError ? <p className="error-banner">{roleFormError}</p> : null}
                <label className="form-field">
                  <span>Назва</span>
                  <input
                    type="text"
                    value={newRoleName}
                    onChange={(e) => setNewRoleName(e.target.value)}
                    aria-label="Назва нової ролі"
                  />
                </label>
                {PERMISSION_FIELDS.map((field) => (
                  <label key={field.key} className="flex items-center gap-2 text-sm text-text">
                    <input
                      type="checkbox"
                      checked={newRolePerms[field.key]}
                      onChange={(e) => toggleNewRolePerm(field.key, e.target.checked)}
                    />
                    {field.label}
                  </label>
                ))}
                <div className="role-form-actions">
                  <button
                    type="button"
                    className="role-form-cancel-btn"
                    onClick={() => {
                      setShowCreateRole(false);
                      setRoleFormError(null);
                    }}
                    disabled={creatingRole}
                  >
                    Скасувати
                  </button>
                  <button
                    type="submit"
                    className="sheet-reserve-btn"
                    disabled={creatingRole || !newRoleName.trim()}
                  >
                    {creatingRole ? "Створюємо…" : "Створити"}
                  </button>
                </div>
              </form>
            ) : (
              <button
                type="button"
                className="link-button mt-2"
                onClick={() => setShowCreateRole(true)}
              >
                + Створити роль
              </button>
            )}
          </div>

          <ul className="mt-4 flex flex-col gap-2">
            {members.map((member) => {
              const isOwner = member.role === "owner";
              const isExpanded = expandedMemberId === member.id;
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
                      setExpandedMemberId((prev) => (prev === member.id ? null : member.id));
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
                        {isOwner ? "повний доступ" : member.role_name}
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
                      <p className="text-xs text-text-soft">Роль</p>
                      <div
                        role="radiogroup"
                        aria-label={`Роль: ${member.display_name ?? member.tg_id}`}
                        className="flex flex-col gap-2"
                      >
                        {roles.map((role) => (
                          <label
                            key={role.id}
                            className="flex items-center gap-2 text-sm text-text"
                          >
                            <input
                              type="radio"
                              name={`member-role-${member.id}`}
                              checked={member.role_id === role.id}
                              onChange={() => void handleMemberRoleChange(member.id, role.id)}
                            />
                            {role.name}
                          </label>
                        ))}
                      </div>
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
