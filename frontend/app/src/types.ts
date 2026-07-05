export type SubscriptionStatus = "trial" | "active" | "past_due" | "canceled" | "expired";

export type InviteStatus =
  | "joined"
  | "already_member"
  | "already_in_shop"
  | "invite_invalid"
  | null;

export interface ShopSummary {
  shop_id: number;
  shop_name: string;
  logo_url: string | null;
  role: "owner" | "manager";
}

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
  invite_status: InviteStatus;
  shops: ShopSummary[];
  active_shop_id: number;
}

export interface Invite {
  id: number;
  token: string;
  url: string;
  expires_at: string;
  created_at?: string;
}

export interface TeamMember {
  id: number;
  tg_id: number;
  display_name: string | null;
  role: "owner" | "manager";
  can_view_inventory: boolean;
  can_edit_products: boolean;
  can_manage_reservations: boolean;
  can_manage_stock: boolean;
  can_view_finance: boolean;
  can_manage_billing: boolean;
}

export type PermissionsPatch = Partial<
  Pick<
    TeamMember,
    | "can_view_inventory"
    | "can_edit_products"
    | "can_manage_reservations"
    | "can_manage_stock"
    | "can_view_finance"
    | "can_manage_billing"
  >
>;

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

export type ReservationStatus = "active" | "released" | "fulfilled" | "shipped";

export interface Reservation {
  id: number;
  variant_id: number;
  order_id: number | null;
  qty: number;
  reason: string | null;
  customer_note: string | null;
  source: string;
  status: ReservationStatus;
  ttn: string | null;
  np_status: string | null;
  expires_at: string | null;
  created_at: string;
  released_at: string | null;
  shipped_at: string | null;
}

export interface ReserveInput {
  qty: number;
  customer_note?: string;
  expires_at?: string;
}

export type FinancePeriod = "week" | "month" | "year" | "all";

export interface FinanceChartPoint {
  date: string;
  revenue: string;
}

export interface FinanceTopProduct {
  product_id: number;
  name: string;
  revenue_uah: string;
  units: number;
}

export interface FinanceReasonCount {
  reason: string;
  count: number;
}

export interface FinanceSummary {
  shop_id: number;
  revenue_uah: string;
  sales_count: number;
  units_sold: number;
  returns_uah: string;
  returns_count: number;
  chart: FinanceChartPoint[];
  top_products: FinanceTopProduct[];
  release_reasons: FinanceReasonCount[];
  return_reasons: FinanceReasonCount[];
}

export type WriteOffReason = "sold" | "defect" | "correction" | "other";

export interface AdjustPayload {
  qty: number;
  reason: WriteOffReason;
  comment?: string;
}

export type ReleaseReason =
  | "customer_changed_mind"
  | "unresponsive"
  | "mistaken_reservation"
  | "other";

export interface ReleasePayload {
  reason: ReleaseReason;
  comment?: string;
}

export interface ShipPayload {
  ttn?: string;
}

export type NotPickedUpReason = "did_not_pick_up" | "refused" | "other";

export interface NotPickedUpPayload {
  reason: NotPickedUpReason;
  comment?: string;
}

export interface NpKeyStatus {
  connected: boolean;
}

export interface NpCity {
  ref: string;
  name: string;
}

export interface NpWarehouse {
  ref: string;
  name: string;
}

export interface NpSenderProfile {
  city_ref: string | null;
  city_name: string | null;
  warehouse_ref: string | null;
  warehouse_name: string | null;
  phone: string | null;
  name: string | null;
}

export interface NpSenderPayload {
  city_ref: string;
  city_name: string;
  warehouse_ref: string;
  warehouse_name: string;
  phone: string;
  name: string;
}

export interface CreateTtnPayload {
  recipient_name: string;
  recipient_phone: string;
  recipient_city_ref: string;
  recipient_warehouse_ref: string;
  weight?: number;
  cod?: boolean;
  cod_amount?: string;
  description?: string;
}

export interface CreateTtnResult {
  ttn: string;
  delivery_cost: string;
}

export type TabId = "sklad" | "dashboard" | "settings";
