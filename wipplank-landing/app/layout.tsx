import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "Wipplank — Email for humans and agents", description: "An open-source email client for the terminal, with a CLI, TUI and MCP server built in." };
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="en"><body>{children}</body></html>; }
