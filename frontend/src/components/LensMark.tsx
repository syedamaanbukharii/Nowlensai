// The NowLens mark: a stylised camera aperture — the "lens" that brings
// documentation into focus. Used in the rail and on the auth gate.

export function LensMark({ size = 26 }: { size?: number }) {
  return (
    <svg
      className="brand-mark"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="16" cy="16" r="14" stroke="var(--primary)" strokeWidth="2" />
      {/* aperture blades */}
      <g stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round">
        <path d="M16 4 L24.5 9 L24.5 9" />
        <path d="M16 16 L16 4" opacity="0" />
      </g>
      <path
        d="M16 8.5 L22.5 12.2 L22.5 19.8 L16 23.5 L9.5 19.8 L9.5 12.2 Z"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinejoin="round"
        fill="none"
      />
      <circle cx="16" cy="16" r="3" fill="var(--primary)" />
    </svg>
  );
}
