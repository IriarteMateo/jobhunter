import type { Metadata } from "next";
import "./globals.css";
import { AutoActualizar } from "@/components/AutoActualizar";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "AI Job Hunter",
  description: "Buscador y ranking inteligente de empleos para primer trabajo en Buenos Aires",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="min-h-full">
        <Nav />
        <main className="mx-auto w-full max-w-6xl px-4 pb-24 pt-6 sm:px-6">{children}</main>
        <AutoActualizar />
      </body>
    </html>
  );
}
