export type SubscriptionStatus = "trial" | "active" | "past_due" | "canceled" | "expired";

export interface Shop {
  shop_id: number;
  shop_name: string;
  shop_slug: string;
  role: "owner" | "manager";
  logo_url: string | null;
  accent_color: string;
  status: SubscriptionStatus | null;
  is_writable: boolean;
  trial_ends_at: string | null;
  current_period_end: string | null;
  plan_code: string | null;
  limits: Record<string, unknown>;
  products_count: number;
  active_count: number;
  max_products: number | null;
}

export interface Plan {
  code: string;
  name: string;
  period: "month" | "year";
  price_uah: string;
  price_stars: number;
  limits: Record<string, unknown>;
}

export interface Variant {
  id: number;
  sku: string | null;
  axis_values: Record<string, string>;
  price: string;
  on_hand: number;
  reserved: number;
  available: number;
  low_stock_threshold: number;
  photo_url: string | null;
}

export interface Photo {
  id: number;
  url: string;
  position: number;
}

export interface Product {
  id: number;
  name: string;
  description: string | null;
  template_id: number | null;
  attributes: Record<string, unknown>;
  is_demo: boolean;
  is_frozen: boolean;
  archived: boolean;
  variants: Variant[];
  photos: Photo[];
  created_at?: string;
}

export interface TemplateField {
  key: string;
  label: string;
  type: string;
  options?: string[];
}

export interface TemplateFieldSchema {
  attributes: TemplateField[];
  variant_axes: TemplateField[];
  extras?: Record<string, unknown>;
}

export interface Template {
  id: number;
  code: string;
  name: string;
  field_schema: TemplateFieldSchema;
  shop_id?: number | null;
}

export interface VariantInput {
  axis_values: Record<string, string>;
  price: string;
  sku?: string;
  on_hand: number;
  low_stock_threshold?: number;
}

export interface VariantPatchPayload {
  price?: string;
  sku?: string | null;
  axis_values?: Record<string, string>;
}

export interface VariantAddPayload {
  price: string;
  axis_values?: Record<string, string>;
  sku?: string;
}

export interface ProductInput {
  name: string;
  variants: VariantInput[];
  description?: string;
  template_id?: number;
  attributes?: Record<string, unknown>;
}

export interface ProductPatch {
  name?: string;
  description?: string | null;
  attributes?: Record<string, unknown>;
  archived?: boolean;
}

export type ReservationStatus = "active" | "released" | "fulfilled";

export interface Reservation {
  id: number;
  variant_id: number;
  order_id: number | null;
  qty: number;
  reason: string | null;
  customer_note: string | null;
  source: string;
  status: ReservationStatus;
  expires_at: string | null;
  created_at: string;
  released_at: string | null;
}

export interface ReserveInput {
  qty: number;
  customer_note?: string;
  expires_at?: string;
}

export interface FinanceSummary {
  shop_id: number;
  revenue_uah: string;
}

export type TabId = "sklad" | "dashboard" | "settings";
