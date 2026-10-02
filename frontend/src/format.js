export const PLATFORM_COLORS = {
  netflix: "var(--netflix)",
  prime: "var(--prime)",
  disney: "var(--disney)",
  apple: "var(--apple)",
  crave: "var(--crave)",
};

const DASH = "–";

export const num = (v, digits = 1) => (v == null ? DASH : v.toFixed(digits));
export const pct = (v, digits = 0) => (v == null ? DASH : `${(v * 100).toFixed(digits)}%`);
export const count = (v) => (v == null ? DASH : v.toLocaleString());

export function signed(v, digits = 2) {
  if (v == null) return DASH;
  const rounded = Number(v.toFixed(digits));
  if (rounded === 0) return `±${(0).toFixed(digits)}`;
  return `${rounded > 0 ? "+" : "−"}${Math.abs(rounded).toFixed(digits)}`;
}

// Change in a 0–1 share, shown in percentage points
export const signedPoints = (v, digits = 1) => (v == null ? DASH : `${signed(v * 100, digits)} pts`);

export function trend(v, threshold = 0.005) {
  if (v == null || Math.abs(v) < threshold) return "flat";
  return v > 0 ? "up" : "down";
}

export const when = (iso) =>
  iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : DASH;

export const shortDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : DASH;

export function regionName(code) {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(code);
  } catch {
    return code;
  }
}
