import { LayoutGrid, Package, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TabId } from "../types";

interface BottomTabBarProps {
  active: TabId;
  onChange: (tab: TabId) => void;
}

const TABS: { id: TabId; labelKey: string; Icon: typeof Package }[] = [
  { id: "dashboard", labelKey: "nav.dashboard", Icon: LayoutGrid },
  { id: "sklad", labelKey: "nav.sklad", Icon: Package },
  { id: "settings", labelKey: "nav.settings", Icon: Settings },
];

export function BottomTabBar({ active, onChange }: BottomTabBarProps) {
  const { t } = useTranslation();
  return (
    <div role="tablist" aria-label="Навігація" className="tab-bar">
      {TABS.map(({ id, labelKey, Icon }) => (
        <button
          key={id}
          role="tab"
          aria-selected={active === id}
          type="button"
          className="tab-bar__item"
          onClick={() => onChange(id)}
        >
          <Icon size={22} aria-hidden="true" strokeWidth={active === id ? 2.4 : 1.8} />
          <span>{t(labelKey)}</span>
        </button>
      ))}
    </div>
  );
}
