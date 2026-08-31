import { CATEGORY_COLORS, CATEGORY_LABELS } from "@/lib/filters";
import type { Category } from "@/lib/types";

export default function CategoryTag({ category }: { category: Category }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 border px-1.5 py-0.5 text-xs font-medium"
      style={{ borderColor: CATEGORY_COLORS[category], color: CATEGORY_COLORS[category] }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: CATEGORY_COLORS[category] }}
      />
      {CATEGORY_LABELS[category]}
    </span>
  );
}
