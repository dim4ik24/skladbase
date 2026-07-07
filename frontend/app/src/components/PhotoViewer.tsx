import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Photo } from "../types";

interface PhotoViewerProps {
  photos: Photo[];
  initialIndex: number;
  onClose: () => void;
}

const SWIPE_THRESHOLD_PX = 40;

export function PhotoViewer({ photos, initialIndex, onClose }: PhotoViewerProps) {
  const [index, setIndex] = useState(initialIndex);
  const touchStartX = useRef<number | null>(null);

  function goPrev() {
    setIndex((i) => (i - 1 + photos.length) % photos.length);
  }

  function goNext() {
    setIndex((i) => (i + 1) % photos.length);
  }

  function handleTouchStart(e: React.TouchEvent) {
    touchStartX.current = e.touches[0].clientX;
  }

  function handleTouchEnd(e: React.TouchEvent) {
    const startX = touchStartX.current;
    touchStartX.current = null;
    if (startX === null) return;
    const deltaX = e.changedTouches[0].clientX - startX;
    if (deltaX > SWIPE_THRESHOLD_PX) goPrev();
    else if (deltaX < -SWIPE_THRESHOLD_PX) goNext();
  }

  const photo = photos[index];
  if (!photo) return null;

  const viewer = (
    <div
      className="photo-viewer-overlay"
      role="dialog"
      aria-label="Перегляд фото"
      onClick={onClose}
    >
      <button type="button" className="photo-viewer-close" aria-label="Закрити" onClick={onClose}>
        ✕
      </button>

      {photos.length > 1 ? (
        <button
          type="button"
          className="photo-viewer-arrow photo-viewer-arrow--prev"
          aria-label="Попереднє фото"
          onClick={(e) => {
            e.stopPropagation();
            goPrev();
          }}
        >
          ‹
        </button>
      ) : null}

      <img
        src={photo.url}
        alt=""
        className="photo-viewer-image"
        onClick={(e) => e.stopPropagation()}
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
      />

      {photos.length > 1 ? (
        <button
          type="button"
          className="photo-viewer-arrow photo-viewer-arrow--next"
          aria-label="Наступне фото"
          onClick={(e) => {
            e.stopPropagation();
            goNext();
          }}
        >
          ›
        </button>
      ) : null}

      {photos.length > 1 ? (
        <div className="photo-viewer-dots" aria-hidden="true">
          {photos.map((p, i) => (
            <span key={p.id} className={`photo-viewer-dot${i === index ? " photo-viewer-dot--active" : ""}`} />
          ))}
        </div>
      ) : null}
    </div>
  );

  return createPortal(viewer, document.body);
}
