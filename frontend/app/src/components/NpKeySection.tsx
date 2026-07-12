import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import * as api from "../api";
import { errorMessage } from "../errors";
import { NpCityPicker } from "./NpCityPicker";
import { NpWarehousePicker } from "./NpWarehousePicker";
import type { NpCity, NpSenderProfile, NpWarehouse } from "../types";

function isSenderConfigured(sender: NpSenderProfile | null): boolean {
  return (
    sender !== null &&
    sender.city_ref !== null &&
    sender.warehouse_ref !== null &&
    sender.phone !== null &&
    sender.name !== null
  );
}

function SenderSection() {
  const { t } = useTranslation();
  const [sender, setSender] = useState<NpSenderProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [city, setCity] = useState<NpCity | null>(null);
  const [warehouse, setWarehouse] = useState<NpWarehouse | null>(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const profile = await api.getNpSender();
        if (!mounted) return;
        setSender(profile);
        setName(profile.name ?? "");
        setPhone(profile.phone ?? "");
        setCity(
          profile.city_ref && profile.city_name
            ? { ref: profile.city_ref, name: profile.city_name }
            : null,
        );
        setWarehouse(
          profile.warehouse_ref && profile.warehouse_name
            ? { ref: profile.warehouse_ref, name: profile.warehouse_name }
            : null,
        );
      } catch (err) {
        if (!mounted) return;
        setError(errorMessage(err, t("settings.np.senderLoadFailed")));
      } finally {
        if (mounted) setLoading(false);
      }
    }
    void load();
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t навмисно не в deps: завантаження лише на mount
  }, []);

  async function handleSave() {
    if (!name.trim() || !phone.trim() || !city || !warehouse) {
      setError(t("settings.np.senderFieldsMissing"));
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const profile = await api.putNpSender({
        city_ref: city.ref,
        city_name: city.name,
        warehouse_ref: warehouse.ref,
        warehouse_name: warehouse.name,
        phone: phone.trim(),
        name: name.trim(),
      });
      setSender(profile);
    } catch (err) {
      setError(errorMessage(err, t("settings.np.senderSaveFailed")));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="np-sender-section">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-bold text-text-soft uppercase tracking-wide">
          {t("settings.np.senderTitle")}
        </h4>
        {isSenderConfigured(sender) ? (
          <span className="rounded-full bg-[var(--state-ok)] px-2.5 py-0.5 text-[10px] font-bold text-green-deep">
            {t("settings.np.senderConfigured")}
          </span>
        ) : null}
      </div>

      {loading ? (
        <p className="status-text">{t("common.loading")}</p>
      ) : (
        <>
          {error ? <p className="error-banner">{error}</p> : null}
          <label className="form-field">
            <span>{t("settings.np.fullNameLabel")}</span>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="form-field">
            <span>{t("settings.np.phoneLabel")}</span>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="380XXXXXXXXX"
            />
          </label>
          <NpCityPicker label={t("shipping.city")} value={city} onChange={setCity} />
          <NpWarehousePicker
            label={t("shipping.warehouse")}
            cityRef={city?.ref ?? null}
            value={warehouse}
            onChange={setWarehouse}
          />
          <button
            type="button"
            className="mt-1"
            disabled={saving}
            onClick={() => void handleSave()}
          >
            {saving ? t("settings.np.senderSaving") : t("settings.np.senderSaveButton")}
          </button>
        </>
      )}
    </div>
  );
}

export function NpKeySection() {
  const { t } = useTranslation();
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const status = await api.getNpStatus();
        if (!mounted) return;
        setConnected(status.connected);
      } catch (err) {
        if (!mounted) return;
        setError(errorMessage(err, t("settings.np.checkStatusFailed")));
      } finally {
        if (mounted) setLoading(false);
      }
    }
    void load();
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t навмисно не в deps: завантаження лише на mount
  }, []);

  async function handleConnect() {
    if (!apiKey.trim()) return;
    setError(null);
    setSaving(true);
    try {
      const status = await api.putNpKey(apiKey.trim());
      setConnected(status.connected);
      setApiKey("");
    } catch (err) {
      setError(errorMessage(err, t("settings.np.connectFailed")));
    } finally {
      setSaving(false);
    }
  }

  async function handleDisconnect() {
    setError(null);
    try {
      await api.deleteNpKey();
      setConnected(false);
    } catch (err) {
      setError(errorMessage(err, t("settings.np.disconnectFailed")));
    } finally {
      setConfirmDisconnect(false);
    }
  }

  return (
    <div className="glass-card rounded-[20px] p-4 shadow-[var(--shadow-card)]">
      <h3 className="text-sm font-bold text-text-soft uppercase tracking-wide mb-3">
        {t("settings.np.title")}
      </h3>

      {error ? <p className="error-banner">{error}</p> : null}

      {loading ? (
        <p className="status-text">{t("common.loading")}</p>
      ) : connected ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="rounded-full bg-[var(--state-ok)] px-2.5 py-0.5 text-[10px] font-bold text-green-deep">
              {t("settings.np.connected")}
            </span>
          </div>
          <p className="text-xs text-text-soft">{t("settings.np.autoUpdateHint")}</p>

          {confirmDisconnect ? (
            <div className="flex gap-2 mt-1">
              <button type="button" onClick={() => setConfirmDisconnect(false)}>
                {t("settings.np.no")}
              </button>
              <button type="button" className="btn-danger" onClick={() => void handleDisconnect()}>
                {t("settings.np.confirmDisconnect")}
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="btn-danger-outline mt-1"
              onClick={() => setConfirmDisconnect(true)}
            >
              {t("settings.np.disconnectButton")}
            </button>
          )}

          <div className="sheet-divider" />
          <SenderSection />
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex gap-2">
            <label className="flex-1 flex flex-col gap-1">
              <span className="text-xs font-semibold text-text-soft">
                {t("settings.np.apiKeyLabel")}
              </span>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full rounded-xl px-3 py-2 text-sm bg-[var(--glass-bg)] border border-[var(--line)] text-text outline-none focus:border-[var(--green)]"
              />
            </label>
            <button
              type="button"
              disabled={saving || !apiKey.trim()}
              onClick={() => void handleConnect()}
              className="shrink-0 rounded-xl px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
              style={{
                background: "linear-gradient(135deg, var(--green) 0%, var(--green-deep) 100%)",
                boxShadow: "var(--shadow-cta)",
              }}
            >
              {saving ? t("settings.ellipsis") : t("settings.np.connectButton")}
            </button>
          </div>
          <p className="text-xs text-text-soft">{t("settings.np.apiKeyHint")}</p>
        </div>
      )}
    </div>
  );
}
