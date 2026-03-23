import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { InfoIcon } from "./icons";

type InfoTooltipProps = {
  tooltipId: string;
  buttonLabel: string;
  content: string;
  align?: "left" | "right";
  buttonClassName?: string;
};

type TooltipPosition = {
  top: number;
  left: number;
  width: number;
};

const VIEWPORT_PADDING = 12;
const MOBILE_BREAKPOINT = 768;
const TOOLTIP_GAP = 10;
const DESKTOP_TOOLTIP_WIDTH = 288;

export function InfoTooltip({
  tooltipId,
  buttonLabel,
  content,
  align = "right",
  buttonClassName = "rounded-full p-0.5 text-zinc-500 outline-none transition-colors hover:text-zinc-400 focus-visible:ring-2 focus-visible:ring-teal-400/70",
}: InfoTooltipProps) {
  const [visible, setVisible] = useState(false);
  const [position, setPosition] = useState<TooltipPosition | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    if (!visible || !buttonRef.current || !panelRef.current) {
      return;
    }

    function updatePosition() {
      if (!buttonRef.current || !panelRef.current) {
        return;
      }

      const buttonRect = buttonRef.current.getBoundingClientRect();
      const panelRect = panelRef.current.getBoundingClientRect();
      const isMobile = window.innerWidth <= MOBILE_BREAKPOINT;

      if (isMobile) {
        setPosition({
          top: VIEWPORT_PADDING,
          left: VIEWPORT_PADDING,
          width: window.innerWidth - VIEWPORT_PADDING * 2,
        });
        return;
      }

      const width = Math.min(DESKTOP_TOOLTIP_WIDTH, window.innerWidth - VIEWPORT_PADDING * 2);
      const measuredHeight = panelRect.height;
      const desiredLeft = align === "left" ? buttonRect.left : buttonRect.right - width;
      const left = Math.min(
        Math.max(desiredLeft, VIEWPORT_PADDING),
        window.innerWidth - width - VIEWPORT_PADDING,
      );

      const spaceBelow = window.innerHeight - buttonRect.bottom - VIEWPORT_PADDING;
      const spaceAbove = buttonRect.top - VIEWPORT_PADDING;
      const showAbove = spaceBelow < measuredHeight + TOOLTIP_GAP && spaceAbove > spaceBelow;
      const desiredTop = showAbove
        ? buttonRect.top - measuredHeight - TOOLTIP_GAP
        : buttonRect.bottom + TOOLTIP_GAP;
      const top = Math.min(
        Math.max(desiredTop, VIEWPORT_PADDING),
        window.innerHeight - measuredHeight - VIEWPORT_PADDING,
      );

      setPosition({ top, left, width });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [align, content, visible]);

  const tooltip =
    visible && typeof document !== "undefined"
      ? createPortal(
          <div
            className={`pointer-events-none fixed z-[9999] rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-left text-xs text-zinc-300 shadow-2xl transition-opacity duration-200 ${
              position ? "opacity-100" : "opacity-0"
            }`}
            id={tooltipId}
            ref={panelRef}
            role="tooltip"
            style={
              position
                ? {
                    top: `${position.top}px`,
                    left: `${position.left}px`,
                    width: `${position.width}px`,
                    maxWidth: `${position.width}px`,
                  }
                : {
                    top: `${VIEWPORT_PADDING}px`,
                    left: `${VIEWPORT_PADDING}px`,
                    width: `${DESKTOP_TOOLTIP_WIDTH}px`,
                    maxWidth: `calc(100vw - ${VIEWPORT_PADDING * 2}px)`,
                    visibility: "hidden",
                  }
            }
          >
            {content}
          </div>,
          document.body,
        )
      : null;

  return (
    <div
      className="relative"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      <button
        aria-describedby={tooltipId}
        aria-expanded={visible}
        aria-label={buttonLabel}
        className={buttonClassName}
        onBlur={() => setVisible(false)}
        onClick={() => setVisible((current) => !current)}
        onFocus={() => setVisible(true)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setVisible(false);
          }
        }}
        ref={buttonRef}
        type="button"
      >
        <InfoIcon aria-hidden="true" className="h-4 w-4 cursor-help" />
      </button>
      {tooltip}
    </div>
  );
}
