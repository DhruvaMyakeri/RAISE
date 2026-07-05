import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vantage: Grounded AI ROI Intelligence",
  description:
    "A multi-agent system that predicts and explains AI project ROI, grounded in company data and cited industry benchmarks.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <div className="topbar-inner">
            <div className="brand">
              <div className="brand-mark">
                <span />
              </div>
              <div>
                <div className="brand-name">Vantage</div>
                <div className="brand-sub">Grounded AI ROI Intelligence</div>
              </div>
            </div>
            <div className="topbar-tag">
              <span className="status-dot" />
              multi-agent · Vultr + NVIDIA
            </div>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
