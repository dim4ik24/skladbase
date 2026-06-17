/**
 * SkladBase — типізований API-клієнт (Стадія 7a).
 *
 * На КОЖЕН запит — заголовок `X-Telegram-Init-Data` (бекенд бере shop_id
 * лише з нього, CLAUDE.md, інваріант №1). Базовий URL — `VITE_API_BASE`.
 */
import { getInitData } from "./telegram";
import type {
  Product,
  ProductInput,
  ProductPatch,
  Reservation,
  ReserveInput,
  Shop,
  Template,
  Variant,
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "X-Telegram-Init-Data": getInitData(),
  };
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

export function adjust(variantId: number, newOnHand: number): Promise<Variant> {
  return request<Variant>(`/api/variants/${variantId}/adjust`, {
    method: "POST",
    body: JSON.stringify({ new_on_hand: newOnHand }),
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

export function releaseReservation(id: number): Promise<Reservation> {
  return request<Reservation>(`/api/reservations/${id}/release`, { method: "POST" });
}

export function fulfillReservation(id: number): Promise<Reservation> {
  return request<Reservation>(`/api/reservations/${id}/fulfill`, { method: "POST" });
}
