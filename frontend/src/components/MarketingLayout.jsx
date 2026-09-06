import MarketingNav    from "./MarketingNav.jsx";
import MarketingFooter from "./MarketingFooter.jsx";

export default function MarketingLayout({ title, children }) {
  return (
    <div className="font-body text-ink bg-paper antialiased">
      <MarketingNav />
      <main className="pt-24 pb-20 px-6 max-w-3xl mx-auto min-h-screen">
        <h1 className="font-display text-4xl text-ink mb-8">{title}</h1>
        <div className="prose prose-neutral max-w-none">
          {children}
        </div>
      </main>
      <MarketingFooter />
    </div>
  );
}
