import { getCouponContent } from "@/lib/data";
import Markdown from "react-markdown";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export default async function CouponDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const filename = decodeURIComponent(slug);
  const content = getCouponContent(filename);

  return (
    <div className="p-8">
      <Link
        href="/coupons"
        className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary mb-6"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to coupons
      </Link>

      <h1 className="text-2xl font-bold text-white mb-6">{filename}</h1>

      <div className="rounded-xl border border-border-card bg-bg-card p-6">
        {content ? (
          <div className="prose prose-invert prose-sm max-w-none font-mono text-sm leading-relaxed text-text-primary [&_h1]:text-text-primary [&_h2]:text-text-primary [&_h3]:text-text-primary [&_a]:text-accent [&_strong]:text-white [&_table]:text-text-secondary [&_th]:text-text-primary [&_td]:border-border-card [&_th]:border-border-card [&_hr]:border-border-card">
            <Markdown>{content}</Markdown>
          </div>
        ) : (
          <p className="text-text-secondary">Coupon file not found.</p>
        )}
      </div>
    </div>
  );
}
