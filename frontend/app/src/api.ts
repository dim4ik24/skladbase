/**
 * SkladBase — типізований API-клієнт (Стадія 7a).
 *
 * На КОЖЕН запит — заголовок `X-Telegram-Init-Data` (бекенд бере shop_id
 * лише з нього, CLAUDE.md, інваріант №1). Базовий URL — `VITE_API_BASE`.
 */
import i18n from "./i18n";
import { getInitData } from "./telegram";
import type {
  AdjustPayload,
  CreateTtnPayload,
  CreateTtnResult,
  FinancePeriod,
  FinanceSummary,
  HistoryEvent,
  Invite,
  MemberPermissionsPatch,
  NotPickedUpPayload,
  NpCity,
  NpKeyStatus,
  NpSenderPayload,
  NpSenderProfile,
  NpWarehouse,
  Photo,
  Plan,
  Product,
  ProductInput,
  ProductPatch,
  ReleasePayload,
  Reservation,
  ReserveInput,
  Role,
  RoleCreate,
  RolePatch,
  Shop,
  ShipPayload,
  TeamMember,
  Template,
  Variant,
  VariantAddPayload,
  VariantPatchPayload,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`API error ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// Multi-shop (Стадія 3б): яке membership обирає бекенд серед СВОЇХ tg_id
// (X-Shop-Id — лише вибір, backend сам валідує; чужий/невідомий id -> 403,
// НЕ підробка shop_id). null -> заголовок не шлеться, бекенд бере дефолт.
let activeShopId: number | null = null;

export function setActiveShopId(id: number | null): void {
  activeShopId = id;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "X-Telegram-Init-Data": getInitData(),
    "X-App-Language": i18n.language,
  };
  if (activeShopId != null) {
    headers["X-Shop-Id"] = String(activeShopId);
  }
  if (init.body && !(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...headers, ...init.headers },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // тіло не JSON — лишаємо statusText
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function getMe(): Promise<Shop> {
  return request<Shop>("/api/me");
}

export function getProducts(): Promise<Product[]> {
  return request<Product[]>("/api/products");
}

export function restock(variantId: number, qty: number): Promise<Variant> {
  return request<Variant>(`/api/variants/${variantId}/restock`, {
    method: "POST",
    body: JSON.stringify({ qty }),
  });
}

export function adjust(variantId: number, payload: AdjustPayload): Promise<Variant> {
  return request<Variant>(`/api/variants/${variantId}/adjust`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getTemplates(): Promise<Template[]> {
  return request<Template[]>("/api/templates");
}

export function createProduct(payload: ProductInput): Promise<Product> {
  return request<Product>("/api/products", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateProduct(id: number, patch: ProductPatch): Promise<Product> {
  return request<Product>(`/api/products/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function uploadVariantPhoto(variantId: number, file: File): Promise<Variant> {
  const formData = new FormData();
  formData.append("file", file);
  return request<Variant>(`/api/variants/${variantId}/photo`, {
    method: "POST",
    body: formData,
  });
}

export function reserve(variantId: number, payload: ReserveInput): Promise<Reservation> {
  return request<Reservation>(`/api/variants/${variantId}/reserve`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getReservations(): Promise<Reservation[]> {
  return request<Reservation[]>("/api/reservations");
}

export function releaseReservation(id: number, payload?: ReleasePayload): Promise<Reservation> {
  return request<Reservation>(`/api/reservations/${id}/release`, {
    method: "POST",
    body: payload ? JSON.stringify(payload) : undefined,
  });
}

export function fulfillReservation(id: number): Promise<Reservation> {
  return request<Reservation>(`/api/reservations/${id}/fulfill`, { method: "POST" });
}

export function shipReservation(id: number, payload?: ShipPayload): Promise<Reservation> {
  return request<Reservation>(`/api/reservations/${id}/ship`, {
    method: "POST",
    body: payload ? JSON.stringify(payload) : undefined,
  });
}

export function updateReservationTtn(id: number, ttn: string): Promise<Reservation> {
  return request<Reservation>(`/api/reservations/${id}/ttn`, {
    method: "PATCH",
    body: JSON.stringify({ ttn }),
  });
}

export function pickUpReservation(id: number): Promise<Reservation> {
  return request<Reservation>(`/api/reservations/${id}/pick-up`, { method: "POST" });
}

export function notPickedUpReservation(
  id: number,
  payload: NotPickedUpPayload,
): Promise<Reservation> {
  return request<Reservation>(`/api/reservations/${id}/not-picked-up`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getPlans(): Promise<Plan[]> {
  return request<Plan[]>("/api/billing/plans");
}

export function checkoutStars(planCode: string): Promise<{ invoice_link: string }> {
  return request<{ invoice_link: string }>("/api/billing/checkout/stars", {
    method: "POST",
    body: JSON.stringify({ plan_code: planCode }),
  });
}

export function redeemPromo(code: string): Promise<{ current_period_end: string | null }> {
  return request<{ current_period_end: string | null }>("/api/billing/promo", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export function createTemplate(name: string, field_schema: Record<string, unknown>): Promise<Template> {
  return request<Template>("/api/templates", {
    method: "POST",
    body: JSON.stringify({ name, field_schema }),
  });
}

export function uploadProductPhoto(productId: number, file: File): Promise<Photo> {
  const formData = new FormData();
  formData.append("file", file);
  return request<Photo>(`/api/products/${productId}/photos`, {
    method: "POST",
    body: formData,
  });
}

export function deleteProductPhoto(productId: number, photoId: number): Promise<void> {
  return request<void>(`/api/products/${productId}/photos/${photoId}`, {
    method: "DELETE",
  });
}

export function clearDemos(): Promise<{ removed: number }> {
  return request<{ removed: number }>("/api/shop/clear-demos", { method: "POST" });
}

export function updateShopProfile(name: string): Promise<{ shop_name: string; logo_url: string | null }> {
  return request("/api/shop", { method: "PATCH", body: JSON.stringify({ name }) });
}

export function uploadShopLogo(file: File): Promise<{ logo_url: string }> {
  const formData = new FormData();
  formData.append("file", file);
  return request("/api/shop/logo", { method: "POST", body: formData });
}

export function deleteShopLogo(): Promise<void> {
  return request<void>("/api/shop/logo", { method: "DELETE" });
}

export function getNpStatus(): Promise<NpKeyStatus> {
  return request<NpKeyStatus>("/api/shop/np-key");
}

export function putNpKey(apiKey: string): Promise<NpKeyStatus> {
  return request<NpKeyStatus>("/api/shop/np-key", {
    method: "PUT",
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export function deleteNpKey(): Promise<void> {
  return request<void>("/api/shop/np-key", { method: "DELETE" });
}

export function searchNpCities(query: string): Promise<NpCity[]> {
  return request<NpCity[]>(`/api/np/cities?q=${encodeURIComponent(query)}`);
}

export function getNpWarehouses(cityRef: string): Promise<NpWarehouse[]> {
  return request<NpWarehouse[]>(`/api/np/warehouses?city_ref=${encodeURIComponent(cityRef)}`);
}

export function getNpSender(): Promise<NpSenderProfile> {
  return request<NpSenderProfile>("/api/shop/np-sender");
}

export function putNpSender(payload: NpSenderPayload): Promise<NpSenderProfile> {
  return request<NpSenderProfile>("/api/shop/np-sender", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function createTtn(
  reservationId: number,
  payload: CreateTtnPayload,
): Promise<CreateTtnResult> {
  return request<CreateTtnResult>(`/api/reservations/${reservationId}/create-ttn`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getFinanceSummary(period: FinancePeriod = "all"): Promise<FinanceSummary> {
  return request<FinanceSummary>(`/api/finance/summary?period=${period}`);
}

export function getFinanceHistory(
  period: FinancePeriod = "all",
  date?: string,
): Promise<HistoryEvent[]> {
  const dateParam = date ? `&date=${encodeURIComponent(date)}` : "";
  return request<HistoryEvent[]>(`/api/finance/history?period=${period}${dateParam}`);
}

export function patchVariant(variantId: number, payload: VariantPatchPayload): Promise<Variant> {
  return request<Variant>(`/api/variants/${variantId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function addVariant(productId: number, payload: VariantAddPayload): Promise<Variant> {
  return request<Variant>(`/api/products/${productId}/variants`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteVariant(variantId: number): Promise<void> {
  return request<void>(`/api/variants/${variantId}`, { method: "DELETE" });
}

export function createInvite(): Promise<Invite> {
  return request<Invite>("/api/team/invites", { method: "POST" });
}

export function listInvites(): Promise<Invite[]> {
  return request<Invite[]>("/api/team/invites");
}

export function revokeInvite(id: number): Promise<void> {
  return request<void>(`/api/team/invites/${id}`, { method: "DELETE" });
}

export function listMembers(): Promise<TeamMember[]> {
  return request<TeamMember[]>("/api/team/members");
}

export function removeMember(membershipId: number): Promise<void> {
  return request<void>(`/api/team/members/${membershipId}`, { method: "DELETE" });
}

export function getRoles(): Promise<Role[]> {
  return request<Role[]>("/api/team/roles");
}

export function createRole(payload: RoleCreate): Promise<Role> {
  return request<Role>("/api/team/roles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function patchRole(roleId: number, patch: RolePatch): Promise<Role> {
  return request<Role>(`/api/team/roles/${roleId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function deleteRole(roleId: number): Promise<void> {
  return request<void>(`/api/team/roles/${roleId}`, { method: "DELETE" });
}

export function setMemberRole(membershipId: number, roleId: number): Promise<TeamMember> {
  return request<TeamMember>(`/api/team/members/${membershipId}/role`, {
    method: "PATCH",
    body: JSON.stringify({ role_id: roleId }),
  });
}

export function patchMemberPermissions(
  membershipId: number,
  patch: MemberPermissionsPatch,
): Promise<TeamMember> {
  return request<TeamMember>(`/api/team/members/${membershipId}/permissions`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}
