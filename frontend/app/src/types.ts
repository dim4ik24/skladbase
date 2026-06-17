export interface Shop {
  shop_id: number;
  shop_name: string;
  shop_slug: string;
  role: "owner" | "manager";
  logo_url: string | null;
  accent_color: string;
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

export interface Product {
  id: number;
  name: string;
  description: string | null;
  template_id: number | null;
  attributes: Record<string, unknown>;
  is_demo: boolean;
  archived: boolean;
  variants: Variant[];
}
