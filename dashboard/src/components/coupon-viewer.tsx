import { getLatestCoupon } from "@/lib/data";
import Markdown from "react-markdown";

export async function CouponViewer() {
  const coupon = getLatestCoupon();

  return (
    <div className="rounded-xl border border-border-card bg-bg-card p-5">
      <h2 className="text-lg font-semibold text-text-primary mb-4">
        Latest Daily Run
      </h2>
      {coupon ? (
        <div className="max-h-[500px] overflow-y-auto pr-2">
          <p className="text-xs text-text-secondary mb-3">{coupon.filename}</p>
          <div className="prose prose-invert prose-sm max-w-none font-mono text-sm leading-relaxed text-text-primary [&_h1]:text-text-primary [&_h2]:text-text-primary [&_h3]:text-text-primary [&_a]:text-accent [&_strong]:text-white [&_table]:text-text-secondary [&_th]:text-text-primary [&_td]:border-border-card [&_th]:border-border-card [&_hr]:border-border-card">
            <Markdown>{coupon.content}</Markdown>
          </div>
        </div>
      ) : (
        <p className="text-sm text-text-secondary">
          No coupon files found. Run the pipeline to generate today&apos;s
          coupons.
        </p>
      )}
    </div>
  );
}
