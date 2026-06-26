import { LayoutGrid, Package, Settings } from "lucide-react";
import type { TabId } from "../types";

interface BottomTabBarProps {
  active: TabId;
  onChange: (tab: TabId) => void;
}

const TABS: { id: TabId; label: string; Icon: typeof Package }[] = [
  { id: "sklad", label: "Склад", Icon: Package },
  { id: "dashboard", label: "Дашборд", Icon: LayoutGrid },
  { id: "settings", label: "Налаштування", Icon: Settings },
];

export function BottomTabBar({ active, onChange }: BottomTabBarProps) {
  return (
    <div role="tablist" aria-label="Навігація" className="tab-bar">
      {TABS.map(({ id, label, Icon }) => (
        <button
          key={id}
          role="tab"
          aria-selected={active === id}
          type="button"
          className="tab-bar__item"
          onClick={() => onChange(id)}
        >
          <Icon size={22} aria-hidden="true" strokeWidth={active === id ? 2.4 : 1.8} />
          <span>{label}</span>
        </button>
      ))}
    </div>
  );
}
