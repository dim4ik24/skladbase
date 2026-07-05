import { useLayoutEffect, useState } from "react";
import type { RefObject } from "react";

interface DropdownRect {
  top: number;
  left: number;
  width: number;
}

/**
 * Позиція для dropdown-списку, який рендериться в портал (document.body) —
 * потрібно, бо і NpCityPicker, і NpWarehousePicker використовуються всередині
 * bottom sheet (overflow/scroll-контейнер обрізав би звичайний absolute-список).
 * Перераховує на scroll/resize, поки dropdown відкритий (scroll capture на
 * document — ловить скрол БУДЬ-якого предка, бо ці події не спливають).
 */
export function useAnchoredDropdown(
  anchorRef: RefObject<HTMLElement | null>,
  open: boolean,
): DropdownRect | null {
  const [rect, setRect] = useState<DropdownRect | null>(null);

  useLayoutEffect(() => {
    if (!open) return;

    function update() {
      const el = anchorRef.current;
      if (!el) return;
      const box = el.getBoundingClientRect();
      setRect({ top: box.bottom, left: box.left, width: box.width });
    }

    update();
    window.addEventListener("resize", update);
    document.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      document.removeEventListener("scroll", update, true);
    };
  }, [anchorRef, open]);

  // Гейтимо на виході з хука, не всередині ефекту: коли open стає false,
  // старий rect більше не читається жодним споживачем (усі рендерять
  // dropdown лише за умови `open && rect`), тож немає потреби скидати
  // стан прямим setState у тілі ефекту.
  return open ? rect : null;
}
