import { useState } from "react";
import { InfoIcon } from "./icons";

type InfoTooltipProps = {
  tooltipId: string;
  buttonLabel: string;
  content: string;
  align?: "left" | "right";
  buttonClassName?: string;
};

export function InfoTooltip({
  tooltipId,
  buttonLabel,
  content,
  align = "right",
  buttonClassName = "rounded-full p-0.5 text-zinc-500 outline-none transition-colors hover:text-zinc-400 focus-visible:ring-2 focus-visible:ring-teal-400/70",
}: InfoTooltipProps) {
  const [visible, setVisible] = useState(false);

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
        type="button"
      >
        <InfoIcon aria-hidden="true" className="h-4 w-4 cursor-help" />
      </button>
      <div
        className={`info-tooltip-panel pointer-events-none absolute top-full z-10 mt-2 w-72 max-w-[min(18rem,calc(100vw-2rem))] rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-left text-xs text-zinc-300 transition-opacity duration-200 ${
          align === "left" ? "left-0" : "right-0"
        } ${visible ? "opacity-100" : "opacity-0"}`}
        id={tooltipId}
      >
        {content}
      </div>
    </div>
  );
}
