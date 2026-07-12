import { useEffect, useRef, useState } from "react";
import type { FormEvent, RefObject } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import * as api from "../api";
import { ApiError } from "../api";
import { errorMessage } from "../errors";
import { shareInviteLink } from "../telegram";
import type { Invite, Role, RolePermissions, TeamMember } from "../types";

const COLLAPSE_TRANSITION = { duration: 0.2, ease: "easeInOut" as const };

const PERMISSION_FIELDS: Array<{ key: keyof RolePermissions; labelKey: string }> = [
  { key: "can_view_inventory", labelKey: "team.permissions.viewInventory" },
  { key: "can_edit_products", labelKey: "team.permissions.editProducts" },
  { key: "can_manage_reservations", labelKey: "team.permissions.manageReservations" },
  { key: "can_manage_stock", labelKey: "team.permissions.manageStock" },
  { key: "can_view_finance", labelKey: "team.permissions.viewFinance" },
  { key: "can_manage_billing", labelKey: "team.permissions.manageBilling" },
];

const DEFAULT_ROLE_PERMS: RolePermissions = {
  can_view_inventory: true,
  can_edit_products: true,
  can_manage_reservations: true,
  can_manage_stock: true,
  can_view_finance: true,
  can_manage_billing: true,
};

// Єдина роль, яку не можна редагувати — "Менеджер" (теж is_system) тепер
// відкривається на редагування як звичайна кастомна роль (бейдж "системна"
// лишається — просто інформація, не блокер). Дзеркалить backend (team.py,
// _OWNER_ROLE_NAME): DELETE лишається забороненим для ОБОХ системних ролей.
const OWNER_ROLE_NAME = "Власник";

function rolePermissions(role: Role): RolePermissions {
  return {
    can_view_inventory: role.can_view_inventory,
    can_edit_products: role.can_edit_products,
    can_manage_reservations: role.can_manage_reservations,
    can_manage_stock: role.can_manage_stock,
    can_view_finance: role.can_view_finance,
    can_manage_billing: role.can_manage_billing,
  };
}

function hoursLeft(expiresAt: string): number {
  const ms = new Date(expiresAt).getTime() - Date.now();
  return Math.max(0, Math.round(ms / (60 * 60 * 1000)));
}

function membersCountLabel(count: number, t: TFunction): string {
  return t("team.membersCount", { count });
}

interface TeamSectionProps {
  scrollContainerRef: RefObject<HTMLDivElement | null>;
}

type ExpandedItem = { type: "role" | "member"; id: number } | null;

/** Скрол-згортання (фідбек "поле не зникає"): якщо відкрита розгортка
 * ПОВНІСТЮ вийшла за межі скрол-контейнера — закриваємо. IntersectionObserver
 * з isIntersecting=false спрацьовує саме на 0% видимості (дефолтний
 * threshold 0), тобто "частково видима" НЕ закриває — рівно те, що треба,
 * інакше розгортка зникла б "під пальцем" під час самого скролу.
 *
 * setExpandedItem викликається через ФУНКЦІОНАЛЬНИЙ апдейтер, що звіряє
 * поточний expandedItem з тим item, за яким СПОСТЕРІГАВ саме цей observer
 * — інакше живий баг: клік на іншому рядку (роль/член) міняє expandedItem
 * і водночас (той самий скрол, що вивів попередню панель за межі екрана)
 * будить старий observer СТАРОЇ панелі; без цієї звірки його колбек
 * долітав би вже ПІСЛЯ того, як новий item відкрився, і тихо скидав би
 * його назад у null. */
function useCollapseWhenScrolledOut(
  panelRef: RefObject<HTMLDivElement | null>,
  scrollContainerRef: RefObject<HTMLDivElement | null>,
  item: ExpandedItem,
  setExpandedItem: (updater: (current: ExpandedItem) => ExpandedItem) => void,
) {
  useEffect(() => {
    if (!item) return;
    const panel = panelRef.current;
    if (!panel) return;
    const watched = item;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) return;
        setExpandedItem((current) =>
          current?.type === watched.type && current.id === watched.id ? null : current,
        );
      },
      { root: scrollContainerRef.current, threshold: 0 },
    );
    observer.observe(panel);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item?.type, item?.id]);
}

