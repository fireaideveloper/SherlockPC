import { t } from "../i18n";

export function Pager({
  page,
  pages,
  onChange,
  disabled = false,
}: {
  page: number;
  pages: number;
  onChange: (page: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="pager">
      <button
        disabled={disabled || page === 0}
        onClick={() => onChange(page - 1)}
        aria-label={t("Previous page")}
      >
        ←
      </button>
      <span>
        {page + 1} / {Math.max(1, pages)}
      </span>
      <button
        disabled={disabled || page + 1 >= pages}
        onClick={() => onChange(page + 1)}
        aria-label={t("Next page")}
      >
        →
      </button>
    </div>
  );
}
