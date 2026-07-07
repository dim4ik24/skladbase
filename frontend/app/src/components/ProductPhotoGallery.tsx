import { useRef, useState } from "react";
import { ApiError } from "../api";
import { PhotoViewer } from "./PhotoViewer";
import type { Product } from "../types";

interface ProductPhotoGalleryProps {
  product: Product;
  photosAllowed: boolean;
  onUpload: (file: File) => Promise<void>;
  onDelete: (photoId: number) => Promise<void>;
}

export function ProductPhotoGallery({
  product,
  photosAllowed,
  onUpload,
  onDelete,
}: ProductPhotoGalleryProps) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const sortedPhotos = [...product.photos].sort((a, b) => a.position - b.position);
  const count = sortedPhotos.length;

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;

    setUploading(true);
    setError(null);
    try {
      await onUpload(file);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) setError("Максимум 10 фото на товар");
        else if (err.status === 413) setError("Файл занадто великий");
        else if (err.status !== 402) setError(err.detail);
        // 402 — already shown by App as UpgradePrompt
      } else {
        setError("Помилка завантаження");
      }
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(photoId: number) {
    setError(null);
    try {
      await onDelete(photoId);
    } catch (err) {
      if (err instanceof ApiError) setError(err.detail);
      else setError("Помилка видалення");
    }
  }

  return (
    <div className="photo-gallery-section">
      <p className="photo-gallery-title">
        Фото товару{" "}
        <span className="photo-count">{count}/10</span>
      </p>

      {!photosAllowed ? (
        <p className="photo-blocked-notice">
          Фото доступні на тарифі Basic+. Видалення наявних дозволено.
        </p>
      ) : null}

      <div className="photo-grid">
        {sortedPhotos.map((photo, i) => (
          <div key={photo.id} className="photo-thumb">
            <img src={photo.url} alt="" onClick={() => setViewerIndex(i)} />
            <button
              type="button"
              className="photo-thumb__remove"
              aria-label="Видалити фото"
              onClick={() => void handleDelete(photo.id)}
            >
              ✕
            </button>
          </div>
        ))}

        {photosAllowed ? (
          <>
            <button
              type="button"
              className="photo-add-btn"
              disabled={uploading || count >= 10}
              aria-label="Додати фото товару"
              onClick={() => fileInputRef.current?.click()}
            >
              {uploading ? "…" : "+"}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              hidden
              onChange={handleFileChange}
            />
          </>
        ) : null}
      </div>

      {error ? <p className="photo-error">{error}</p> : null}

      {viewerIndex !== null ? (
        <PhotoViewer
          photos={sortedPhotos}
          initialIndex={viewerIndex}
          onClose={() => setViewerIndex(null)}
        />
      ) : null}
    </div>
  );
}