export function TeamSection({ scrollContainerRef }: TeamSectionProps) {
  const { t } = useTranslation();
  const [invites, setInvites] = useState<Invite[]>([]);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newInvite, setNewInvite] = useState<Invite | null>(null);
  const [confirmRevokeId, setConfirmRevokeId] = useState<number | null>(null);
  const [confirmRemoveId, setConfirmRemoveId] = useState<number | null>(null);

  // Аккордеон: розгортка ролі й розгортка члена ділять ОДИН стан — відкриття
  // будь-якої з них закриває попередню відкриту (незалежно, роль це чи
  // член), бо фідбек "поле не зникає" був саме про це — забуту відкриту
  // розгортку деінде на екрані.
  const [expandedItem, setExpandedItem] = useState<
    { type: "role" | "member"; id: number } | null
  >(null);

  const [showCreateRole, setShowCreateRole] = useState(false);
  const [newRoleName, setNewRoleName] = useState("");
  const [newRolePerms, setNewRolePerms] = useState<RolePermissions>(DEFAULT_ROLE_PERMS);
  const [creatingRole, setCreatingRole] = useState(false);
  const [roleFormError, setRoleFormError] = useState<string | null>(null);
  const [roleNameDraft, setRoleNameDraft] = useState("");
  const [confirmDeleteRoleId, setConfirmDeleteRoleId] = useState<number | null>(null);
  const [ownerRoleHint, setOwnerRoleHint] = useState(false);
  const [pendingRoleChange, setPendingRoleChange] = useState<{
    memberId: number;
    roleId: number;
  } | null>(null);

  // Один ref на панель, що зараз розгорнута — акордеон гарантує, що
  // одночасно існує щонайбільше одна.
  const expandedPanelRef = useRef<HTMLDivElement | null>(null);
  useCollapseWhenScrolledOut(expandedPanelRef, scrollContainerRef, expandedItem, setExpandedItem);

  useEffect(() => {
    if (!ownerRoleHint) return;
    const timer = setTimeout(() => setOwnerRoleHint(false), 3000);
    return () => clearTimeout(timer);
  }, [ownerRoleHint]);

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
        setError(errorMessage(err, t("team.loadFailed")));
      } finally {
        if (mounted) setLoading(false);
      }
    }
    void load();
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t навмисно не в deps: завантаження лише на mount
  }, []);

  async function handleCreateInvite() {
    setError(null);
    setCreating(true);
    try {
      const invite = await api.createInvite();
      setNewInvite(invite);
      setInvites((prev) => [invite, ...prev]);
    } catch (err) {
      setError(errorMessage(err, t("team.invites.createFailed")));
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
      setError(errorMessage(err, t("team.invites.revokeFailed")));
    } finally {
      setConfirmRevokeId(null);
    }
  }

  async function handleRemoveMember(id: number) {
    setError(null);
    try {
      await api.removeMember(id);
      setMembers((prev) => prev.filter((m) => m.id !== id));
      setExpandedItem((prev) => (prev?.type === "member" && prev.id === id ? null : prev));
    } catch (err) {
      setError(errorMessage(err, t("team.members.removeFailed")));
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
              ...rolePermissions(nextRole),
              // Backend скидає overrides в тій самій транзакції, що й
              // призначення ролі (team.py, update_member_role) —
              // дзеркалимо тут одразу, не чекаючи відповіді.
              overridden: [],
            }
          : m,
      ),
    );
    try {
      const updated = await api.setMemberRole(memberId, roleId);
      setMembers((prev) => prev.map((m) => (m.id === memberId ? updated : m)));
    } catch (err) {
      setMembers((prev) => prev.map((m) => (m.id === memberId ? previous : m)));
      setError(errorMessage(err, t("team.members.roleChangeFailed")));
    }
  }

  // Зміна ролі скидає всі індивідуальні override — якщо вони Є, підтверди
  // (two-step, той самий патерн, що й Скасувати/Видалити роль вище).
  function handleRoleRadioChange(member: TeamMember, roleId: number) {
    if (roleId === member.role_id) return;
    if (member.overridden.length > 0) {
      setPendingRoleChange({ memberId: member.id, roleId });
      return;
    }
    void handleMemberRoleChange(member.id, roleId);
  }

  async function confirmPendingRoleChange() {
    if (!pendingRoleChange) return;
    const { memberId, roleId } = pendingRoleChange;
    setPendingRoleChange(null);
    await handleMemberRoleChange(memberId, roleId);
  }

  async function handleMemberPermToggle(
    memberId: number,
    field: keyof RolePermissions,
    value: boolean | null,
  ) {
    setError(null);
    const previous = members.find((m) => m.id === memberId);
    if (!previous) return;
    const role = roles.find((r) => r.id === previous.role_id);
    const effectiveValue = value === null ? (role?.[field] ?? false) : value;
    const nextOverridden =
      value === null
        ? previous.overridden.filter((f) => f !== field)
        : previous.overridden.includes(field)
          ? previous.overridden
          : [...previous.overridden, field];

    setMembers((prev) =>
      prev.map((m) =>
        m.id === memberId ? { ...m, [field]: effectiveValue, overridden: nextOverridden } : m,
      ),
    );
    try {
      const updated = await api.patchMemberPermissions(memberId, { [field]: value });
      setMembers((prev) => prev.map((m) => (m.id === memberId ? updated : m)));
    } catch (err) {
      setMembers((prev) => prev.map((m) => (m.id === memberId ? previous : m)));
      setError(errorMessage(err, t("team.members.permissionsUpdateFailed")));
    }
  }

  async function handleResetAllOverrides(memberId: number) {
    setError(null);
    const previous = members.find((m) => m.id === memberId);
    if (!previous) return;
    const role = roles.find((r) => r.id === previous.role_id);

    setMembers((prev) =>
      prev.map((m) =>
        m.id === memberId
          ? { ...m, ...(role ? rolePermissions(role) : {}), overridden: [] }
          : m,
      ),
    );
    try {
      const resetPatch = Object.fromEntries(PERMISSION_FIELDS.map((f) => [f.key, null]));
      const updated = await api.patchMemberPermissions(memberId, resetPatch);
      setMembers((prev) => prev.map((m) => (m.id === memberId ? updated : m)));
    } catch (err) {
      setMembers((prev) => prev.map((m) => (m.id === memberId ? previous : m)));
      setError(errorMessage(err, t("team.members.overridesResetFailed")));
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
        setRoleFormError(t("team.roles.duplicateName"));
      } else {
        setRoleFormError(errorMessage(err, t("team.roles.createFailed")));
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
      setError(errorMessage(err, t("team.roles.updateFailed")));
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
      setError(errorMessage(err, t("team.roles.updateFailed")));
    }
  }

  async function handleDeleteRole(roleId: number) {
    setError(null);
    try {
      await api.deleteRole(roleId);
      setRoles((prev) => prev.filter((r) => r.id !== roleId));
      setExpandedItem((prev) => (prev?.type === "role" && prev.id === roleId ? null : prev));
    } catch (err) {
      setError(errorMessage(err, t("team.roles.deleteFailed")));
    } finally {
      setConfirmDeleteRoleId(null);
    }
  }

  function handleShare(url: string) {
    shareInviteLink(url, t("team.invites.shareText"));
  }

  function handleCopy(url: string) {
    void navigator.clipboard?.writeText(url);
  }

  return (
    <div className="glass-card rounded-[20px] p-4 shadow-[var(--shadow-card)]">
      <h3 className="text-sm font-bold text-text-soft uppercase tracking-wide mb-3">
        {t("team.title")}
      </h3>

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
        {creating ? t("team.invites.creating") : t("team.invites.createButton")}
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
              {t("team.invites.copyButton")}
            </button>
            <button
              type="button"
              onClick={() => handleShare(newInvite.url)}
              className="flex-1 rounded-xl px-3 py-1.5 text-xs font-semibold text-white"
              style={{
                background: "linear-gradient(135deg, var(--green) 0%, var(--green-deep) 100%)",
              }}
            >
              {t("team.invites.shareButton")}
            </button>
          </div>
        </div>
      ) : null}

      {loading ? (
        <p className="status-text">{t("common.loading")}</p>
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
                    {t("team.invites.expiresIn", { hours: hoursLeft(invite.expires_at) })}
                  </span>
                  {confirmRevokeId === invite.id ? (
                    <div className="flex gap-2 shrink-0">
                      <button type="button" onClick={() => setConfirmRevokeId(null)}>
                        {t("team.no")}
                      </button>
                      <button
                        type="button"
                        className="btn-danger"
                        onClick={() => void handleRevoke(invite.id)}
                      >
                        {t("team.invites.confirmRevoke")}
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="btn-danger-outline shrink-0"
                      onClick={() => setConfirmRevokeId(invite.id)}
                    >
                      {t("common.cancel")}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          ) : null}

          <div className="mt-4">
            <h4 className="text-xs font-bold text-text-soft uppercase tracking-wide mb-2">
              {t("team.roles.title")}
            </h4>

            {ownerRoleHint ? (
              <div className="banner banner-neutral" onClick={() => setOwnerRoleHint(false)}>
                <span>{t("team.roles.ownerHint")}</span>
                <button
                  type="button"
                  className="banner-dismiss"
                  aria-label={t("common.close")}
                  onClick={() => setOwnerRoleHint(false)}
                >
                  ×
                </button>
              </div>
            ) : null}

            <ul className="flex flex-col gap-2">
              {roles.map((role) => {
                const isExpanded = expandedItem?.type === "role" && expandedItem.id === role.id;
                const isLockedRole = role.name === OWNER_ROLE_NAME;
                return (
                  <li
                    key={role.id}
                    className="rounded-xl bg-[var(--glass-bg)] border border-[var(--line)] overflow-hidden"
                  >
                    <div
                      role={isLockedRole ? undefined : "button"}
                      tabIndex={isLockedRole ? undefined : 0}
                      onClick={() => {
                        if (isLockedRole) {
                          setOwnerRoleHint(true);
                          return;
                        }
                        const next = isExpanded ? null : { type: "role" as const, id: role.id };
                        setExpandedItem(next);
                        setRoleNameDraft(next ? role.name : "");
                      }}
                      className={`flex items-center justify-between gap-2 px-3 py-2 ${
                        isLockedRole ? "" : "cursor-pointer"
                      }`}
                    >
                      <div className="min-w-0 flex items-center gap-2">
                        <p className="text-sm text-text truncate">{role.name}</p>
                        {role.is_system ? (
                          <span className="badge">{t("team.roles.systemBadge")}</span>
                        ) : null}
                      </div>
                      <span className="text-xs text-text-soft shrink-0">
                        {membersCountLabel(role.members_count, t)}
                      </span>
                    </div>

                    <AnimatePresence initial={false}>
                      {!isLockedRole && isExpanded ? (
                        <motion.div
                          ref={expandedPanelRef}
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={COLLAPSE_TRANSITION}
                          style={{ overflow: "hidden" }}
                          className="flex flex-col gap-2 px-3 pb-3 pt-2 border-t border-[var(--line)]"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <label className="form-field">
                            <span>{t("team.roles.nameLabel")}</span>
                            <input
                              type="text"
                              value={roleNameDraft}
                              onChange={(e) => setRoleNameDraft(e.target.value)}
                              onBlur={() => void handleRoleNameCommit(role.id)}
                              aria-label={t("team.roles.nameAriaLabel", { name: role.name })}
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
                              {t(field.labelKey)}
                            </label>
                          ))}

                          {!role.is_system ? (
                            confirmDeleteRoleId === role.id ? (
                              <div className="flex gap-2 mt-1">
                                <button
                                  type="button"
                                  onClick={() => setConfirmDeleteRoleId(null)}
                                >
                                  {t("team.no")}
                                </button>
                                <button
                                  type="button"
                                  className="btn-danger"
                                  onClick={() => void handleDeleteRole(role.id)}
                                >
                                  {t("team.confirmDelete")}
                                </button>
                              </div>
                            ) : (
                              <button
                                type="button"
                                className="btn-danger-outline mt-1"
                                onClick={() => setConfirmDeleteRoleId(role.id)}
                              >
                                {t("team.roles.deleteButton")}
                              </button>
                            )
                          ) : null}
                        </motion.div>
                      ) : null}
                    </AnimatePresence>
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
                  <span>{t("team.roles.nameLabel")}</span>
                  <input
                    type="text"
                    value={newRoleName}
                    onChange={(e) => setNewRoleName(e.target.value)}
                    aria-label={t("team.roles.newNameAriaLabel")}
                  />
                </label>
                {PERMISSION_FIELDS.map((field) => (
                  <label key={field.key} className="flex items-center gap-2 text-sm text-text">
                    <input
                      type="checkbox"
                      checked={newRolePerms[field.key]}
                      onChange={(e) => toggleNewRolePerm(field.key, e.target.checked)}
                    />
                    {t(field.labelKey)}
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
                    {t("common.cancel")}
                  </button>
                  <button
                    type="submit"
                    className="sheet-reserve-btn"
                    disabled={creatingRole || !newRoleName.trim()}
                  >
                    {creatingRole ? t("team.roles.creating") : t("team.roles.createSubmit")}
                  </button>
                </div>
              </form>
            ) : (
              <button
                type="button"
                className="link-button mt-2"
                onClick={() => setShowCreateRole(true)}
              >
                {t("team.roles.createButton")}
              </button>
            )}
          </div>

          <ul className="mt-4 flex flex-col gap-2">
            {members.map((member) => {
              const isOwner = member.role === "owner";
              const isExpanded =
                expandedItem?.type === "member" && expandedItem.id === member.id;
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
                      setExpandedItem(isExpanded ? null : { type: "member", id: member.id });
                    }}
                    className={`flex items-center justify-between gap-2 px-3 py-2 ${
                      isOwner ? "" : "cursor-pointer"
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="text-sm text-text truncate flex items-center gap-1.5">
                        {member.display_name ?? String(member.tg_id)}
                        {member.overridden.length > 0 ? (
                          <span
                            className="perm-override-dot"
                            aria-label={t("team.members.overriddenLabel")}
                            title={t("team.members.overriddenLabel")}
                          />
                        ) : null}
                      </p>
                      <p className="text-xs text-text-soft">
                        {isOwner ? t("team.members.fullAccess") : member.role_name}
                      </p>
                    </div>
                    {!isOwner ? (
                      confirmRemoveId === member.id ? (
                        <div
                          className="flex gap-2 shrink-0"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button type="button" onClick={() => setConfirmRemoveId(null)}>
                            {t("team.no")}
                          </button>
                          <button
                            type="button"
                            className="btn-danger"
                            onClick={() => void handleRemoveMember(member.id)}
                          >
                            {t("team.confirmDelete")}
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
                          {t("team.members.removeButton")}
                        </button>
                      )
                    ) : null}
                  </div>

                  <AnimatePresence initial={false}>
                    {!isOwner && isExpanded ? (
                      <motion.div
                        ref={expandedPanelRef}
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={COLLAPSE_TRANSITION}
                        style={{ overflow: "hidden" }}
                        className="flex flex-col gap-2 px-3 pb-3 pt-2 border-t border-[var(--line)]"
                      >
                        <p className="text-xs text-text-soft">{t("team.members.roleLabel")}</p>
                        <div
                          role="radiogroup"
                          aria-label={t("team.members.roleAriaLabel", {
                            name: member.display_name ?? member.tg_id,
                          })}
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
                                onChange={() => handleRoleRadioChange(member, role.id)}
                              />
                              {role.name}
                            </label>
                          ))}
                        </div>

                        {pendingRoleChange?.memberId === member.id ? (
                          <div className="flex flex-col gap-2 rounded-xl bg-[var(--bg)] p-2">
                            <p className="text-xs text-text-soft">
                              {t("team.members.overridesWillReset")}
                            </p>
                            <div className="flex gap-2">
                              <button
                                type="button"
                                onClick={() => setPendingRoleChange(null)}
                              >
                                {t("common.cancel")}
                              </button>
                              <button
                                type="button"
                                className="btn-danger"
                                onClick={() => void confirmPendingRoleChange()}
                              >
                                {t("team.members.confirmRoleChange")}
                              </button>
                            </div>
                          </div>
                        ) : null}

                        <div className="flex items-center justify-between mt-1">
                          <p className="text-xs text-text-soft">
                            {t("team.members.permissionsLabel")}
                          </p>
                          {member.overridden.length > 0 ? (
                            <button
                              type="button"
                              className="link-button"
                              onClick={() => void handleResetAllOverrides(member.id)}
                            >
                              {t("team.members.resetToRoleButton")}
                            </button>
                          ) : null}
                        </div>
                        {PERMISSION_FIELDS.map((field) => {
                          const isOverridden = member.overridden.includes(field.key);
                          return (
                            <label
                              key={field.key}
                              className="flex items-center gap-2 text-sm text-text"
                            >
                              <input
                                type="checkbox"
                                checked={member[field.key]}
                                onChange={(e) =>
                                  void handleMemberPermToggle(
                                    member.id,
                                    field.key,
                                    e.target.checked,
                                  )
                                }
                              />
                              {t(field.labelKey)}
                              {isOverridden ? (
                                <button
                                  type="button"
                                  className="perm-override-dot"
                                  aria-label={t("team.members.resetFieldAriaLabel", {
                                    field: t(field.labelKey),
                                  })}
                                  title={t("team.members.overriddenTooltip")}
                                  onClick={() =>
                                    void handleMemberPermToggle(member.id, field.key, null)
                                  }
                                />
                              ) : null}
                            </label>
                          );
                        })}
                      </motion.div>
                    ) : null}
                  </AnimatePresence>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
