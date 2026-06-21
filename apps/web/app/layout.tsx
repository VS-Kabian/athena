import type { Metadata } from "next";
import { Hanken_Grotesk, JetBrains_Mono } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { Sidebar } from "@/components/shell/Sidebar";

const sans = Hanken_Grotesk({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "ATHENA — Deep Research",
  description: "Autonomous deep research.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <body className={`${sans.variable} ${mono.variable}`}>
        <Script id="theme-init" strategy="beforeInteractive">
          {"try{var t=localStorage.getItem('athena:theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;}catch(e){}"}
        </Script>
        <div className="app-shell">
          <Sidebar />
          <main className="app-main">{children}</main>
        </div>
      </body>
    </html>
  );
}
