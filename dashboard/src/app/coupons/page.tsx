import Link from "next/link";
import { FileText } from "lucide-react";
import { getCouponList } from "@/lib/data";

export default function CouponsPage() {
  const coupons = getCouponList();

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-white mb-8">Target Coupons</h1>

      {coupons.length === 0 ? (
        <div className="rounded-xl border border-border-card bg-bg-card p-8 text-center">
          <p className="text-text-secondary">
            No coupon files found in betting/coupons/.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {coupons.map((coupon) => (
            <Link
              key={coupon.filename}
              href={`/coupons/${encodeURIComponent(coupon.filename)}`}
              className="flex items-center gap-3 rounded-xl border border-border-card bg-bg-card p-4 transition-colors hover:border-accent/50"
            >
              <FileText className="h-5 w-5 text-accent" />
              <div>
                <p className="text-sm font-medium text-text-primary">
                  {coupon.date}
                </p>
                <p className="text-xs text-text-secondary">
                  {coupon.filename}
                </p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
